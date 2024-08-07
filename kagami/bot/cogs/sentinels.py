import re
from abc import ABC
from copy import deepcopy
from dataclasses import dataclass
from enum import IntEnum, auto

import aiosqlite
import discord
import discord.ui
from discord.ext import commands
from discord import app_commands, Interaction, InteractionMessage, InteractionResponse
from discord.ext.commands import GroupCog, Cog
from discord. app_commands import AppCommand, Transform, Transformer, Range, Group, Choice, autocomplete

from bot.ext import errors
from bot.kagami_bot import Kagami
from bot.utils.bot_data import Server, OldSentinel
from bot.utils.interactions import respond
from bot.utils.ui import MessageScroller
from bot.utils.database import Database, InfoDB
from bot.utils.pages import createPageList, createPageInfoText, CustomRepr
from typing import (
    Literal, Union, List, Any
)


class SentinelDB(Database):
    @dataclass
    class SentinelSettings(Database.Row):
        guild_id: int
        sentinels_enabled: bool = True
        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS SentinelSettings(
            guild_id INTEGER NOT NULL,
            sentinels_enabled INTEGER DEFAULT 1,
            PRIMARY KEY(guild_id),
            FOREIGN KEY(guild_id) REFERENCES GUILD(id) 
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            )
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS SentinelSettings
            """
            TRIGGER_BEFORE_INSERT_GUILD = """
            CREATE TRIGGER IF NOT EXISTS SentinelSettings_insert_guild_before_insert
            BEFORE INSERT ON SentinelSettings
            BEGIN
                INSERT INTO Guild(id)
                VALUES (NEW.guild_id)
                ON CONFLICT(id) DO NOTHING;
            END;
            """
            UPSERT = """
            INSERT INTO SentinelSettings (guild_id, sentinels_enabled)
            VALUES(:guild_id, :sentinels_enabled)
            ON CONFLICT (guild_id)
            DO UPDATE SET sentinels_enabled = :sentinels_enabled
            """
            SELECT = """
            SELECT * FROM SentinelSettings
            WHERE guild_id = ?
            """
            DELETE = """
            DELETE FROM SentinelSettings
            WHERE guild_id = ?
            """

    @dataclass
    class Sentinel(Database.Row):
        guild_id: int
        name: str
        uses: int
        enabled: bool = True
        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS Sentinel(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            uses INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            PRIMARY KEY(guild_id, name),
            FOREIGN KEY(guild_id) REFERENCES GUILD(id) 
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            )
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS Sentinel
            """
            TRIGGER_BEFORE_INSERT_SETTINGS = """
            CREATE TRIGGER IF NOT EXISTS Sentinel_insert_settings_before_insert
            BEFORE INSERT ON Sentinel
            BEGIN
                INSERT INTO SentinelSettings(guild_id)
                VALUES (NEW.guild_id)
                ON CONFLICT(guild_id) DO NOTHING;
            END;
            """
            INSERT = """
            INSERT OR IGNORE INTO Sentinel(guild_id, name)
            VALUES(:guild_id, :name)
            """
            INCREMENT_USES = """
            UPDATE Sentinel SET uses = uses + 1
            WHERE guild_id = ? AND name = ?
            """
            EDIT = """
            Update Sentinel SET name = :name
            WHERE name = :old_name
            """
            SELECT = """
            SELECT * FROM Sentinel
            WHERE guild_id = ? AND name = ?
            """
            SELECT_LIKE_NAMES = """
            SELECT name FROM Sentinel
            WHERE (guild_id = ?) AND (name LIKE ?)
            LIMIT ? OFFSET ?
            """
            TOGGLE = """
            UPDATE Sentinel
            SET
                enabled = NOT enabled
            WHERE
                guild_id = ? AND
                name = ?
            """

    class DisabledSentinelChannels(Database.Row):
        guild_id: int
        channel_id: int
        class Queries:
            CREATE_TABLE = f"""
            CREATE TABLE IF NOT EXISTS DisabledSentinelChannels(
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY(guild_id, channel_id),
                FOREIGN KEY(guild_id) REFERENCES GUILD(id)
                    ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            )
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS DisabledSentinelChannels
            """
            TRIGGER_BEFORE_INSERT_SETTINGS = """
            CREATE TRIGGER IF NOT EXISTS DisabledSentinelChannels_insert_settings_before_insert
            BEFORE INSERT ON DisabledSentinelChannels
            BEGIN
                INSERT INTO SentinelSettings(guild_id)
                VALUES (NEW.guild_id)
                ON CONFLICT(guild_id) DO NOTHING;
            END;
            """
            INSERT = """
            INSERT OR IGNORE INTO DisabledSentinelChannels(guild_id, channel_id)
            VALUES(:guild_id, :channel_id)
            """
            DELETE = """
            DELETE FROM DisabledSentinelChannels
            WHERE guild_id = :guild_id AND channel_id = :channel_id
            """
            TOGGLE = f"""
            SELECT CASE WHEN EXISTS (
                    SELECT 1 FROM DisabledSentinelChannels WHERE 
                        guild_id = :guild_id AND channel_id = : channel_id
                ) THEN
                {DELETE}
            ELSE
                {INSERT}
            END;
            """
            SELECT_EXISTS = """
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM DisabledSentinelChannels
                WHERE
                    guild_id = :guild_id AND channel_id = : channel_id
            )
            THEN 1
            ELSE 0
            END;
            """

    @dataclass
    class SentinelTrigger(Database.Row):
        class TriggerType(IntEnum):
            word = 1 # in message split by spaces
            phrase = 2 # in message as string
            regex = 3 # regex matching
            reaction = 4 # triggers on a reaction
        type: TriggerType
        object: str
        id: int = None
        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS SentinelTrigger(
            id INTEGER NOT NULL,
            type INTEGER NOT NULL,
            object TEXT NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (type, object) 
            )
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS SentinelTrigger
            """
            INSERT = """
            INSERT INTO SentinelTrigger(type, object)
            VALUES (:type, :object)
            ON CONFLICT(type, object) DO NOTHING
            RETURNING id
            """
            SELECT_ID = """
            SELECT id FROM SentinelTrigger
            WHERE type = ? AND object = ?
            """
            SELECT_IDS = """
            SELECT id FROM SentinelTrigger
            WHERE object = ?
            """
            DELETE = """
            DELETE FROM SentinelTrigger
            WHERE id = :id
            returning *
            """

    @dataclass
    class SentinelResponse(Database.Row):
        class ResponseType(IntEnum):
            message = 1
            reply = 2
        type: ResponseType
        content: str
        reactions: str
        id: int = None

        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS SentinelResponse(
            id INTEGER NOT NULL,
            type INTEGER NOT NULL,
            content TEXT,
            reactions TEXT,
            PRIMARY KEY (id),
            UNIQUE (type, content, reactions)
            )
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS SentinelResponse
            """
            INSERT = """
            INSERT INTO SentinelResponse(type, content, reactions)
            VALUES (:type, :content, :reactions)
            ON CONFLICT(type, content, reactions) DO NOTHING
            RETURNING id
            """
            SELECT_ID = """
            SELECT id FROM SentinelResponse
            WHERE type = ? AND content = ? AND reactions = ?
            """
            SELECT_RESPONSE = """
            SELECT
                *
            FROM SentinelResponse
            WHERE id = ?
            """
            DELETE = """
            DELETE FROM SentinelResponse
            WHERE id = :id
            RETURNING *
            """

    @dataclass
    class SentinelSuit(Database.Row):
        guild_id: int
        sentinel_name: str
        name: str
        weight: int = 100
        trigger_id: int = None
        response_id: int = None
        enabled: bool = True

        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS SentinelSuit(
            guild_id INTEGER NOT NULL,
            sentinel_name TEXT NOT NULL,
            name TEXT NOT NULL,
            weight INTEGER NOT NULL ON CONFLICT REPLACE DEFAULT 10,
            trigger_id INTEGER DEFAULT NULL,
            response_id INTEGER DEFAULT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (guild_id, sentinel_name, name),
            FOREIGN KEY (guild_id) REFERENCES Guild(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (sentinel_name) REFERENCES Sentinel(name)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (trigger_id) REFERENCES SentinelTrigger(id)
                ON UPDATE RESTRICT ON DELETE SET NULL,
            FOREIGN KEY (response_id) REFERENCES SentinelResponse(id)
                ON UPDATE RESTRICT ON DELETE SET NULL
            )
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS SentinelSuit
            """
            TRIGGER_BEFORE_INSERT_SENTINEL = """
            CREATE TRIGGER IF NOT EXISTS SentinelSuit_insert_sentinel_before_insert
            BEFORE INSERT ON SentinelSuit
            BEGIN
                INSERT INTO Sentinel(guild_id, name)
                VALUES (NEW.guild_id, NEW.sentinel_name)
                ON CONFLICT(guild_id, name) DO NOTHING;
            END
            """
            TRIGGER_AFTER_UPDATE_TRIGGER = """
            CREATE TRIGGER IF NOT EXISTS SentinelSuit_delete_trigger_after_update
            AFTER UPDATE OF trigger_id on SentinelSuit
            WHEN (SELECT COUNT(*) FROM SentinelSuit WHERE trigger_id = OLD.trigger_id) = 0 
            BEGIN
                DELETE FROM SentinelTrigger
                WHERE id = OLD.trigger_id;
            END
            """
            TRIGGER_AFTER_UPDATE_RESPONSE = """
            CREATE TRIGGER IF NOT EXISTS SentinelSuit_delete_response_after_update
            AFTER UPDATE OF response_id on SentinelSuit
            WHEN (SELECT COUNT(*) FROM SentinelSuit WHERE response_id = OLD.response_id) = 0 
            BEGIN
                DELETE FROM SentinelResponse
                WHERE id = OLD.response_id;
            END
            """
            TRIGGER_AFTER_UPDATE = """
            CREATE TRIGGER IF NOT EXISTS SentinelSuit_delete_after_update
            AFTER UPDATE ON SentinelSuit
            WHEN NEW.trigger_id IS NULL AND NEW.response_id IS NULL
            BEGIN
                DELETE FROM SentinelSuit
                WHERE guild_id = OLD.guild_id AND name = OLD.name AND sentinel_name = OLD.sentinel_name;
            END
            """
            TRIGGER_AFTER_DELETE_TRIGGER = """
            CREATE TRIGGER IF NOT EXISTS SentinelSuit_delete_trigger_after_delete
            AFTER DELETE ON SentinelSuit
            WHEN (SELECT COUNT(*) FROM SentinelSuit WHERE trigger_id = OLD.trigger_id) = 0
            BEGIN
                DELETE FROM SentinelTrigger
                WHERE id = OLD.trigger_id;
            END
            """
            TRIGGER_AFTER_DELETE_RESPONSE = """
            CREATE TRIGGER IF NOT EXISTS SentinelSuit_delete_response_after_delete
            AFTER DELETE ON SentinelSuit
            WHEN (SELECT COUNT(*) FROM SentinelSuit WHERE response_id = OLD.response_id) = 0
            BEGIN
                DELETE FROM SentinelResponse
                WHERE id = OLD.response_id;
            END
            """
            # _DELETE_TRIGGER_TRACKING_AFTER_DELETE = """
            # CREATE TRIGGER IF NOT EXISTS SentinelSuit_delete_trigger_tracking_after_delete
            # AFTER DELETE ON SentinelSuit
            # WHEN (
            #     SELECT COUNT(*) FROM SentinelSuit WHERE trigger_id = OLD.trigger_id AND guild_id = OLD.guild_id
            # ) = 0
            # BEGIN
            #     DELETE FROM SentinelTrigger
            #     WHERE id = OLD.trigger_id;
            # END
            # """
            # _DELETE_RESPONSE_TRACKING_AFTER_DELETE = """
            # CREATE TRIGGER IF NOT EXISTS SentinelSuit_delete_response_after_delete
            # AFTER DELETE ON SentinelSuit
            # WHEN (
            #     SELECT COUNT(*) FROM SentinelSuit WHERE response_id = OLD.response_id AND guild_id = OLD.guild_id
            # ) = 0
            # BEGIN
            #     DELETE FROM SentinelResponse
            #     WHERE id = OLD.response_id;
            # END
            # """
            INSERT = """
            INSERT OR IGNORE INTO SentinelSuit(guild_id, sentinel_name, name, weight, trigger_id, response_id)
            VALUES (:guild_id, :sentinel_name, :name, :weight, :trigger_id, :response_id)
            """
            UPSERT = """
            INSERT INTO SentinelSuit(guild_id, sentinel_name, name, weight, trigger_id, response_id)
            VALUES (:guild_id, :sentinel_name, :name, :weight, :trigger_id, :response_id)
            ON CONFLICT (guild_id, sentinel_name, name)
            DO UPDATE SET trigger_id = coalesce(trigger_id, :trigger_id), 
                          response_id = coalesce(response_id, :response_id)
            """
            UPDATE = """
            INSERT INTO SentinelSuit(guild_id, sentinel_name, name, weight, trigger_id, response_id)
            VALUES (:guild_id, :sentinel_name, :name, :weight, :trigger_id, :response_id)
            ON CONFLICT (guild_id, sentinel_name, name)
            DO UPDATE SET trigger_id = :trigger_id,
                          response_id = :response_id,
                          weight = :weight
            """
            SELECT = """
            SELECT * FROM SentinelSuit
            WHERE guild_id = ? AND sentinel_name = ? AND name = ?
            """
            SELECT_FROM_TRIGGER_ID = """
            SELECT * FROM SentinelSuit
            WHERE guild_id = ? AND trigger_id = ?
            """
            SELECT_NULL_TRIGGER_SUITS = """
            SELECT * FROM SentinelSuit 
            WHERE guild_id = :guild_id AND sentinel_name = :sentinel_name AND trigger_id = NULL
            """
            SELECT_NULL_TRIGGER_NAMES = """
            SELECT name FROM SentinelSuit 
            WHERE (guild_id = ?) AND (sentinel_name = ?) AND (trigger_id IS NULL)
            """
            SELECT_SIMILAR_NULL_TRIGGER_SUIT_NAMES = """
            SELECT name FROM SentinelSuit 
            WHERE (guild_id = ?) AND (sentinel_name = ?) AND (trigger_id IS NULL) AND (name LIKE ?)
            LIMIT ? OFFSET ?
            """
            SELECT_NULL_RESPONSE_SUITS = """
            SELECT * FROM SentinelSuit 
            WHERE * AND (sentinel_name = ?) AND (response_id IS NULL)
            """
            SELECT_SIMILAR_NULL_RESPONSE_SUIT_NAMES = """
            SELECT name FROM SentinelSuit 
            WHERE (guild_id = ?) AND (sentinel_name = ?) AND (response_id IS NULL) AND (name LIKE ?)
            LIMIT ? OFFSET ?
            """
            SELECT_SIMILAR_SUIT_NAMES = """
            SELECT name FROM SentinelSuit
            WHERE guild_id = ? AND sentinel_name = ? AND name LIKE ?
            LIMIT ? OFFSET ?
            """
            TOGGLE = """
            UPDATE SentinelSuit
            SET
                enabled = NOT enabled
            WHERE
                guild_id = ? AND
                sentinel_name = ? AND
                name = ?
            """
            DELETE = """
            DELETE FROM SentinelSuit WHERE guild_id = ? AND sentinel_name = ? AND name = ?
            """
            __space_regex = "[,.;:''\"?!@#$%^&*()~`+=|/\\ ]" # sql escaped space regex
            GET_SUITS_FROM_MESSAGE = f"""
            WITH triggered_suits AS (
                SELECT
                    SentinelSuit.guild_id,
                    SentinelSuit.sentinel_name,
                    SentinelSuit.name,
                    weight,
                    trigger_id,
                    response_id,
                    SentinelSuit.enabled,
                    Sentinel.enabled AS sentinel_enabled
                FROM SentinelSuit
                LEFT JOIN SentinelTrigger ON 
                    SentinelTrigger.id = SentinelSuit.trigger_id 
                LEFT JOIN Sentinel ON 
                    Sentinel.name = SentinelSuit.sentinel_name
                WHERE 
                    (
                        (SentinelTrigger.type = 1 AND ' '||:message_content||' ' REGEXP '{__space_regex}'||SentinelTrigger.object||'{__space_regex}') OR  
                        (SentinelTrigger.type = 2 AND instr(:message_content, SentinelTrigger.object)) OR  
                        (SentinelTrigger.type = 3 AND :message_content REGEXP SentinelTrigger.object)
                    ) AND
                    SentinelSuit.guild_id = :guild_id AND 
                    SentinelSuit.enabled = 1 AND
                    sentinel_enabled = 1
                ORDER BY sentinel_name DESC
            ),
            sentinel_suit_info AS (
                SELECT
                    sentinel_name,
                    (abs(random()) / 9223372036854775807.0) AS r_val,
                    SUM(weight) AS t_weight
                FROM triggered_suits
                GROUP BY sentinel_name
            ),
            cumulative_probabilities AS (
                SELECT
                    suits.sentinel_name,
                    name,
                    (weight / (t_weight * 1.0)) AS prob,
                    sum((weight / (t_weight * 1.0))) OVER (PARTITION BY suits.sentinel_name ORDER BY name) AS c_prob
                FROM triggered_suits AS suits
                LEFT JOIN sentinel_suit_info AS sentinel_info ON 
                    sentinel_info.sentinel_name = suits.sentinel_name
                ORDER BY suits.sentinel_name
            ),
            selected_suits AS (
                SELECT 
                    suits.guild_id,
                    suits.sentinel_name,
                    suits.name,
                    weight,
                    trigger_id,
                    response_id,
                    enabled
                FROM triggered_suits AS suits
                LEFT JOIN sentinel_suit_info AS sentinel_info ON 
                    sentinel_info.sentinel_name = suits.sentinel_name
                LEFT JOIN cumulative_probabilities AS c_probs ON 
                    c_probs.sentinel_name = suits.sentinel_name AND
                    c_probs.name = suits.name
                WHERE c_prob >= r_val
                GROUP BY suits.sentinel_name
            )
            SELECT
                *
            FROM selected_suits;
            """
            GET_RANDOM_RESPONSE_SUIT = """
            with null_trigger_suits AS (
                SELECT
                    *
                FROM SentinelSuit
                WHERE
                    trigger_id ISNULL AND
                    sentinel_name = :sentinel_name AND
                    enabled = 1
            ),
            c_probs AS (
                SELECT
                    name,
                    (weight / ((SELECT SUM(weight) FROM null_trigger_suits)  * 1.0)) AS prob,
                    sum( weight / ( (SELECT SUM(weight) FROM null_trigger_suits) * 1.0 ) ) OVER (ORDER BY name) AS c_prob
                FROM null_trigger_suits
            )
            SELECT
                guild_id,
                suits.sentinel_name,
                suits.name,
                weight,
                trigger_id,
                response_id,
                enabled
            FROM null_trigger_suits AS suits
            INNER JOIN c_probs ON
                c_probs.name = suits.name
            WHERE c_prob >= (abs(random()) / 9223372036854775807.0)
            LIMIT 1
            """
            GET_SUITS_FROM_REACTION = f"""
            WITH triggered_suits AS (
                SELECT
                    SentinelSuit.guild_id,
                    SentinelSuit.sentinel_name,
                    SentinelSuit.name,
                    weight,
                    trigger_id,
                    response_id,
                    SentinelSuit.enabled,
                    Sentinel.enabled AS sentinel_enabled
                FROM SentinelSuit
                LEFT JOIN SentinelTrigger ON 
                    SentinelTrigger.id = SentinelSuit.trigger_id 
                LEFT JOIN Sentinel ON 
                    Sentinel.name = SentinelSuit.sentinel_name
                WHERE 
                    SentinelTrigger.type = 4 AND SentinelTrigger.object = :reaction_str AND
                    SentinelSuit.guild_id = :guild_id AND 
                    SentinelSuit.enabled = 1 AND
                    sentinel_enabled = 1
                ORDER BY sentinel_name DESC
            ),
            sentinel_suit_info AS (
                SELECT
                    sentinel_name,
                    (abs(random()) / 9223372036854775807.0) AS r_val,
                    SUM(weight) AS t_weight
                FROM triggered_suits
                GROUP BY sentinel_name
            ),
            cumulative_probabilities AS (
                SELECT
                    suits.sentinel_name,
                    name,
                    (weight / (t_weight * 1.0)) AS prob,
                    sum((weight / (t_weight * 1.0))) OVER (PARTITION BY suits.sentinel_name ORDER BY name) AS c_prob
                FROM triggered_suits AS suits
                LEFT JOIN sentinel_suit_info AS sentinel_info ON 
                    sentinel_info.sentinel_name = suits.sentinel_name
                ORDER BY suits.sentinel_name
            ),
            selected_suits AS (
                SELECT 
                    suits.guild_id,
                    suits.sentinel_name,
                    suits.name,
                    weight,
                    trigger_id,
                    response_id,
                    enabled
                FROM triggered_suits AS suits
                LEFT JOIN sentinel_suit_info AS sentinel_info ON 
                    sentinel_info.sentinel_name = suits.sentinel_name
                LEFT JOIN cumulative_probabilities AS c_probs ON 
                    c_probs.sentinel_name = suits.sentinel_name AND
                    c_probs.name = suits.name
                WHERE c_prob >= r_val
                GROUP BY suits.sentinel_name
            )
            SELECT
                *
            FROM selected_suits;
            """

    # These dataclasses are from past attempts at a tracking implementation
    # They are stored here as future reference for their triggers
    @dataclass
    class _SentinelSuitUses(Database.Row):
        class SuitPart(IntEnum):
            trigger = 0
            response = 1
        guild_id: int
        sentinel_name: str
        suit_name: str
        suit_part: SuitPart
        user_id: int
        uses: int
        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS SentinelSuitUses(
            guild_id INTEGER NOT NULL,
            sentinel_name TEXT NOT NULL,
            suit_name TEXT NOT NULL,
            suit_part INT NOT NULL
            )
            """


        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS SentinelTriggerUses(
        guild_id INTEGER NOT NULL,
        sentinel_name TEXT NOT NULL,
        suit_name TEXT NOT NULL,
        UNIQUE (guild_id, trigger_type, trigger_object, user_id),
        FOREIGN KEY(guild_id) REFERENCES Guild(id)
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(user_id) REFERENCES User(id)
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS SentinelTriggerUses
        """
        TRIGGER_BEFORE_INSERT_USER = """
        CREATE TRIGGER IF NOT EXISTS insert_user_before_insert
        BEFORE INSERT ON SentinelTriggerUses
        BEGIN
            INSERT INTO User(id)
            VALUES(NEW.user_id)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_INSERT = """
        INSERT INTO SentinelTriggerUses(guild_id, trigger_object, user_id)
        VALUES(:guild_id, :trigger_object, :user_id)
        ON CONFLICT DO NOTHING
        """
        QUERY_UPSERT = """
        INSERT INTO SentinelTriggerUses(guild_id, trigger_object, user_id)
        VALUES(:guild_id, :trigger_object, :user_id)
        ON CONFLICT(guild_id, trigger_object, user_id)
        DO UPDATE SET uses = uses + 1
        """

    @dataclass
    class _SentinelResponseUses(Database.Row):
        guild_id: str
        response_type: int
        response_content: str
        user_id: int
        uses: int
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS SentinelTriggerUses(
        guild_id INTEGER NOT NULL,
        trigger_type INTEGER NOT NULL,
        trigger_object TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        uses INTEGER DEFAULT 0,
        UNIQUE (guild_id, trigger_type, trigger_object, user_id),
        FOREIGN KEY(guild_id) REFERENCES Guild(id)
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(user_id) REFERENCES User(id)
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS SentinelTriggerUses
        """
        TRIGGER_BEFORE_INSERT_USER = """
        CREATE TRIGGER IF NOT EXISTS insert_user_before_insert
        BEFORE INSERT ON SentinelTriggerUses
        BEGIN
            INSERT OR IGNORE INTO User(id)
            VALUES(NEW.user_id);
        END
        """
        QUERY_INSERT = """
        INSERT INTO SentinelTriggerUses(guild_id, trigger_object, user_id)
        VALUES(:guild_id, :trigger_object, :user_id)
        ON CONFLICT DO NOTHING
        """
        QUERY_UPSERT = """
        INSERT INTO SentinelTriggerUses(guild_id, trigger_object, user_id)
        VALUES(:guild_id, :trigger_object, :user_id)
        ON CONFLICT(guild_id, trigger_object, user_id)
        DO UPDATE SET uses = uses + 1
        """

    class SuitHasTrigger(errors.CustomCheck):
        MESSAGE = "The specific suit already has a trigger"

    class SuitHasResponse(errors.CustomCheck):
        MESSAGE = "The specific suit already has a response"

    class SuitDoesNotExist(errors.CustomCheck):
        MESSAGE = "The specific suit does not exist"

    class SentinelDoesNotExist(errors.CustomCheck):
        MESSAGE = "The specific sentinel does not exist"

    class InvalidRegex(errors.CustomCheck):
        MESSAGE = "The entered regex is not valid"

    async def upsertSentinelSettings(self, sentinel_settings: SentinelSettings):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelSettings.Queries.UPSERT, sentinel_settings.asdict())
            await db.commit()

    async def fetchSentinelSettings(self, guild_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.SentinelSettings.rowFactory
            result = await db.execute_fetchall(SentinelDB.SentinelSettings.Queries.SELECT, (guild_id,))
            return result[0][0] if result else None
    async def insertSentinel(self, sentinel: Sentinel) -> bool:
        async with aiosqlite.connect(self.file_path) as db:
            cursor = await db.execute(SentinelDB.Sentinel.Queries.INSERT, sentinel.asdict())
            row_count = cursor.rowcount
            await db.commit()
        return row_count > 0

    async def insertTrigger(self, trigger: SentinelTrigger) -> int:
        async with aiosqlite.connect(self.file_path) as db:
            result = await db.execute_fetchall(SentinelDB.SentinelTrigger.Queries.INSERT, trigger.asdict())
            if len(result) == 0:
                result = await db.execute_fetchall(SentinelDB.SentinelTrigger.Queries.SELECT_ID,
                                                   (trigger.type, trigger.object))
            # cursor = await db.execute(SentinelDB.SentinelTrigger.Queries.INSERT, trigger.asdict())
            # await db.execute(SentinelDB.SentinelTrigger.Queries.INSERT, trigger.asdict())
            await db.commit()
        if result:
            trigger_id = result[0][0]
        else:
            raise aiosqlite.OperationalError("New row not created despite lack of existing row")
        return trigger_id

    async def insertTriggers(self, triggers: list[SentinelTrigger]):
        async with aiosqlite.connect(self.file_path) as db:
            data = [trigger.asdict() for trigger in triggers]
            await db.executemany(SentinelDB.SentinelTrigger.Queries.INSERT, data)
            await db.commit()

    async def insertResponse(self, response: SentinelResponse) -> int:
        async with aiosqlite.connect(self.file_path) as db:
            # rowid = await db.execute_insert(SentinelDB.SentinelResponse.Queries.INSERT, response.asdict())
            result: list = await db.execute_fetchall(SentinelDB.SentinelResponse.Queries.INSERT, response.asdict())
            if len(result) == 0:
                result = await db.execute_fetchall(SentinelDB.SentinelResponse.Queries.SELECT_ID,
                                                   (response.type, response.content, response.reactions))
            # await db.execute(SentinelDB.SentinelResponse.Queries.INSERT, response.asdict())
            await db.commit()
        if len(result):
            response_id = result[0][0]
        else:
            raise aiosqlite.OperationalError("New row not created despite lack of existing row")
        return response_id

    async def insertResponses(self, responses: list[SentinelResponse]):
        async with aiosqlite.connect(self.file_path) as db:
            data = [response.asdict() for response in responses]
            await db.executemany(SentinelDB.SentinelResponse.Queries.INSERT, data)
            await db.commit()

    async def insertSuit(self, suit: SentinelSuit):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelSuit.Queries.INSERT, suit.asdict())
            await db.commit()

    async def upsertSuit(self, suit: SentinelSuit):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelSuit.Queries.UPSERT, suit.asdict())
            await db.commit()

    async def updateSuit(self, suit: SentinelSuit):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelSuit.Queries.UPDATE, suit.asdict())
            await db.commit()

    async def deleteSuit(self, suit: SentinelSuit):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelSuit.Queries.DELETE, (suit.guild_id, suit.sentinel_name, suit.name))
            await db.commit()

    async def insertSuitPair(self, guild_id: int, sentinel_name: str, name: str, trigger: SentinelTrigger=None, response: SentinelResponse=None, weight=None):
        async with aiosqlite.connect(self.file_path) as db:
            trigger_id = 0
            response_id = 0
            # Just trust me bro, these queries return an integer but due to the fetchall it is a list of rows
            # since rows are just tuples I am accessing the first (and only) element
            if trigger:
                result: list = await db.execute_fetchall(SentinelDB.SentinelTrigger.Queries.INSERT, trigger.asdict())
                trigger_id = result[0][0] if result else None
            if response:
                result: list = await db.execute_fetchall(SentinelDB.SentinelResponse.Queries.INSERT, response.asdict())
                response_id = result[0][0] if result else None
            suit = SentinelDB.SentinelSuit(guild_id=guild_id, sentinel_name=sentinel_name, name=name,
                                           trigger_id=trigger_id, response_id=response_id,
                                           weight=weight)
            await db.execute(SentinelDB.SentinelSuit.Queries.INSERT, suit.asdict())
            await db.commit()
        # print(f"{trigger_id=}, {response_id=}")

    async def fetchSentinel(self, guild_id: int, name: str) -> Sentinel:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.Sentinel.rowFactory
            result: list[SentinelDB.Sentinel] = await db.execute_fetchall(SentinelDB.Sentinel.Queries.SELECT,
                                                                          (guild_id, name))
        return result[0] if result else None

    async def fetchSimilarSentinelNames(self, guild_id: int, name: str, limit: int=1, offset: int=0):
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(SentinelDB.Sentinel.Queries.SELECT_LIKE_NAMES,
                                                         (guild_id, f"%{name}%", limit, offset))
            names = [n[0] for n in names]
        return names

    async def fetchSentinelSuit(self, guild_id: int, sentinel_name: str, name: str) -> SentinelSuit:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.SentinelSuit.rowFactory
            result = await db.execute_fetchall(SentinelDB.SentinelSuit.Queries.SELECT, (guild_id, sentinel_name, name))
        return result[0] if result else None

    async def fetchSimilarSuitNames(self, guild_id: int, sentinel_name: str, name: str,
                                    limit: int=1, offset: int=0):
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(
                SentinelDB.SentinelSuit.Queries.SELECT_SIMILAR_SUIT_NAMES,
                (guild_id, sentinel_name, f"%{name}%", limit, offset))
            names = [n[0] for n in names]
        return names

    async def fetchSimilarNullTriggerSuitNames(self, guild_id: int, sentinel_name: str, name: str,
                                               limit: int=1, offset: int=0):
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(
                SentinelDB.SentinelSuit.Queries.SELECT_SIMILAR_NULL_TRIGGER_SUIT_NAMES,
                (guild_id, sentinel_name, f"%{name}%", limit, offset))
            names = [n[0] for n in names]
        return names

    async def fetchSimilarNullResponseSuitNames(self, guild_id: int, sentinel_name: str, name: str,
                                                limit: int=1, offset: int=0):
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(
                SentinelDB.SentinelSuit.Queries.SELECT_SIMILAR_NULL_RESPONSE_SUIT_NAMES,
                (guild_id, sentinel_name, f"%{name}%", limit, offset))
            names = [n[0] for n in names]
        return names

    async def getMatchingSuitsFromMessage(self, guild_id: int, message_content: str) -> list[SentinelSuit]:
        async with aiosqlite.connect(self.file_path) as db:
            def regexp(pattern, string):
                if string is None:
                    return False
                return re.search(pattern, string) is not None
            await db.create_function("REGEXP", 2, regexp)
            db.row_factory = SentinelDB.SentinelSuit.rowFactory
            params = {"guild_id": guild_id, "message_content": message_content}
            async with db.execute(SentinelDB.SentinelSuit.Queries.GET_SUITS_FROM_MESSAGE, params) as cur:
                suit: SentinelDB.SentinelSuit
                return await cur.fetchall()

    async def getMatchingSuitsFromReaction(self, guild_id: int, reaction_str: str) -> list[SentinelSuit]:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.SentinelSuit.rowFactory
            params = {"guild_id": guild_id, "reaction_str": reaction_str}
            async with db.execute(SentinelDB.SentinelSuit.Queries.GET_SUITS_FROM_REACTION, params) as cur:
                suit: SentinelDB.SentinelSuit
                return await cur.fetchall()

    async def getWeightedRandomResponseSuit(self, guild_id: int, sentinel_name: str) -> SentinelSuit:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.SentinelSuit.rowFactory
            params = {"guild_id": guild_id, "sentinel_name": sentinel_name}
            async with db.execute(SentinelDB.SentinelSuit.Queries.GET_RANDOM_RESPONSE_SUIT, params) as cur:
                suit: SentinelDB.SentinelSuit = await cur.fetchone()
                return suit

    async def fetchResponse(self, response_id) -> SentinelResponse:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.SentinelResponse.rowFactory
            async with db.execute(SentinelDB.SentinelResponse.Queries.SELECT_RESPONSE, (response_id,)) as cur:
                return await cur.fetchone()

    async def toggleSentinel(self, sentinel: Sentinel):
        async with aiosqlite.connect(self.file_path) as db:
            cur = await db.execute(SentinelDB.Sentinel.Queries.TOGGLE, )
            await db.commit()

    async def toggleSuit(self, suit: SentinelSuit):
        async with aiosqlite.connect(self.file_path) as db:
            cur = await db.execute(SentinelDB.SentinelSuit.Queries.TOGGLE)
            await db.commit()

    async def toggleChannel(self, guild_id: int, channel_id: int) -> bool:
        """Returns a boolean where True corresponds to sentinels being enabled on the channel"""
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = lambda row: row[0]
            params = {"guild_id": guild_id, "channel_id": channel_id}
            cur = await db.execute(SentinelDB.DisabledSentinelChannels.Queries.SELECT_EXISTS, params)
            disabled = bool(await cur.fetchone())
            if disabled:
                await db.execute(SentinelDB.DisabledSentinelChannels.Queries.DELETE, params)
            else:
                await db.execute(SentinelDB.DisabledSentinelChannels.Queries.INSERT, params)
            await db.commit()
        return disabled # by this point the state has been flipped

    async def disableChannel(self, guild_id: int, channel_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            params = {"guild_id": guild_id, "channel_id": channel_id}
            await db.execute(SentinelDB.DisabledSentinelChannels.Queries.INSERT, params)
            await db.commit()

    async def enableChannel(self, guild_id: int, channel_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            params = {"guild_id": guild_id, "channel_id": channel_id}
            await db.execute(SentinelDB.DisabledSentinelChannels.Queries.DELETE, params)
            await db.commit()

    async def getTriggerIds(self, message_content: str):
        async with aiosqlite.connect(self.file_path) as db:
            result: list[int] = await db.execute_fetchall("""
            SELECT id FROM SentinelTrigger WHERE object
            """)

    async def getPhraseTriggers(self, message_content: str):
        async with aiosqlite.connect(self.file_path) as db:
            query = """
            SELECT id FROM SentinelTrigger WHERE type = ?
            AND instr(?, object)
            """
            phrase = SentinelDB.SentinelTrigger.TriggerType.phrase
            async with db.execute(query, (2, message_content)) as cur:
                ids = await cur.fetchall()
                return ids

    async def getWordTriggers(self, message_content: str):
        async with aiosqlite.connect(self.file_path) as db:
            def regexp(pattern, string):
                if string is None:
                    return False
                return re.search(pattern, string) is not None

            await db.create_function("REGEXP", 2, regexp)
            regex = f"[,.;:'\"?!@#$%^&*()~`+=|/\\ ]"
            regex = regex.replace("'", "''") # escapes the single quotes by replacing theme with double quotes
            query = f"""
            SELECT id FROM SentinelTrigger WHERE type = ?
            AND ' '||?||' ' REGEXP '{regex}'||object||'{regex}'
            """
            async with db.execute(query, (2, message_content)) as cur:
                ids = await cur.fetchall()
                return ids

    async def getSuits(self, guild_id: int, message_content: str):
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.SentinelSuit.rowFactory
            cur: aiosqlite.Cursor = await db.execute("""
            SELECT * FROM SentinelSuit
            WHERE guild_id = :guild_id 
            AND trigger_id = (SELECT id FROM SentinelTrigger WHERE object = :trigger_object)
            """)
            pass


    async def suitGeneratorFromTrigger(self, guild_id, trigger_object: str):
        async with aiosqlite.connect(self.file_path) as db:
            id_query = SentinelDB.SentinelTrigger.Queries.SELECT_IDS
            suit_query = SentinelDB.SentinelSuit.Queries.SELECT_FROM_TRIGGER_ID

            async with db.execute(id_query, (trigger_object,)) as cursor:
                async for row in cursor:
                    trigger_id = row[0][0]


            db.row_factory = SentinelDB.SentinelSuit
            cur = await db.execute()
            yield ..., ..., ...
        # Test to see if output is what is expected


class SentinelScope(IntEnum):
    """
    Since this is an int enum is can be multiplied by a guild id
    if scope = 0 then guild id = 0
    otherwise for 1 it isn't 0
    This is always going to be binary, if not urgently fix everything that uses the multiplication method
    """
    GLOBAL = 0
    LOCAL = 1


class GuildTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           current: str) -> list[Choice[str]]:
        user = interaction.user
        guilds = list(user.mutual_guilds)
        choices = [Choice(name=guild.name, value=str(guild.id)) for guild in guilds
                   if current.lower() in guild.name.lower()][:25]
        return choices

    async def transform(self, interaction: Interaction,
                        value: str, /) -> discord.Guild:
        guild_id = int(value)
        guild = interaction.client.get_guild(guild_id)
        return guild


class SentinelTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           current: str, /) -> list[Choice[str]]:
        guild_id = interaction.namespace.scope
        if guild_id == SentinelScope.LOCAL:
            guild_id = interaction.guild_id
        bot: Kagami = interaction.client
        db = SentinelDB(bot.config.db_path)
        names = await db.fetchSimilarSentinelNames(guild_id=guild_id,
                                                   name=current,
                                                   limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction,
                        value: str, /) -> discord.Guild:
        await respond(interaction)
        guild_id = interaction.namespace.scope
        if guild_id == 1: guild_id = interaction.guild_id
        bot: Kagami = interaction.client
        db = SentinelDB(bot.config.db_path)
        return await db.fetchSentinel(guild_id=guild_id, name=value)


class SentinelSuitTransformer(Transformer):
    def __init__(self, empty_field: Literal["trigger_id", "response_id"]=None):
        self.empty_field = empty_field

    async def autocomplete(self, interaction: Interaction,
                           current: str, /) -> List[Choice[str]]:
        guild_id = interaction.namespace.scope
        if guild_id == SentinelScope.LOCAL: guild_id = interaction.guild_id
        sentinel_name = interaction.namespace.sentinel
        bot: Kagami = interaction.client
        db = SentinelDB(bot.config.db_path)
        if self.empty_field == "trigger_id":
            names = await db.fetchSimilarNullTriggerSuitNames(guild_id, sentinel_name, current, limit=25)
        elif self.empty_field == "response_id":
            names = await db.fetchSimilarNullResponseSuitNames(guild_id, sentinel_name, current, limit=25)
        else:
            names = await db.fetchSimilarSuitNames(guild_id, sentinel_name, current, limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction, value: str, /) -> SentinelDB.SentinelSuit:
        await respond(interaction)
        guild_id = interaction.namespace.scope
        if guild_id == 1: guild_id = interaction.guild_id
        bot: Kagami = interaction.client
        db = SentinelDB(bot.config.db_path)
        sentinel_name = interaction.namespace.sentinel
        result = await db.fetchSentinelSuit(guild_id, sentinel_name, value)

        if result:
            if self.empty_field == "trigger_id" and result.trigger_id is not None:
                raise SentinelDB.SuitHasTrigger
            elif self.empty_field == "response_id" and result.response_id is not None:
                raise SentinelDB.SuitHasResponse

        return result


async def triggerSanityCheck(trigger_type: SentinelDB.SentinelTrigger.TriggerType,
                             trigger_object: str) -> bool:
    raise NotImplementedError


async def triggerSanitizer(trigger_type: SentinelDB.SentinelTrigger.TriggerType,
                           trigger_object: str) -> tuple[SentinelDB.SentinelTrigger.TriggerType, str]:
    raise NotImplementedError


async def responseSanityCheck(response_type: SentinelDB.SentinelResponse.ResponseType,
                              content: str, reactions: str) -> bool:
    raise NotImplementedError


async def responseSanitizer(response_type: SentinelDB.SentinelResponse.ResponseType,
                            content: str,
                            reactions: str) -> tuple[SentinelDB.SentinelResponse.ResponseType, str, str]:
    raise NotImplementedError


class Sentinels(GroupCog, name="s"):
    def __init__(self, bot: Kagami):
        self.bot: Kagami = bot
        self.config = bot.config
        self.database = SentinelDB(bot.config.db_path)

    async def cog_load(self) -> None:
        await self.database.init(drop=self.config.drop_tables)
        # await self.database.init(drop=True)
        if self.bot.config.migrate_data: await self.migrateData()
        # pass

    async def cog_unload(self) -> None:
        pass

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        return True

    add_group = Group(name="add", description="commands for adding sentinel components")
    remove_group = Group(name="remove", description="commands for removing sentinel components")
    edit_group = Group(name="edit", description="commands for editing sentinel components")
    view_group = Group(name="view", description="commands for viewing sentinel information")
    toggle_group = Group(name="toggle", description="commands for toggling sentinel components")
    enable_group = Group(name="enable", description="commands for enabling sentinel components")
    disable_group = Group(name="disable", description="commands for disabling sentinel components")

    Guild_Transform = Transform[InfoDB.Guild, GuildTransformer]
    Sentinel_Transform = Transform[SentinelDB.Sentinel, SentinelTransformer]
    SuitNullTrigger_Transform = Transform[SentinelDB.SentinelSuit, SentinelSuitTransformer(empty_field="trigger_id")]
    SuitNullResponse_Transform = Transform[SentinelDB.SentinelSuit, SentinelSuitTransformer(empty_field="response_id")]
    Suit_Transform = Transform[SentinelDB.SentinelSuit, SentinelSuitTransformer]

    @dataclass
    class SentinelPayload:
        content: str
        user_id: int
        guild_id: int
        channel_id: int
        type: Literal["message", "reaction"]

    @dataclass
    class SentinelEvent:
        type: Literal["message", "reaction"]
        content: str
        user: discord.User
        guild: discord.Guild
        channel: discord.TextChannel

    async def onSentinelEvent(self, event: SentinelEvent):
        guild_settings = await self.database.fetchSentinelSettings(event.guild.id)
        global_settings = await self.database.fetchSentinelSettings(0)
        if event.type == "message":
            # iterate through every suit that have their trigger match
            # the queries should return suits one by one that would be triggered by the message
            # the content will be passed along with the guild_id to a generator function
            # a return suit should only have a specific sentinel for a guild once

            # potential methods
            # method 1: iterate through all suits for each sentinel on a guild
            # check each of their triggers and note the suits that triggered
            # either pick at random or decide based off trigger weight which suit is activated
            # then determine the response based off of weight if there isn't a paired response
            # phrase: check if object in content
            # word: check if object in content split by spaces
            # regex: just match the regex to the content
            pass
        elif event.type == "reaction":
            # take the reaction string and find a suit with that trigger
            pass

        lower = event.content.lower()

    async def getSentinel(self, trigger_object: str):
        # check each sentinel for a trigger that procs on the message
        # each sentinel should only give one response even if it has multiple triggers proc
        # then if the trigger is parts of a suit, give the suit response
        # if there is not a paired response then pick any response that doesn't have a paired trigger


        pass

    async def getResponsesForMessage(self, guild_id: int, content: str) -> list[SentinelDB.SentinelResponse]:
        triggered_suits: list[SentinelDB.SentinelSuit]
        triggered_suits = await self.database.getMatchingSuitsFromMessage(guild_id, content)
        responses = []
        for suit in triggered_suits:
            response_id = suit.response_id
            if not response_id:
                suit = await self.database.getWeightedRandomResponseSuit(guild_id, suit.sentinel_name)
                if not suit: continue
                response_id = suit.response_id
            response: SentinelDB.SentinelResponse = await self.database.fetchResponse(response_id)
            responses += [response]
        return responses

    async def getResponsesForReaction(self, guild_id: int, reaction: discord.Reaction):
        reaction_str = str(reaction)
        triggered_suits: list[SentinelDB.SentinelSuit]
        triggered_suits = await self.database.getMatchingSuitsFromReaction(guild_id, reaction_str)
        responses = []
        for suit in triggered_suits:
            response_id = suit.response_id
            if not response_id:
                suit = await self.database.getWeightedRandomResponseSuit(guild_id, suit.sentinel_name)
                if not suit: continue
                response_id = suit.response_id
            response: SentinelDB.SentinelResponse = await self.database.fetchResponse(response_id)
            responses += [response]
        return responses

    async def handleResponses(self, original_message: discord.Message, responses):
        for response in responses:
            if len(response.content) > 0:
                if response.type == response.ResponseType.message:
                    await original_message.channel.send(content=response.content)
                elif response.type == response.ResponseType.reply:
                    await original_message.reply(content=response.content)
            if len(response.reactions) > 0:
                for reaction in response.reactions.split(";"):
                    partial_emoji = discord.PartialEmoji.from_str(reaction.strip())
                    await original_message.add_reaction(partial_emoji)




    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return

        responses = await self.getResponsesForMessage(message.guild.id, message.content)
        global_responses = await self.getResponsesForMessage(0, message.content)
        await self.handleResponses(message, responses)
        await self.handleResponses(message, global_responses)


    # @commands.Cog.listener()
    # async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member):
    #     if user.id == self.bot.user.id:
    #         return
    #     responses = await self.getResponsesForReaction(reaction.message.guild.id, reaction)
    #     global_responses = await self.getResponsesForReaction(0, reaction)
    #     await self.handleResponses(reaction.message, responses)
    #     await self.handleResponses(reaction.message, global_responses)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, event: discord.RawReactionActionEvent):
        if event.user_id == self.bot.user.id:
            return
        responses = await self.getResponsesForReaction(guild_id=event.guild_id, reaction=event.emoji)
        global_responses = await self.getResponsesForReaction(guild_id=0, reaction=event.emoji)
        channel = await self.bot.fetch_channel(event.channel_id)
        message = await channel.fetch_message(event.message_id)
        await self.handleResponses(message, responses)
        await self.handleResponses(message, global_responses)

    @commands.is_owner()
    @commands.command(name="migrate_sentinels")
    async def migrateCommand(self, ctx):
        await self.migrateData()
        await ctx.send("Migrated sentinel data")

    @commands.is_owner()
    @commands.command(name="gpti")
    async def getPhraseTriggerIDS(self, ctx: commands.Context, *, message: str):
        ids = await self.database.getPhraseTriggers(message_content=message)
        await ctx.send(f"message: {message}, {ids}")

    @commands.is_owner()
    @commands.command(name="gwti")
    async def getWordTriggerIDS(self, ctx: commands.Context, *, message: str):
        ids = await self.database.getWordTriggers(message_content=message)
        await ctx.send(f"message: {message} : {ids}")


    async def migrateData(self):
        """
        Old Sentinels are triggered by their name being present as a phrase in the message
        They have a separate response parameter
        data migration missing usage numbers
        upsert into the usage table for each as well
        """
        async def convertSentinel(_guild_id: int, _sentinel_name: str,  _sentinel: OldSentinel
                                  ) -> tuple[SentinelDB.SentinelTrigger, SentinelDB.SentinelResponse]:

            _trigger = SentinelDB.SentinelTrigger(type=SentinelDB.SentinelTrigger.TriggerType.phrase,
                                                  object=_sentinel_name)
            reactions = ";".join(_sentinel.reactions)
            _response = SentinelDB.SentinelResponse(type=SentinelDB.SentinelResponse.ResponseType.reply,
                                                    content=_sentinel.response, reactions=reactions)
            # _uses = SentinelDB.SentinelTriggerUses(guild_id=_guild_id, trigger_object=)

            return _trigger, _response

        for server_id, server in self.bot.data.servers.items():
            server_id = int(server_id)
            try: guild = await self.bot.fetch_guild(server_id)
            except discord.NotFound: continue
            converted_sentinels = [await convertSentinel(server_id, name, sentinel)
                                   for name, sentinel in server.sentinels.items()]
            if len(converted_sentinels):
                triggers, responses = zip(*converted_sentinels)
                for trigger, response in converted_sentinels:
                    trigger_id = await self.database.insertTrigger(trigger)
                    response_id = await self.database.insertResponse(response)
                    suit = SentinelDB.SentinelSuit(guild_id=server_id, sentinel_name=trigger.object, name=trigger.object,
                                                   trigger_id=trigger_id, response_id=response_id)
                    await self.database.insertSuit(suit)
                # await self.database.insertTriggers(triggers)
                # await self.database.insertResponses(responses)

        converted_sentinels = [await convertSentinel(0, name, sentinel)
                               for name, sentinel in self.bot.data.globals.sentinels.items()]
        if len(converted_sentinels):
            for trigger, response in converted_sentinels:
                trigger_id = await self.database.insertTrigger(trigger)
                response_id = await self.database.insertResponse(response)
                suit = SentinelDB.SentinelSuit(guild_id=0, sentinel_name=trigger.object, name=trigger.object,
                                               trigger_id=trigger_id, response_id=response_id)
                await self.database.insertSuit(suit)
                #
                # await self.database.insertSuitPair(guild_id=0, sentinel_name=trigger.object, name=trigger.object,
                #                                    trigger=trigger, response=response, weight=10)
            # await self.database.insertTriggers(triggers)
            # await self.database.insertResponses(responses)

    def validate_regex(self, regex: str) -> bool:
        pass

    # App Command
    @app_commands.rename(trigger_type="type", trigger_object="object")
    @add_group.command(name="trigger", description="add a sentinel trigger")
    async def add_trigger(self, interaction: Interaction, scope: SentinelScope,
                          sentinel: Sentinel_Transform, suit: SuitNullTrigger_Transform,
                          trigger_type: SentinelDB.SentinelTrigger.TriggerType, trigger_object: str,
                          weight: int=100):
        await respond(interaction)
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        if trigger_type == 3:
            try:
                re.compile(trigger_object)
            except re.error:
                raise SentinelDB.InvalidRegex
        # guild_id = scope * interaction.guild_id
        trigger = SentinelDB.SentinelTrigger(type=trigger_type, object=trigger_object)
        trigger_id = await self.database.insertTrigger(trigger)
        if suit:
            # if suit.trigger_id: raise SentinelDB.SuitHasTrigger
            # else:
            suit.trigger_id = trigger_id
        else:
            suit = SentinelDB.SentinelSuit(guild_id, sentinel_name=interaction.namespace.sentinel,
                                           name=interaction.namespace.suit, trigger_id=trigger_id,
                                           weight=weight)
        await self.database.upsertSuit(suit)
        await respond(interaction, f"Added a trigger to the suit `{suit.name}` for sentinel `{suit.sentinel_name}`")
        # await self.database.insertTrigger(trigger)
        # await respond(interaction, f"Added a trigger to the sentinel `{interaction.namespace.sentinel}`")

    @app_commands.rename(response_type="type")
    @app_commands.describe(reactions="emotes separated by semicolon ( ; )")
    @add_group.command(name="response", description="add a sentinel response")
    async def add_response(self, interaction: Interaction, scope: SentinelScope,
                           sentinel: Sentinel_Transform, suit: SuitNullResponse_Transform,
                           response_type: SentinelDB.SentinelResponse.ResponseType,
                           content: str="", reactions: str="",
                           weight: int=100):
        await respond(interaction)
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        # guild_id = scope * interaction.guild_id
        response = SentinelDB.SentinelResponse(type=response_type, content=content, reactions=reactions)
        response_id = await self.database.insertResponse(response)
        if suit:
            # if suit.response_id: raise SentinelDB.SuitHasResponse
            # else:
            suit.response_id = response_id
        else:
            suit = SentinelDB.SentinelSuit(guild_id, sentinel_name=interaction.namespace.sentinel,
                                           name=interaction.namespace.suit, response_id=response_id,
                                           weight=weight)
        await self.database.upsertSuit(suit)
        await respond(interaction, f"Added a response to the suit `{suit.name}` for sentinel `{suit.sentinel_name}`")

    @remove_group.command(name="trigger", description="remove a trigger from a suit")
    async def remove_trigger(self, interaction: Interaction,
                             scope: SentinelScope, sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction)
        if sentinel is None: raise SentinelDB.SentinelDoesNotExist
        if suit is None: raise SentinelDB.SuitDoesNotExist
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        # set the trigger for the sentinel and suit to None
        suit.trigger_id = None
        trigger = await self.database.updateSuit(suit=suit)
        await respond(interaction, f"Removed trigger from suit `{suit.name}` for sentinel `{sentinel.name}`")

    @remove_group.command(name="response", description="remove a response from a suit")
    async def remove_response(self, interaction: Interaction,
                              scope: SentinelScope, sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction)
        if sentinel is None: raise SentinelDB.SentinelDoesNotExist
        if suit is None: raise SentinelDB.SuitDoesNotExist
        # set the response for the sentinel and suit to None
        suit.response_id = None
        response = await self.database.updateSuit(suit=suit)
        await respond(interaction, f"Removed response from suit `{suit.name}` for sentinel `{sentinel.name}`")

    @remove_group.command(name="suit", description="remove a trigger-response pairing from a sentinel")
    async def remove_suit(self, interaction: Interaction,
                          scope: SentinelScope, sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction)
        if sentinel is None: raise SentinelDB.SentinelDoesNotExist
        if suit is None: raise SentinelDB.SuitDoesNotExist
        await self.database.deleteSuit(suit)
        await respond(interaction, f"Remove the suit `{suit.name}` from sentinel `{sentinel.name}`")

    @edit_group.command(name="trigger", description="edit a suit's trigger")
    async def edit_trigger(self, interaction: Interaction, scope: SentinelScope,
                           sentinel: Sentinel_Transform, suit: Suit_Transform,
                           trigger_type: SentinelDB.SentinelTrigger.TriggerType=None, trigger_object: str=None,
                           weight: int=None):
        await respond(interaction)
        if sentinel is None: raise SentinelDB.SentinelDoesNotExist
        if suit is None: raise SentinelDB.SuitDoesNotExist
        if trigger_type == 3:
            try:
                re.compile(trigger_object)
            except re.error:
                raise SentinelDB.InvalidRegex

        if trigger_type and trigger_object:
            trigger = SentinelDB.SentinelTrigger(type=trigger_type, object=trigger_object)
            trigger_id = await self.database.insertTrigger(trigger)
            suit.trigger_id = trigger_id
        if weight is not None:
            suit.weight = weight
        await self.database.updateSuit(suit)
        await respond(interaction, f"Added edited a trigger on suit `{suit.name}` for sentinel `{suit.sentinel_name}`")

    @edit_group.command(name="response", description="edit a suit's response")
    async def edit_response(self, interaction: Interaction, scope: SentinelScope,
                            sentinel: Sentinel_Transform, suit: Suit_Transform,
                            response_type: SentinelDB.SentinelResponse.ResponseType=None,
                            content: str=None, reactions: str=None,
                            weight: int=None):
        await respond(interaction)
        if sentinel is None: raise SentinelDB.SentinelDoesNotExist
        if suit is None: raise SentinelDB.SuitDoesNotExist

        if response_type and (content or reactions):
            reactions = reactions or ""
            content = content or ""
            response = SentinelDB.SentinelResponse(type=response_type, content=content, reactions=reactions)
            response_id = await self.database.insertResponse(response)
            suit.response_id = response_id
        if weight is not None:
            suit.weight = weight
        await self.database.updateSuit(suit)
        await respond(interaction, f"Edited a response on suit `{suit.name}` for sentinel `{suit.sentinel_name}`")


    @toggle_group.command(name="suit", description="toggle an individual suit")
    async def toggle_suit(self, interaction: Interaction, scope: SentinelScope,
                          sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction)
        if sentinel is None: raise SentinelDB.SentinelDoesNotExist
        if suit is None: raise SentinelDB.SuitDoesNotExist
        await self.database.toggleSuit(suit)
        state = "enabled" if not suit.enabled else "disabled"
        await respond(interaction, f"The suit `{suit.name}` on sentinel `{sentinel.name}` is now `{state}`")

    @toggle_group.command(name="sentinel", description="toggle an entire sentinel")
    async def toggle_sentinel(self, interaction: Interaction, scope: SentinelScope,
                              sentinel: Sentinel_Transform):
        await respond(interaction)
        if sentinel is None: raise SentinelDB.SentinelDoesNotExist
        await self.database.toggleSentinel(sentinel)
        state = "enabled" if not sentinel.enabled else "disabled"
        await respond(interaction, f"The sentinel `{sentinel.name}` is now `{state}`")

    async def channel_autocomplete(self, interaction: Interaction, current: str) -> list[Choice[str]]:
        channels = interaction.guild.text_channels + interaction.guild.voice_channels
        options = [
              Choice(name=channel.name, value=str(channel.id))
              for channel in channels
              if current.lower() in channel.name.lower() or current == str(channel.id)
        ][:25]
        return options

    @toggle_group.command(name="channel", description="toggle all sentinels for a channel")
    # @app_commands.rename(channel_id="channel")
    # @autocomplete(channel_id=channel_autocomplete)
    async def toggle_channel(self, interaction: Interaction, channel: discord.TextChannel | discord.VoiceChannel=None, state: Literal["Enabled", "Disabled"]="Disabled", extent: Literal["all", "local", "global"]="all"):
        await respond(interaction)
        if channel is None:
            channel = interaction.channel
        state = state == "Enabled"
        state_str = "enabled" if state else "disabled"

        async def toggle(new_state: bool, guild_id):
            if new_state:
                await self.database.enableChannel(guild_id=guild_id, channel_id=channel.id)
            else:
                await self.database.disableChannel(guild_id=guild_id, channel_id=channel.id)

        if extent == "local":
            await toggle(new_state=state, guild_id=interaction.guild_id)
            await respond(interaction, content=f"Local sentinels are now `{state_str}` in `{channel.name}`")
        elif extent == "global":
            await toggle(new_state=state, guild_id=0)
            await respond(interaction, content=f"Global sentinels are now `{state_str}` in `{channel.name}`")
        else:
            await toggle(new_state=state, guild_id=interaction.guild_id)
            await toggle(new_state=state, guild_id=0)
            await respond(interaction, content=f"Local and Global sentinels are now `{state_str}` in `{channel.name}`")

    @enable_group.command(name="channel", description="enable all sentinels for a channel")
    async def enable_channel(self, interaction: Interaction, channel: discord.TextChannel | discord.VoiceChannel=None, extent: Literal["all", "local", "global"]="all"):
        await respond(interaction)
        if channel is None:
            channel = interaction.channel

        if extent == "local":
            await self.database.enableChannel(guild_id=interaction.guild_id, channel_id=channel.id)
            await respond(interaction, content=f"Local sentinels are now `enabled` in `{channel.name}`")
        elif extent == "global":
            await self.database.enableChannel(guild_id=0, channel_id=channel.id)
            await respond(interaction, content=f"Global sentinels are now `enabled` in `{channel.name}`")
        else:
            await self.database.enableChannel(guild_id=interaction.guild_id, channel_id=channel.id)
            await self.database.enableChannel(guild_id=0, channel_id=channel.id)
            await respond(interaction, content=f"Local and Global sentinels are now `enabled` in `{channel.name}`")

    @disable_group.command(name="channel", description="enable all sentinels for a channel")
    async def disable_channel(self, interaction: Interaction,
                              channel: discord.TextChannel | discord.VoiceChannel = None,
                              extent: Literal["all", "local", "global"] = "all"):
        await respond(interaction)
        if channel is None:
            channel = interaction.channel

        if extent == "local":
            await self.database.disableChannel(guild_id=interaction.guild_id, channel_id=channel.id)
            await respond(interaction, content=f"Local sentinels are now `disabled` in `{channel.name}`")
        elif extent == "global":
            await self.database.disableChannel(guild_id=0, channel_id=channel.id)
            await respond(interaction, content=f"Global sentinels are now `disabled` in `{channel.name}`")
        else:
            await self.database.disableChannel(guild_id=interaction.guild_id, channel_id=channel.id)
            await self.database.disableChannel(guild_id=0, channel_id=channel.id)
            await respond(interaction, content=f"Local and Global sentinels are now `disabled` in `{channel.name}`")


    @view_group.command(name="all", description="view all sentinels on a guild")
    async def view_all(self, interaction: Interaction):
        raise NotImplementedError

    @view_group.command(name="sentinel", description="view all suits in a sentinel")
    async def view_sentinel(self, interaction: Interaction):
        raise NotImplementedError

    @view_group.command(name="suit", description="view the trigger and response associated with a suit")
    async def view_suit(self, interaction: Interaction):
        raise NotImplementedError


async def setup(bot):
    await bot.add_cog(Sentinels(bot))

