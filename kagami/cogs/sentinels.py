import asyncio
from math import floor
import re
from dataclasses import dataclass
from enum import IntEnum

import aiosqlite
import discord
import discord.ui
from discord.ext import commands
from discord import app_commands, Interaction
from discord.ext.commands import GroupCog
from discord.app_commands import Transform, Transformer, Group, Choice
from common import errors
from bot import Kagami
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings
from common.paginator import Scroller, ScrollerState
from utils.depr_db_interface import Database
from common.utils import acstr
from typing import (
    Literal, List, Callable, Any, override
)

@dataclass
class SentinelSettings(Table, schema_version=1, trigger_version=1):
    guild_id: int
    local_enabled: bool = True
    global_enabled: bool = False
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SentinelSettings}(
            guild_id INTEGER NOT NULL,
            local_enabled INTEGER DEFAULT 1,
            global_enabled INTEGER DEFAULT 0,
            PRIMARY KEY(guild_id),
            FOREIGN KEY(guild_id) REFERENCES {Guild}(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        await db.execute(query)

    @classmethod
    async def insert_from_temp(cls, db: aiosqlite.Connection):
        await super().insert_from_temp(db)
        # query = f"""
        #     INSERT INTO {SentinelSettings}(guild_id)
        #     SELECT *
        #     FROM temp_{SentinelSettings}
        # """
        # await db.execute(query)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSettings}_insert_guild_before_insert
            BEFORE INSERT ON {SentinelSettings}
            BEGIN
                INSERT INTO Guild(id)
                VALUES (NEW.guild_id)
                ON CONFLICT(id) DO NOTHING;
            END;
            """, f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSettings}_set_global_defaults
            AFTER INSERT ON {SentinelSettings}
            FOR EACH ROW
            WHEN NEW.guild_id = 0
            BEGIN
                UPDATE {SentinelSettings}
                SET global_enabled = 1
                WHERE rowid = NEW.rowid;
            END;
            """
        ]
        for trigger in triggers:
            await db.execute(trigger)

    async def upsert(self, db: aiosqlite.Connection) -> "SentinelSettings":
        query = f"""
        INSERT INTO {SentinelSettings}(guild_id, local_enabled, global_enabled)
        VALUES(:guild_id, :local_enabled, :global_enabled)
        ON CONFLICT (guild_id)
        DO UPDATE SET 
            local_enabled = :local_enabled,
            global_enabled = :global_enabled
        RETURNING *
        """
        db.row_factory = SentinelSettings.row_factory
        async with db.execute(query, self.asdict()) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, guild_id: int) -> "SentinelSettings":
        query = f"""
        SELECT * FROM {SentinelSettings}
        WHERE guild_id = ?
        """
        db.row_factory = SentinelSettings.row_factory
        async with db.execute(query, (guild_id,)) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int) -> "SentinelSettings":
        query = """
        DELETE FROM SentinelSettings
        WHERE guild_id = ?
        RETURNING *
        """
        db.row_factory = SentinelSettings.row_factory
        async with db.execute(query, (guild_id,)) as cur:
            result = await cur.fetchone()
        return result

@dataclass
class Sentinel(Table, schema_version=1, trigger_version=1):
    guild_id: int
    name: str
    uses: int
    enabled: bool = True

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {Sentinel}(
        guild_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        uses INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1,
        PRIMARY KEY(guild_id, name),
        FOREIGN KEY(guild_id) REFERENCES {Sentinel}(guild_id) 
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        await db.execute(query)

    @classmethod
    async def insert_from_temp(cls, db: aiosqlite.Connection):
        # query = f"""
        # INSERT INTO {Sentinel}(guild_id, name, enabled)
        # SELECT guild_id, name, enabled 
        # FROM temp_{Sentinel}
        # """
        # await db.execute(query)
        await super().insert_from_temp(db)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        trigger = f"""
        CREATE TRIGGER IF NOT EXISTS {Sentinel}_insert_settings_before_insert
        BEFORE INSERT ON {Sentinel}
        BEGIN
            INSERT INTO {Sentinel}(guild_id)
            VALUES (NEW.guild_id)
            ON CONFLICT(guild_id) DO NOTHING;
        END;
        """
        await db.execute(trigger)

    async def insert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT OR IGNORE INTO {Sentinel}(guild_id, name)
        VALUES(:guild_id, :name)
        """
        await db.execute(query, self.asdict())

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "Sentinel":
        query = f"""
        DELETE FROM {Sentinel}
        WHERE guild_id = ? AND name = ?
        RETURNING *
        """
        db.row_factory = Sentinel.row_factory
        async with db.execute(query, (guild_id, name)) as cur:
            result = await cur.fetchone()
        return result

    async def delete(self, db: aiosqlite.Connection) -> "Sentinel":
        query = f"""
        DELETE FROM {Sentinel}
        WHERE guild_id = :guild_id AND name = :name
        RETURNING *
        """
        db.row_factory = Sentinel.row_factory
        async with db.execute(query, self.asdict()) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "Sentinel":
        query = f"""
        SELECT * FROM {Sentinel}
        WHERE guild_id = ? AND name = ?
        """
        db.row_factory = Sentinel.row_factory
        async with db.execute(query, (guild_id, name)) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectAllWhere(cls, db: aiosqlite.Connection, guild_id: int, limit: int=None, offset: int=0) -> list["Sentinel"]:
        query = f"""
        SELECT * FROM {Sentinel}
        WHERE guild_id = ?
        LIMIT ? OFFSET ?
        """
        db.row_factory = Sentinel.row_factory
        async with db.execute(query, (guild_id, limit, offset)) as cur:
            result = await cur.fetchall()
        return result

    @classmethod
    async def selectCountWhere(cls, db: aiosqlite.Connection, guild_id: int) -> int:
        query = f"""
        SELECT COUNT(*) FROM {Sentinel}
        WHERE guild_id = ?
        """
        db.row_factory = None
        async with db.execute(query, (guild_id,)) as cur:
            res = await cur.fetchone()
        return res[0] if res else 0

    @classmethod
    async def selectLikeNamesWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str, limit: int=None, offset: int=0):
        query = f"""
        SELECT name FROM {Sentinel}
        WHERE (guild_id = ?) AND (name LIKE ?)
        LIMIT ? OFFSET ?
        """
        db.row_factory = Sentinel.row_factory
        async with db.execute(query, (guild_id, f"%{name}%", limit, offset)) as cur:
            results = await cur.fetchall()
        return [n.name for n in results]
    
    @classmethod
    async def selectAllInfoWhere(cls, db: aiosqlite.Connection, guild_id: int, limit: int=None, offset: int=0) -> list["SentinelInfo"]:
        infos = await SentinelInfo.selectAllWhere(db, guild_id=guild_id, limit=limit, offset=offset)
        return infos
        # TODO Implement this with a new dataclass representing sentinel info
        # This should contain the name, response + trigger count, scope, whatever else makes sense for an overview


    @classmethod
    async def toggleWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "Sentinel":
        query = f"""
        UPDATE {Sentinel}
        SET
            enabled = NOT enabled
        WHERE
            guild_id = ? AND
            name = ?
        RETURNING *
        """
        db.row_factory = Sentinel
        async with db.execute(query, (guild_id, name)) as cur:
            result = await cur.fetchone()
        return result

    async def toggle(self, db: aiosqlite.Connection) -> "Sentinel":
        query = f"""
        UPDATE {SentinelSuit}
        SET
            enabled = NOT enabled
        WHERE
            guild_id = :guild_id AND
            name = :name
        RETURNING *
        """
        db.row_factory = Sentinel
        async with db.execute(query, self.asdict()) as cur:
            result = await cur.fetchone()
        return result

@dataclass
class SentinelInfo:
    guild_id: int
    name: str
    suit_count: int
    trigger_count: int
    response_count: int
    enabled: int

    @classmethod
    async def selectAllWhere(cls, db: aiosqlite.Connection, guild_id: int, limit: int=None, offset: int=0) -> list["SentinelInfo"]:
        query = f"""
        SELECT 
            {Sentinel}.guild_id as guild_id,
            {Sentinel}.name as name,
            (SELECT COUNT(*) FROM {SentinelSuit} 
                WHERE 
                    {SentinelSuit}.sentinel_name = {Sentinel}.name AND 
                    {SentinelSuit}.trigger_id NOT NULL AND 
                    {SentinelSuit}.response_id NOT NULL
            ) AS suit_count,
            (SELECT COUNT(*) FROM {SentinelSuit} 
                WHERE 
                    {SentinelSuit}.sentinel_name = {Sentinel}.name AND 
                    {SentinelSuit}.response_id IS NULL
            ) AS trigger_count,
		    (SELECT COUNT(*) FROM {SentinelSuit} 
                WHERE 
                    {SentinelSuit}.sentinel_name = {Sentinel}.name AND 
                    {SentinelSuit}.trigger_id IS NULL
            ) AS response_count,
            {Sentinel}.enabled AS enabled
	    FROM {SentinelSuit}
	    LEFT JOIN {Sentinel} ON 
		    {Sentinel}.name = {SentinelSuit}.sentinel_name
        WHERE {Sentinel}.guild_id = ?
        GROUP BY {SentinelSuit}.sentinel_name
        LIMIT ? OFFSET ?
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (guild_id, limit, offset)) as cur:
            ress = await cur.fetchall()
        infos = [cls(**res) for res in ress]
        return infos

@dataclass
class SentinelChannelSettings(Table, schema_version=2, trigger_version=1):
    guild_id: int
    channel_id: int
    global_disabled: bool = False
    local_disabled: bool = False

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SentinelChannelSettings}(
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            global_disabled INTEGER DEFAULT 0,
            local_disabled INTEGER DEFAULT 0,
            PRIMARY KEY(guild_id, channel_id),
            FOREIGN KEY(guild_id) REFERENCES {SentinelSettings}(guild_id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        await db.execute(query)

    @classmethod
    async def insert_from_temp(cls, db: aiosqlite.Connection):
        # query = f"""
        # INSERT INTO {DisabledSentinelChannels}(guild_id, channel_id)
        # SELECT guild_id, channel_id
        # FROM temp_{DisabledSentinelChannels}
        # """
        # await db.execute(query)
        # pass
        await super().insert_from_temp(db)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        trigger = f"""
        CREATE TRIGGER IF NOT EXISTS {SentinelChannelSettings}_insert_settings_before_insert
        BEFORE INSERT ON {SentinelChannelSettings}
        BEGIN
            INSERT INTO {SentinelSettings}(guild_id)
            VALUES (NEW.guild_id)
            ON CONFLICT(guild_id) DO NOTHING;
        END;
        """

    async def insert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT OR IGNORE INTO {SentinelChannelSettings}(guild_id, channel_id, global_disabled, local_disabled)
            VALUES(:guild_id, :channel_id, :global_disabled, :local_disabled)
        """
        await db.execute(query, self.asdict())

    @classmethod
    @override
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int, channel_id: int) -> "SentinelChannelSettings | None":
        params = {"guild_id": guild_id, "channel_id": channel_id}
        query = f"""
        DELETE FROM {SentinelChannelSettings}
        WHERE guild_id = :guild_id AND channel_id = :channel_id
        RETURNING *
        """
        db.row_factory = SentinelChannelSettings.row_factory # pyright:ignore [reportAttributeAccessIssue] 
        async with db.execute(query, params) as cur:
            result: SentinelChannelSettings | None = await cur.fetchone() # pyright:ignore [reportAssignmentType]
        return result

    @override
    async def delete(self, db: aiosqlite.Connection) -> "SentinelChannelSettings | None":
        query = f"""
        DELETE FROM {SentinelChannelSettings}
        WHERE guild_id = :guild_id AND channel_id = :channel_id
        RETURNING *
        """
        db.row_factory = SentinelChannelSettings.row_factory # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, self.asdict()) as cur:
            result: SentinelChannelSettings | None = await cur.fetchone() # pyright:ignore [reportAssignmentType]
        return result

    @override
    async def upsert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT INTO {SentinelChannelSettings}(guild_id, channel_id, global_disabled, local_disabled)
        VALUES(:guild_id, :channel_id, :global_disabled, :local_disabled)
        ON CONFLICT (guild_id, channel_id) 
        DO UPDATE SET 
            global_disabled = :global_disabled, 
            local_disabled = :local_disabled
        RETURNING *
        """
        db.row_factory = SentinelChannelSettings.row_factory # pyright:ignore [reportAttributeAccessIssue]
        data = self.asdict()
        async with db.execute(query, data) as cur:
            result: SentinelChannelSettings | None = await cur.fetchone() # pyright:ignore [reportAssignmentType]
        return result
    
    @classmethod
    @override
    async def selectValue(cls, db: aiosqlite.Connection, channel_id: int) -> "SentinelChannelSettings | None":
        query = f"SELECT * FROM {SentinelChannelSettings} WHERE channel_id = ?"
        db.row_factory = SentinelChannelSettings.row_factory # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, (channel_id,)) as cur:
            result: SentinelChannelSettings | None = await cur.fetchone() # pyright:ignore [reportAssignmentType]
        return result

    @classmethod
    async def selectAllWhere(cls, db: aiosqlite.Connection, guild_id: int, limit: int=10, offset: int=0) -> list["SentinelChannelSettings"]:
        query = f"""
        SELECT * FROM {SentinelChannelSettings}
        WHERE guild_id = ?
        LIMIT ? OFFSET ?
        """
        db.row_factory = SentinelChannelSettings.row_factory  # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, (guild_id, limit, offset)) as cur:
            results: list[SentinelChannelSettings] = await cur.fetchall() # pyright:ignore [reportAssignmentType]
        return results

    @classmethod
    async def selectDisabledStatus(cls, db: aiosqlite.Connection, guild_id: int, channel_id: int) -> bool:
        """Returns True of False for the specific scope requested.\\
        The weird guild_id behavior is because I didn't feel like doing a full refactor after a change.
        Everything still operates under the assumptions from the previous simple version of this table.

        Args:
            db (aiosqlite.Connection): The aiosqlite database connection
            guild_id (int): The scope, 0 for global and anything else for a specific guild
            channel_id (int): The id of the discord channel that is being looked up

        Returns:
            bool: _description_
        """        
        query = f"SELECT * FROM {SentinelChannelSettings} WHERE channel_id = ?"
        db.row_factory = SentinelChannelSettings.row_factory # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, (channel_id,)) as cur:
            res: SentinelChannelSettings | None = await cur.fetchone() # pyright:ignore [reportAssignmentType] 
        if res is None:
            return False
        elif guild_id == 0:
            return bool(res.global_disabled)
        else:
            return bool(res.local_disabled)

    
    @classmethod
    async def selectCountWhere(cls, db: aiosqlite.Connection, guild_id: int) -> int:
        query = f"SELECT COUNT(*) FROM {SentinelChannelSettings} WHERE guild_id = ?"
        db.row_factory = None
        async with db.execute(query, (guild_id,)) as cur:
            res = await cur.fetchone()
        return res[0] if res else 0

    @classmethod
    async def selectStatusWhere(cls, db: aiosqlite.Connection, channel_id: int) -> "SentinelChannelSettings | None":
        query = f"""
        SELECT * FROM {SentinelChannelSettings}
        WHERE channel_id = ?
        """
        db.row_factory = SentinelChannelSettings.row_factory # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, (channel_id,)) as cur:
            result: SentinelChannelSettings | None = await cur.fetchone() # pyright:ignore [reportAssignmentType]
        return result


@dataclass
class SentinelTrigger(Table, schema_version=1, trigger_version=1):
    class TriggerType(IntEnum):
        word = 1  # in message split by spaces
        phrase = 2  # in message as string
        regex = 3  # regex matching
        reaction = 4  # triggers on a reaction

        def __str__(self):
            return self.name

    type: TriggerType
    object: str
    id: int | None = None

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SentinelTrigger}(
            id INTEGER NOT NULL,
            type INTEGER NOT NULL,
            object TEXT NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (type, object) 
        )
        """
        await db.execute(query)

    @classmethod
    async def selectID(cls, db: aiosqlite.Connection, trigger_type: TriggerType, trigger_object: str) -> int:
        query = f"""
        SELECT id FROM {SentinelTrigger}
        WHERE type = ? AND object = ?
        """
        db.row_factory = None
        async with db.execute(query, (trigger_type, trigger_object)) as cur:
            result = await cur.fetchone()
        if result: result = result[0]
        assert isinstance(result, int)
        return result

    @override
    async def insert(self, db: aiosqlite.Connection) -> int:
        query = f"""
        INSERT INTO {SentinelTrigger}(type, object)
        VALUES (:type, :object)
        ON CONFLICT(type, object) DO NOTHING
        RETURNING id
        """
        db.row_factory = None
        await db.execute(query, self.asdict())
        id = await SentinelTrigger.selectID(db, self.type, self.object)
        return id

    @override
    async def delete(self, db: aiosqlite.Connection) -> "SentinelTrigger | None":
        query = f"""
        DELETE FROM {SentinelTrigger}
        WHERE id = ?
        RETURNING *
        """
        db.row_factory = SentinelTrigger.row_factory # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, (self.id,)) as cur:
            result: SentinelTrigger | None = await cur.fetchone() # pyright:ignore [reportAssignmentType]
        return result

    @classmethod
    @override
    async def selectValue(cls, db: aiosqlite.Connection, id: int) -> "SentinelTrigger | None":
        query = f"""
            SELECT * FROM {SentinelTrigger}
            WHERE id = ?
            """
        db.row_factory = SentinelTrigger.row_factory # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, (id,)) as cur:
            result: SentinelTrigger | None = await cur.fetchone() # pyright:ignore [reportAssignmentType]
        return result

@dataclass
class SentinelResponse(Table, schema_version=1, trigger_version=1):
    class ResponseType(IntEnum):
        message = 1
        reply = 2
        def __str__(self):
            return self.name
    type: ResponseType
    content: str
    reactions: str
    id: int | None = None

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SentinelResponse}(
            id INTEGER NOT NULL,
            type INTEGER NOT NULL,
            content TEXT,
            reactions TEXT,
            PRIMARY KEY (id),
            UNIQUE (type, content, reactions)
        )
        """
        await db.execute(query)

    @classmethod
    async def selectID(cls, db: aiosqlite.Connection, response_type: ResponseType, content: str, reactions: str) -> int | None:
        query = f"""
        SELECT id FROM {SentinelResponse}
        WHERE type = ? AND content = ? AND reactions = ?
        """
        db.row_factory = None
        async with db.execute(query, (response_type, content, reactions)) as cur:
            result = await cur.fetchone()
        if result: result = result[0]
        assert isinstance(result, int)
        return result

    @override
    async def insert(self, db: aiosqlite.Connection) -> int | None:
        query = f"""
        INSERT INTO {SentinelResponse}(type, content, reactions)
        VALUES (:type, :content, :reactions)
        ON CONFLICT(type, content, reactions) DO NOTHING
        RETURNING id
        """
        db.row_factory = None
        await db.execute(query, self.asdict())
        id = await SentinelResponse.selectID(db, self.type, self.content, self.reactions)
        return id

    @classmethod
    @override
    async def selectValue(cls, db: aiosqlite.Connection, id: int) -> "SentinelResponse | None":
        query = f"""
        SELECT * FROM {SentinelResponse}
        WHERE id = ?
        """
        db.row_factory = SentinelResponse.row_factory # pyright:ignore [reportAttributeAccessIssue]
        async with db.execute(query, (id,)) as cur:
            result: SentinelResponse | None = await cur.fetchone() # pyright:ignore [reportAssignmentType] 
        return result

@dataclass
class SentinelSuit(Table, schema_version=1, trigger_version=1):
    guild_id: int
    sentinel_name: str
    name: str
    weight: int = 100
    trigger_id: int | None = None
    response_id: int | None = None
    enabled: bool = True

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SentinelSuit}(
            guild_id INTEGER NOT NULL,
            sentinel_name TEXT NOT NULL,
            name TEXT NOT NULL,
            weight INTEGER NOT NULL ON CONFLICT REPLACE DEFAULT 10,
            trigger_id INTEGER DEFAULT NULL,
            response_id INTEGER DEFAULT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (guild_id, sentinel_name, name),
            FOREIGN KEY (guild_id, sentinel_name) REFERENCES {Sentinel}(guild_id, name)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (trigger_id) REFERENCES {SentinelTrigger}(id)
                ON UPDATE RESTRICT ON DELETE SET NULL,
            FOREIGN KEY (response_id) REFERENCES {SentinelResponse}(id)
                ON UPDATE RESTRICT ON DELETE SET NULL
        )
        """
        await db.execute(query)

    @classmethod
    async def insert_from_temp(cls, db: aiosqlite.Connection):
        # query = f"""
        # INSERT INTO {SentinelSuit}(guild_id, sentinel_name, name, weight, trigger_id, response_id)
        # SELECT guild_id, sentinel_name, name, weight, trigger_id, response_id
        # FROM temp_{SentinelSuit}
        # """
        # await db.execute(query)
        await super().insert_from_temp(db)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        triggers = [
            # Ensures that a new Sentinel is created for each new Suit if it doesn't have one logged yet
            f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSuit}_insert_sentinel_before_insert
            BEFORE INSERT ON {SentinelSuit}
            BEGIN
                INSERT INTO {Sentinel}(guild_id, name)
                VALUES (NEW.guild_id, NEW.sentinel_name)
                ON CONFLICT(guild_id, name) DO NOTHING;
            END
            """,
            # If a Suit has its Trigger updated and there are no more references to that Trigger, delete the Trigger
            f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSuit}_delete_trigger_after_update
            AFTER UPDATE OF trigger_id on {SentinelSuit}
            WHEN (SELECT COUNT(*) FROM {SentinelSuit} WHERE trigger_id = OLD.trigger_id) = 0 
            BEGIN
                DELETE FROM {SentinelTrigger}
                WHERE id = OLD.trigger_id;
            END
            """,
            # If a Suit has its Response updated and there are no more references to that Response, delete the Response
            f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSuit}_delete_response_after_update
            AFTER UPDATE OF response_id on {SentinelSuit}
            WHEN (SELECT COUNT(*) FROM {SentinelSuit} WHERE response_id = OLD.response_id) = 0 
            BEGIN
                DELETE FROM {SentinelResponse}
                WHERE id = OLD.response_id;
            END
            """,
            # If the deleted Suit is the only reference to a Trigger, delete that Trigger from its table
            f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSuit}_delete_trigger_after_delete
            AFTER DELETE ON {SentinelSuit}
            WHEN (SELECT COUNT(*) FROM {SentinelSuit} WHERE trigger_id = OLD.trigger_id) = 0
            BEGIN
                DELETE FROM {SentinelTrigger}
                WHERE id = OLD.trigger_id;
            END
            """,
            # If the delete Suit is the only reference to a Response, delete that Response from its table
            f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSuit}_delete_response_after_delete
            AFTER DELETE ON {SentinelSuit}
            WHEN (SELECT COUNT(*) FROM {SentinelSuit} WHERE response_id = OLD.response_id) = 0
            BEGIN
                DELETE FROM {SentinelResponse}
                WHERE id = OLD.response_id;
            END
            """,
            # Deletes a Suit if it doesn't have a Trigger or Response
            f"""
            CREATE TRIGGER IF NOT EXISTS {SentinelSuit}_delete_after_update
            AFTER UPDATE ON {SentinelSuit}
            WHEN NEW.trigger_id IS NULL AND NEW.response_id IS NULL
            BEGIN
                DELETE FROM {SentinelSuit}
                WHERE guild_id = OLD.guild_id AND name = OLD.name AND sentinel_name = OLD.sentinel_name;
            END
            """
        ]
        for trigger in triggers:
            await db.execute(trigger)

    async def insert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT OR IGNORE 
        INTO 
            {SentinelSuit}(guild_id, sentinel_name, name, weight, trigger_id, response_id)
        VALUES (
            :guild_id, :sentinel_name, :name, :weight, :trigger_id, :response_id
        )
        """
        await db.execute(query, self.asdict())

    async def upsert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT INTO {SentinelSuit}(guild_id, sentinel_name, name, weight, trigger_id, response_id)
        VALUES (:guild_id, :sentinel_name, :name, :weight, :trigger_id, :response_id)
        ON CONFLICT (guild_id, sentinel_name, name)
        DO UPDATE SET trigger_id = coalesce(trigger_id, :trigger_id), 
                      response_id = coalesce(response_id, :response_id)
        """
        await db.execute(query, self.asdict())

    async def update(self, db: aiosqlite.Connection):
        query = f"""
        INSERT INTO {SentinelSuit}(guild_id, sentinel_name, name, weight, trigger_id, response_id)
        VALUES (:guild_id, :sentinel_name, :name, :weight, :trigger_id, :response_id)
        ON CONFLICT (guild_id, sentinel_name, name)
        DO UPDATE SET trigger_id = :trigger_id,
                      response_id = :response_id,
                      weight = :weight
        """
        await db.execute(query, self.asdict())

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, guild_id: int, sentinel_name: str, name: str) -> "SentinelSuit":
        query = f"""
        SELECT * FROM {SentinelSuit}
        WHERE guild_id = ? AND sentinel_name = ? AND name = ?
        """
        params = (guild_id, sentinel_name, name)
        db.row_factory = SentinelSuit.row_factory
        async with db.execute(query, params) as cur:
            result = await cur.fetchone()
        return result
    
    @classmethod
    async def selectCountWhere(cls, db: aiosqlite.Connection, guild_id: int, sentinel_name: str) -> int:
        query = f"""
        SELECT count(*) FROM {SentinelSuit}
        WHERE guild_id = ? AND sentinel_name = ?
        """
        params = (guild_id, sentinel_name)
        db.row_factory = None
        async with db.execute(query, params) as cur:
            result = await cur.fetchone()
        assert result is not None
        return result[0]

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int, sentinel_name: str, name: str) -> "SentinelSuit":
        query = f"""
        DELETE FROM {SentinelSuit} 
        WHERE guild_id = ? AND sentinel_name = ? AND name = ? 
        RETURNING *
        """
        params = (guild_id, sentinel_name, name)
        db.row_factory = SentinelSuit.row_factory
        async with db.execute(query, params) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectLikeNamesWhere(cls, db: aiosqlite.Connection, guild_id: int, sentinel_name: str, name: str,
                                   limit: int=1, offset: int=0, null_field: Literal["trigger", "response"]=None) -> list["SentinelSuit"]:
        extra = ""
        if null_field == "trigger":
            extra = "AND trigger_id IS NULL"
        elif null_field == "response":
            extra = "AND response_id IS NULL"
        elif null_field is None:
            pass
        else:
            raise ValueError("null_field can be either 'trigger', 'response' or None")

        query = f"""
        SELECT name FROM {SentinelSuit}
        WHERE guild_id = ? AND sentinel_name = ? AND name LIKE ? {extra}
        LIMIT ? OFFSET ?
        """
        params = (guild_id, sentinel_name, f"%{name}%", limit, offset)
        db.row_factory = SentinelSuit.row_factory
        async with db.execute(query, params) as cur:
            result: list[SentinelSuit] = await cur.fetchall()
        return [n.name for n in result]

    @classmethod
    async def toggleWhere(cls, db: aiosqlite.Connection, guild_id: int, sentinel_name: str, name: str) -> "SentinelSuit":
        query = f"""
        UPDATE {SentinelSuit}
        SET
            enabled = NOT enabled
        WHERE
            guild_id = ? AND
            sentinel_name = ? AND
            name = ?
        RETURNING *
        """
        params = (guild_id, sentinel_name, name)
        db.row_factory = SentinelSuit.row_factory
        async with db.execute(query, params) as cur:
            result = await cur.fetchone()
        return result

    async def toggle(self, db: aiosqlite.Connection):
        query = f"""
        UPDATE {SentinelSuit}
        SET
            enabled = NOT enabled
        WHERE
            guild_id = :guild_id AND
            sentinel_name = :sentinel_name AND
            name = :name
        RETURNING *
        """
        db.row_factory = SentinelSuit.row_factory
        async with db.execute(query, self.asdict()) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectFromMessage(cls, db: aiosqlite.Connection, guild_id: int, message_content: str) -> list["SentinelSuit"]:
        query = rf"""
        WITH triggered_suits AS (
            SELECT
                {SentinelSuit}.guild_id,
                {SentinelSuit}.sentinel_name,
                {SentinelSuit}.name,
                weight,
                trigger_id,
                response_id,
                {SentinelSuit}.enabled,
                {Sentinel}.enabled AS sentinel_enabled
            FROM {SentinelSuit}
            LEFT JOIN {SentinelTrigger} ON 
                {SentinelTrigger}.id = {SentinelSuit}.trigger_id 
            LEFT JOIN {Sentinel} ON 
                {Sentinel}.name = {SentinelSuit}.sentinel_name
            WHERE 
                (
                    ({SentinelTrigger}.type = 1 AND :message_content REGEXP '(?i)\b'||{SentinelTrigger}.object||'\b') OR  
                    ({SentinelTrigger}.type = 2 AND :message_content REGEXP '(?i)'||{SentinelTrigger}.object) OR  
                    ({SentinelTrigger}.type = 3 AND :message_content REGEXP {SentinelTrigger}.object)
                ) AND
                {SentinelSuit}.guild_id = :guild_id AND 
                {SentinelSuit}.enabled = 1 AND
                sentinel_enabled = 1
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
        def regexp(pattern, string):
            if string is None:
                return False
            return re.search(pattern, string) is not None
        await db.create_function("REGEXP", 2, regexp)
        db.row_factory = SentinelSuit.row_factory
        params = {"guild_id": guild_id, "message_content": message_content}
        async with db.execute(query, params) as cur:
            results = await cur.fetchall()
        return results

    @classmethod
    async def selectWeightedRandomResponse(cls, db: aiosqlite.Connection, guild_id, sentinel_name) -> "SentinelSuit":
        query = f"""
        with null_trigger_suits AS (
            SELECT
                *
            FROM {SentinelSuit}
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
        db.row_factory = SentinelSuit.row_factory
        params = {"guild_id": guild_id, "sentinel_name": sentinel_name}
        async with db.execute(query, params) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectFromReaction(cls, db: aiosqlite.Connection, guild_id: int, reaction_str: str) -> list["SentinelSuit"]:
        query = f"""
        WITH triggered_suits AS (
            SELECT
                {SentinelSuit}.guild_id,
                {SentinelSuit}.sentinel_name,
                {SentinelSuit}.name,
                weight,
                trigger_id,
                response_id,
                {SentinelSuit}.enabled,
                {Sentinel}.enabled AS sentinel_enabled
            FROM {SentinelSuit}
            LEFT JOIN {SentinelTrigger} ON 
                {SentinelTrigger}.id = {SentinelSuit}.trigger_id 
            LEFT JOIN Sentinel ON 
                {Sentinel}.name = {SentinelSuit}.sentinel_name
            WHERE 
                {SentinelTrigger}.type = 4 AND {SentinelTrigger}.object = :reaction_str AND
                {SentinelSuit}.guild_id = :guild_id AND 
                {SentinelSuit}.enabled = 1 AND
                sentinel_enabled = 1
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
        params = {"guild_id": guild_id, "reaction_str": reaction_str}
        db.row_factory = SentinelSuit.row_factory
        async with db.execute(query, params) as cur:
            results = await cur.fetchall()
        return results

@dataclass
class SuitInfo:
    guild_id: int
    sentinel_name: str
    name: str
    weight: int
    enabled: bool
    trigger_type: SentinelTrigger.TriggerType
    trigger_object: str
    response_type: SentinelResponse.ResponseType
    response_content: str
    response_reactions: str
    
    @classmethod
    async def selectAllWhere(cls, db: aiosqlite.Connection, guild_id: int, sentinel_name: str, limit: int=5, offset: int=0) -> list["SuitInfo"]:
        query = f"""
        SELECT 
            Suit.guild_id as guild_id,
            Suit.sentinel_name as sentinel_name,
            Suit.name as name,
            Suit.weight as weight,
            Suit.enabled as enabled,
            Trigger.type as trigger_type,
            Trigger.object as trigger_object,
            Response.type as response_type,
            Response.content as response_content,
            Response.reactions as response_reactions
        FROM {SentinelSuit} as Suit
        LEFT JOIN {SentinelTrigger} as Trigger ON
            Trigger.id = Suit.trigger_id
        LEFT JOIN {SentinelResponse} as Response ON
            Response.id = Suit.response_id
        WHERE
            guild_id = ? AND sentinel_name = ?
        LIMIT ? OFFSET ?
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (guild_id, sentinel_name, limit, offset)) as cur:
            ress = await cur.fetchall()
        return [cls(**res) for res in ress] 
    
    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int, sentinel_name: str) -> "SuitInfo":
        query = f"""
        SELECT 
            Suit.guild_id as guild_id,
            Suit.sentinel_name as sentinel_name,
            Suit.name as name,
            Suit.weight as weight,
            Suit.enabled as enabled,
            Trigger.type as trigger_type,
            Trigger.object as trigger_object,
            Response.type as response_type,
            Response.content as response_content,
            Response.reactions as response_reactions
        FROM {SentinelSuit} as Suit
        LEFT JOIN {SentinelTrigger} as Trigger ON
            Trigger.id = Suit.trigger_id
        LEFT JOIN {SentinelResponse} as Response ON
            Response.id = Suit.response_id
        WHERE
            guild_id = ? AND sentinel_name = ?
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (guild_id, sentinel_name)) as cur:
            res = await cur.fetchone()
        return cls(**res) 



class SentinelScope(IntEnum):
    """
    Since this is an int enum is can be multiplied by a guild id
    if scope = 0 then guild id = 0
    otherwise for 1 it isn't 0
    This is always going to be binary, if not urgently fix everything that uses the multiplication method
    """
    GLOBAL = 0
    LOCAL = 1


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

class SuitHasNoTrigger(errors.CustomCheck):
    MESSAGE = "The specified suit doesn't have a trigger"

class SuitHasNoResponse(errors.CustomCheck):
    MESSAGE = "The specified suit doesn't have a response"

class SuitAlreadyExists(errors.CustomCheck):
    MESSAGE = "There is already a suit with that name"

class SentinelAlreadyExists(errors.CustomCheck):
    MESSAGE = "There is already a sentinel with that name"


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
    def __init__(self, guild_field="scope"):
        self.guild_field = guild_field
    async def autocomplete(self, interaction: Interaction,
                           current: str, /) -> list[Choice[str]]:
        # await interaction.response.defer()
        # guild_id = interaction.namespace.scope
        guild_id = interaction.namespace[self.guild_field]
        if guild_id == SentinelScope.LOCAL:
            guild_id = interaction.guild_id
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            names = await Sentinel.selectLikeNamesWhere(db,
                                                        guild_id=guild_id,
                                                        name=current,
                                                        limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction,
                        value: str, /) -> discord.Guild:
        # await respond(interaction)
        guild_id = interaction.namespace.scope
        if guild_id == 1: guild_id = interaction.guild_id
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            sentinel = await Sentinel.selectValue(db, guild_id, value)
        return sentinel


class SentinelSuitTransformer(Transformer):
    def __init__(self, empty_field: Literal["trigger_id", "response_id"]=None,
                 guild_field="scope", sentinel_field="sentinel"):
        self.empty_field = empty_field
        self.guild_field = guild_field
        self.sentinel_field = sentinel_field

    async def autocomplete(self, interaction: Interaction,
                           current: str, /) -> List[Choice[str]]:
        guild_id = interaction.namespace[self.guild_field]
        if guild_id == SentinelScope.LOCAL: guild_id = interaction.guild_id
        sentinel_name = interaction.namespace[self.sentinel_field]
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            if self.empty_field == "trigger_id":
                names = await SentinelSuit.selectLikeNamesWhere(db, guild_id, sentinel_name, current,
                                                                limit=25, null_field="trigger")
                # names = await db.fetchSimilarNullTriggerSuitNames(guild_id, sentinel_name, current, limit=25)
            elif self.empty_field == "response_id":
                names = await SentinelSuit.selectLikeNamesWhere(db, guild_id, sentinel_name, current,
                                                                limit=25, null_field="response")
                # names = await db.fetchSimilarNullResponseSuitNames(guild_id, sentinel_name, current, limit=25)
            else:
                names = await SentinelSuit.selectLikeNamesWhere(db, guild_id, sentinel_name, current,
                                                                limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction, value: str, /) -> SentinelSuit:
        # await respond(interaction)
        guild_id = interaction.namespace.scope
        if guild_id == 1: guild_id = interaction.guild_id
        bot: Kagami = interaction.client
        sentinel_name = interaction.namespace.sentinel
        async with bot.dbman.conn() as db:
            result = await SentinelSuit.selectValue(db, guild_id, sentinel_name, value)

        if result:
            if self.empty_field == "trigger_id" and result.trigger_id is not None:
                raise SuitHasTrigger
            elif self.empty_field == "response_id" and result.response_id is not None:
                raise SuitHasResponse

        return result



# class Intermediary:
#     def __init__(self, db_manager: DatabaseManager):
#         self.manager = db_manager
#
#     async def getMatchingSuitsFromMessage(self, guild_id, content):
#         async with self.manager.conn() as db:
#             suits = await SentinelSuit.selectFromMessage(db, guild_id, content)
#         return suits
#
#     async def getWeightedRandomResponseSuit(self, guild_id, sentinel_name):
#         async with self.manager.conn() as db:
#             suit = await SentinelSuit.selectWeightedRandomResponse(db, guild_id, sentinel_name)
#         return suit
#
#     async def fetchResponse(self, response_id):
#         async with self.manager.conn() as db:
#             response = await SentinelResponse.selectWhere(db, response_id)
#         return response
#
#     async def getMatchingSuitsFromReaction(self, guild_id, reaction_str):
#         async with self.manager.conn() as db:
#             suits = await SentinelSuit.selectFromReaction(db, guild_id, reaction_str)
#         return suits
#
#     async def fetchSentinelSettings(self, guild_id):
#         async with self.manager.conn() as db:
#             settings = await SentinelSettings.selectWhere(db, guild_id)
#         return settings
#
#     async def upsertSentinelSettings(self, sentinel_settings: SentinelSettings):
#         async with self.manager.conn() as db:
#             await sentinel_settings.up
#
#     async def getChannelDisabledStatus(self, guild_id, channel_id):
#         async with self.manager.conn() as db:
#             exists = await DisabledSentinelChannels.selectExists(db, guild_id, channel_id)
#         return exists


@app_commands.default_permissions(manage_emojis_and_stickers=True)
class Sentinels(GroupCog, name="s"):
    def __init__(self, bot: Kagami):
        self.bot: Kagami = bot
        self.config = bot.config

    async def cog_load(self) -> None:
        await self.bot.dbman.setup(table_group=__name__,
                                   drop_tables=self.bot.config.drop_tables,
                                   drop_triggers=self.bot.config.drop_triggers,
                                   ignore_schema_updates=self.bot.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.bot.config.ignore_trigger_updates)
        # await self.database.init(drop=self.config.drop_tables, schema_update=self.config.schema_update)
        # await self.database.init(drop=True)
        # if self.bot.config.migrate_data: await self.migrateData()

    async def cog_unload(self) -> None:
        pass

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        return True

    def conn(self) -> ConnectionContext:
        return self.bot.dbman.conn()

    add_group = Group(name="add", description="commands for adding sentinel components")
    remove_group = Group(name="remove", description="commands for removing sentinel components")
    edit_group = Group(name="edit", description="commands for editing sentinel components")
    view_group = Group(name="view", description="commands for viewing sentinel information")
    toggle_group = Group(name="toggle", description="commands for toggling sentinel components")
    enable_group = Group(name="enable", description="commands for enabling sentinel components")
    disable_group = Group(name="disable", description="commands for disabling sentinel components")
    copy_group = Group(name="copy", description="commands for copying sentinel components")
    move_group = Group(name="move", description="commands for moving sentinel components")

    Guild_Transform = Transform[Guild | None, GuildTransformer]
    Sentinel_Transform = Transform[Sentinel | None, SentinelTransformer]
    Suit_Transform = Transform[SentinelSuit | None, SentinelSuitTransformer]
    SuitNullTrigger_Transform = Transform[SentinelSuit | None, SentinelSuitTransformer(empty_field="trigger_id")]
    SuitNullResponse_Transform = Transform[SentinelSuit | None, SentinelSuitTransformer(empty_field="response_id")]


    async def getResponsesForMessage(self, guild_id: int, content: str) -> list[SentinelResponse]:
        async with self.conn() as db:
            triggered_suits = await SentinelSuit.selectFromMessage(db, guild_id, content)
            responses = []
            for suit in triggered_suits:
                response_id = suit.response_id
                if not response_id:
                    response_suit = await SentinelSuit.selectWeightedRandomResponse(db, guild_id, suit.sentinel_name)
                    if not response_suit: continue
                    response_id = response_suit.response_id
                response = await SentinelResponse.selectValue(db, response_id)
                responses += [response]
        return responses

    async def getResponsesForReaction(self, guild_id: int, reaction: discord.Reaction):
        reaction_str = str(reaction)
        async with self.conn() as db:
            triggered_suits = await SentinelSuit.selectFromReaction(db, guild_id, reaction_str)
            responses = []
            for suit in triggered_suits:
                response_id = suit.response_id
                if not response_id:
                    response_suit = await SentinelSuit.selectWeightedRandomResponse(db, guild_id, suit.sentinel_name)
                    if not response_suit: continue
                    response_id = response_suit.response_id
                response = await SentinelResponse.selectValue(db, response_id)
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
                    try:
                        await original_message.add_reaction(partial_emoji)
                    except discord.NotFound: pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        channel_id = message.channel.id
        if message.guild:
            guild_id = message.guild.id
        else:
            return
        if message.author.id == self.bot.user.id:
            return

        async with self.conn() as db:
            global_settings = await SentinelSettings.selectValue(db, 0)
            guild_settings = await SentinelSettings.selectValue(db, guild_id)
            if not guild_settings:
                guild_settings = SentinelSettings(guild_id)
                await guild_settings.upsert(db)
                await db.commit()
            channel_global_disabled = await SentinelChannelSettings.selectDisabledStatus(db, 0, channel_id)
            channel_local_disabled = await SentinelChannelSettings.selectDisabledStatus(db, guild_id, channel_id)

        if global_settings.global_enabled and guild_settings.global_enabled and not channel_global_disabled:
            global_responses = await self.getResponsesForMessage(0, message.content)
            await self.handleResponses(message, global_responses)

        if global_settings.local_enabled and guild_settings.local_enabled and not channel_local_disabled:
            responses = await self.getResponsesForMessage(message.guild.id, message.content)
            await self.handleResponses(message, responses)

        # global_settings = await self.database.fetchSentinelSettings(0)
        # channel_global_disabled = await self.database.getChannelDisabledStatus(0, message.channel.id)
        # guild_settings = await self.database.fetchSentinelSettings(message.guild.id)
        # if guild_settings is None:
        #     guild_settings = SentinelDB.SentinelSettings(message.guild.id)
        #     await self.database.upsertSentinelSettings(guild_settings)
        # channel_local_disabled = await self.database.getChannelDisabledStatus(message.guild.id, message.channel.id)
        #
        # if global_settings.global_enabled and guild_settings.global_enabled and not channel_global_disabled:
        #     global_responses = await self.getResponsesForMessage(0, message.content)
        #     await self.handleResponses(message, global_responses)
        #
        # if global_settings.local_enabled and guild_settings.local_enabled and not channel_local_disabled:
        #     responses = await self.getResponsesForMessage(message.guild.id, message.content)
        #     await self.handleResponses(message, responses)


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
        guild_id = event.guild_id
        channel_id = event.channel_id
        message_id = event.message_id
        if event.user_id == self.bot.user.id:
            return
        async with self.conn() as db:
            if await SentinelChannelSettings.selectDisabledStatus(db, event.guild_id, event.channel_id):
                return

            global_settings = await SentinelSettings.selectValue(db, 0)
            guild_settings = await SentinelSettings.selectValue(db, guild_id)
            if not guild_settings:
                guild_settings = SentinelSettings(guild_id)
                await guild_settings.upsert(db)
                await db.commit()
            channel_global_disabled = await SentinelChannelSettings.selectDisabledStatus(db, 0, channel_id)
            channel_local_disabled = await SentinelChannelSettings.selectDisabledStatus(db, guild_id, channel_id)
        channel = await self.bot.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)

        if global_settings.global_enabled and guild_settings.global_enabled and not channel_global_disabled:
            global_responses = await self.getResponsesForReaction(guild_id=0, reaction=event.emoji)
            await self.handleResponses(message, global_responses)

        if global_settings.local_enabled and guild_settings.local_enabled and not channel_local_disabled:
            responses = await self.getResponsesForReaction(guild_id=guild_id, reaction=event.emoji)
            await self.handleResponses(message, responses)

    @commands.is_owner()
    @commands.group(name="sentinels")
    async def sentinel(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await asyncio.gather(
                ctx.message.delete(delay=5),
                ctx.send("Please specify a valid sentinel command", delete_after=5)
            )

    @commands.is_owner()
    @sentinel.command(name="migrate")
    async def migrateCommand(self, ctx):
        await ctx.send("There is no data to migrate")
        # await self.migrateData()
        # await asyncio.gather(
        #     ctx.message.delete(delay=5),
        #     ctx.send("Migrated sentinel data", delete_after=5)
        # )

    @remove_group.command(name="sentinel", description="deletes a sentinel and all its suits")
    async def remove_sentinel(self, interaction: Interaction, scope: SentinelScope, sentinel: Sentinel_Transform):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        async with self.conn() as db:
            await sentinel.delete(db)
            await db.commit()
        # await self.database.deleteSentinel(sentinel)
        await respond(interaction, f"Removed the Sentinel `{sentinel.name}` and all its Suits")

    @toggle_group.command(name="functionality", description="toggles whether global sentinels will be triggered on this server")
    # @commands.has_permissions(manage_guild=True)
    async def toggle_functionality(self, interaction: Interaction,
                                   extent: Literal["global", "local", "both"],
                                   state: Literal["on", "off"]):
        await respond(interaction, ephemeral=True)
        async with self.conn() as db:
            settings = await SentinelSettings.selectValue(db, interaction.guild_id)
            if settings is None:
                settings = SentinelSettings(interaction.guild_id)
            settings.local_enabled = state == "on" if extent in ["local", "both"] else settings.local_enabled
            settings.global_enabled = state == "on" if extent in ["global", "both"] else settings.global_enabled
            await settings.upsert(db)
            await db.commit()
        state_str: Callable[[str], str] = lambda s: "enabled" if s else "disabled"
        await respond(interaction, f"Sentinel Functionality Status: global sentinels `{state_str(settings.global_enabled)}` "
                                   f"- local sentinels `{state_str(settings.local_enabled)}`", delete_after=5)

    @copy_group.command(name="suit", description="copy a suit's trigger and/or response")
    async def copy_suit(self, interaction: Interaction, scope: SentinelScope,
                        sentinel: Sentinel_Transform, suit: Suit_Transform,
                        fields: Literal["trigger", "response", "both"]="both",
                        new_sentinel: Sentinel_Transform=None):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist

        if interaction.namespace.new_sentinel:
            suit.sentinel_name = interaction.namespace.new_sentinel

        if fields == "trigger":
            if not suit.trigger_id: raise SuitHasNoTrigger
            suit.name += " (trigger copy)"
            suit.response_id = None
        elif fields == "response":
            if not suit.response_id: raise SuitHasNoResponse
            suit.name += " (response copy)"
            suit.trigger_id = None
        else:
            suit.name += " (copy)"
        async with self.conn() as db:
            await suit.insert(db)
            await db.commit()
        await respond(interaction, f"Copied the Suit `{interaction.namespace.suit}` "
                                   f"as `{suit.name}` on Sentinel `{suit.sentinel_name}`", delete_after=5)

    @move_group.command(name="suit", description="Move a suit from one sentinel to another")
    async def move_suit(self, interaction: Interaction, scope: SentinelScope,
                        sentinel: Sentinel_Transform, suit: Suit_Transform,
                        new_sentinel: Sentinel_Transform,
                        new_name: Transform[SentinelSuit, SentinelSuitTransformer(sentinel_field="new_sentinel")]=None):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist
        if new_name: raise SuitAlreadyExists
        async with self.conn() as db:
            await suit.delete(db)
            suit.sentinel_name = interaction.namespace.new_sentinel
            suit.name = interaction.namespace.new_name or suit.name
            await suit.insert(db)
            await db.commit()
        await respond(interaction, f"Moved the Suit `{interaction.namespace.suit}` "
                                   f"as `{suit.name}` to Sentinel `{suit.sentinel_name}`", delete_after=5)

    @move_group.command(name="sentinel", description="Move a sentinel and all its suits to another scope")
    async def move_sentinel(self, interaction: Interaction,
                            scope: SentinelScope, sentinel: Sentinel_Transform,
                            new_scope: SentinelScope,
                            new_name: Transform[Sentinel, SentinelTransformer(guild_field="new_scope")]):
        raise errors.NotImplementedYet
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if new_name: raise SentinelAlreadyExists
        # "There is already a sentinel with that name, either change the name or merge the suits"
        # add more advanced moving in the future



    # App Command
    @app_commands.rename(trigger_type="type", trigger_object="object")
    @add_group.command(name="trigger", description="add a sentinel trigger")
    async def add_trigger(self, interaction: Interaction, scope: SentinelScope,
                          sentinel: Sentinel_Transform, suit: SuitNullTrigger_Transform,
                          trigger_type: SentinelTrigger.TriggerType, trigger_object: str,
                          weight: int=100):
        await respond(interaction, ephemeral=True)
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        if trigger_type == 3:
            try:
                re.compile(trigger_object)
            except re.error:
                raise InvalidRegex
        # guild_id = scope * interaction.guild_id
        trigger = SentinelTrigger(type=trigger_type, object=trigger_object)
        async with self.conn() as db:
            trigger_id = await trigger.insert(db)
            if suit:
                suit.trigger_id = trigger_id
            else:
                suit = SentinelSuit(guild_id, sentinel_name=interaction.namespace.sentinel,
                                    name=interaction.namespace.suit, trigger_id=trigger_id,
                                    weight=weight)
            await suit.upsert(db)
            await db.commit()
        await respond(interaction, f"Added a trigger to the suit `{suit.name}` for sentinel `{suit.sentinel_name}`")
        # await self.database.insertTrigger(trigger)
        # await respond(interaction, f"Added a trigger to the sentinel `{interaction.namespace.sentinel}`")

    @app_commands.rename(response_type="type")
    @app_commands.describe(reactions="emotes separated by semicolon ( ; )")
    @add_group.command(name="response", description="add a sentinel response")
    async def add_response(self, interaction: Interaction, scope: SentinelScope,
                           sentinel: Sentinel_Transform, suit: SuitNullResponse_Transform,
                           response_type: SentinelResponse.ResponseType,
                           content: str="", reactions: str="",
                           weight: int=100):
        await respond(interaction, ephemeral=True)
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        # guild_id = scope * interaction.guild_id
        response = SentinelResponse(type=response_type, content=content, reactions=reactions)
        async with self.conn() as db:
            response_id = await response.insert(db)
            # response_id = await self.database.insertResponse(response)
            if suit:
                # if suit.response_id: raise SentinelDB.SuitHasResponse
                # else:
                suit.response_id = response_id
            else:
                suit = SentinelSuit(guild_id, sentinel_name=interaction.namespace.sentinel,
                                    name=interaction.namespace.suit, response_id=response_id,
                                    weight=weight)
            await suit.upsert(db)
            await db.commit()
        await respond(interaction, f"Added a response to the suit `{suit.name}` for sentinel `{suit.sentinel_name}`")

    @remove_group.command(name="trigger", description="remove a trigger from a suit")
    async def remove_trigger(self, interaction: Interaction,
                             scope: SentinelScope, sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        # set the trigger for the sentinel and suit to None
        suit.trigger_id = None
        async with self.conn() as db:
            await suit.update(db)
            await db.commit()
        await respond(interaction, f"Removed trigger from suit `{suit.name}` for sentinel `{sentinel.name}`")

    @remove_group.command(name="response", description="remove a response from a suit")
    async def remove_response(self, interaction: Interaction,
                              scope: SentinelScope, sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist
        # set the response for the sentinel and suit to None
        suit.response_id = None
        async with self.conn() as db:
            await suit.update(db)
        await respond(interaction, f"Removed response from suit `{suit.name}` for sentinel `{sentinel.name}`")

    @remove_group.command(name="suit", description="remove a trigger-response pairing from a sentinel")
    async def remove_suit(self, interaction: Interaction,
                          scope: SentinelScope, sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist
        async with self.conn() as db:
            await suit.delete(db)
            await db.commit()
        await respond(interaction, f"Remove the suit `{suit.name}` from sentinel `{sentinel.name}`")

    @edit_group.command(name="trigger", description="edit a suit's trigger")
    async def edit_trigger(self, interaction: Interaction, scope: SentinelScope,
                           sentinel: Sentinel_Transform, suit: Suit_Transform,
                           trigger_type: SentinelTrigger.TriggerType | None=None, trigger_object: str | None=None,
                           weight: int | None=None):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist
        if trigger_type == 3 and trigger_object is not None:
            try:
                re.compile(trigger_object)
            except re.error:
                raise InvalidRegex

        async with self.conn() as db:
            if trigger_type and trigger_object:
                trigger = SentinelTrigger(type=trigger_type, object=trigger_object)
                trigger_id = await trigger.insert(db)
                suit.trigger_id = trigger_id
            if weight is not None:
                suit.weight = weight
            await suit.update(db)
            await db.commit()
        await respond(interaction, f"Added edited a trigger on suit `{suit.name}` for sentinel `{suit.sentinel_name}`")

    @edit_group.command(name="response", description="edit a suit's response")
    async def edit_response(self, interaction: Interaction, scope: SentinelScope,
                            sentinel: Sentinel_Transform, suit: Suit_Transform,
                            response_type: SentinelResponse.ResponseType | None=None,
                            content: str | None=None, reactions: str | None=None,
                            weight: int | None=None):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist

        async with self.conn() as db:
            if response_type and (content or reactions):
                reactions = reactions or ""
                content = content or ""
                response = SentinelResponse(type=response_type, content=content, reactions=reactions)
                response_id = await response.insert(db)
                suit.response_id = response_id
            if weight is not None:
                suit.weight = weight
            await suit.update(db)
        await respond(interaction, f"Edited a response on suit `{suit.name}` for sentinel `{suit.sentinel_name}`")


    @toggle_group.command(name="suit", description="toggle an individual suit")
    # @commands.has_permissions(manage_guild=True)
    async def toggle_suit(self, interaction: Interaction, scope: SentinelScope,
                          sentinel: Sentinel_Transform, suit: Suit_Transform):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        if suit is None: raise SuitDoesNotExist
        async with self.conn() as db:
            await suit.toggle(db)
            await db.commit()
        state = "enabled" if not suit.enabled else "disabled"
        await respond(interaction, f"The suit `{suit.name}` on sentinel `{sentinel.name}` is now `{state}`")

    @toggle_group.command(name="sentinel", description="toggle an entire sentinel")
    # @commands.has_permissions(manage_guild=True)
    async def toggle_sentinel(self, interaction: Interaction, scope: SentinelScope,
                              sentinel: Sentinel_Transform):
        await respond(interaction, ephemeral=True)
        if sentinel is None: raise SentinelDoesNotExist
        async with self.conn() as db:
            await sentinel.toggle(db)
            await db.commit()
        state = "enabled" if not sentinel.enabled else "disabled"
        await respond(interaction, f"The sentinel `{sentinel.name}` is now `{state}`")

    async def channel_autocomplete(self, interaction: Interaction, current: str) -> list[Choice[str]]:
        assert interaction.guild is not None
        channels = interaction.guild.text_channels + interaction.guild.voice_channels
        options = [
              Choice(name=channel.name, value=str(channel.id))
              for channel in channels
              if current.lower() in channel.name.lower() or current == str(channel.id)
        ][:25]
        return options

    @toggle_group.command(name="channel", description="toggle all sentinels for a channel")
    # @commands.has_permissions(manage_channels=True)
    async def toggle_channel(self, interaction: Interaction, channel: discord.TextChannel | discord.VoiceChannel | None=None, 
                             state: Literal["Enabled", "Disabled"]="Disabled", extent: Literal["all", "local", "global"]="all"):
        # this is not typed properly throughout but it works and i don't feel like typing this mess right now
        await respond(interaction, ephemeral=True)
        if channel is None:
            channel = interaction.channel
        disabled = state == "Disabled"
        # state_str = "enabled" if state else "disabled"
        response = ""
        async with self.conn() as db:
            settings = await SentinelChannelSettings.selectValue(db, channel_id=channel.id)
            if settings is None:
                settings = SentinelChannelSettings(interaction.guild_id, channel.id)
            match extent:
                case "all":
                   settings.global_disabled = disabled
                   settings.local_disabled = disabled
                   response = f"Local and Global sentinels are now `{state}` in `{channel.name}`"
                case "local":
                    settings.local_disabled = disabled 
                    response = f"Local sentinels are now `{state}` in `{channel.name}`"
                case "global":
                    settings.global_disabled = disabled
                    response = f"Global sentinels are now `{state}` in `{channel.name}`"
                case _:
                    raise ValueError("A literal was violated")
            await settings.upsert(db)
            await db.commit()
        await respond(interaction, response)

    @view_group.command(name="all-channel-settings", description="View all the channels which have disabled sentinels")
    async def view_channels(self, interaction: Interaction):
        message = await respond(interaction, ephemeral=False)
        def rep(b):
            return "Disabled" if b else "Enabled"
        async def callback(irxn: Interaction, state: ScrollerState) -> tuple[str, int, int]:
            offset = state.offset
            async with self.bot.dbman.conn() as db:
                count = await SentinelChannelSettings.selectCountWhere(db, interaction.guild_id)
                if offset * 10 > count:
                    offset = floor(count / 10)
                channel_settings = await SentinelChannelSettings.selectAllWhere(db, interaction.guild_id, limit=10, offset=offset)
            
            reps = []
            for i, settings in enumerate(channel_settings):
                index = (offset * 10) + i + 1
                channel = self.bot.get_channel(settings.channel_id)
                temp = f"{acstr(index, 6)} {acstr(channel.name, 24)} - {acstr(rep(bool(settings.global_disabled)), 8)} | {acstr(rep(bool(settings.local_disabled)), 8)}"
                reps.append(temp)
            body = "\n".join(reps)
            header = f"{acstr('Index', 6)} {acstr('Channel Name', 24)} - {acstr('Globals', 8)} | {acstr('Locals', 8)}"
            content = f"```swift\n{header}\n---\n{body}\n---\n```"
            return content, 0, floor((count-1) / 10)
        scroller = Scroller(message, interaction.user, callback)
        await scroller.update(interaction)

    @view_group.command(name="channel-settings")
    async def view_channel(self, interaction: Interaction, channel: discord.TextChannel=None):
        # this seems to fail on first use sometimes, idk seems fine to me
        # hoping this was fixed by other fixes to id fetching
        # type this at another time
        await respond(interaction, ephemeral=True) 
        channel = channel or interaction.channel
        async with self.conn() as db:
            settings = await SentinelChannelSettings.selectValue(db, channel.id)
        if settings is None:
            settings = SentinelChannelSettings(interaction.guild_id, channel.id)
        def rep(b):
            return "Disabled" if b else "Enabled"
        text = f"`{channel.name}` - globals: `{rep(bool(settings.global_disabled))}`  |  locals: `{rep(bool(settings.local_disabled))}`"
        await respond(interaction, text, delete_after=6)

    @staticmethod 
    def get_view_all_callback(dbman: DatabaseManager, scope: str, guild_id: int):
        
        async def callback(irxn: Interaction, state: ScrollerState) -> tuple[str, int, int]:
            offset = state.initial_offset + state.relative_offset
            async with dbman.conn() as db:
                count = await Sentinel.selectCountWhere(db, guild_id=guild_id)
                if offset * 10 > count:
                    offset = floor(count / 10)
                sentinel_infos = await SentinelInfo.selectAllWhere(db, guild_id=guild_id, limit=10, offset=offset * 10)

            reps = []
            for i, info in enumerate(sentinel_infos):
                index = (offset * 10) + i + 1
                temp = f"{acstr(index, 6)} {acstr(info.name, 16)} - {acstr(info.suit_count, 5)} / ({acstr(info.trigger_count, 8 , 'm')}, {acstr(info.response_count, 9, 'm')}) : {acstr(info.enabled, 7, 'r')}"
                reps.append(temp)
            body = "\n".join(reps)
            header = f"There are {count} sentinels within the {scope} scope\n"
            header += f"{acstr('Index', 6)} {acstr('Name', 16)} - {acstr('Suits', 5, 'm')} / ({acstr('Triggers', 8, 'm')}, {acstr('Responses', 9, 'm')}) : {acstr('Enabled', 7, 'r')}"
            content = f"```swift\n{header}\n---\n{body}\n---\n```"
            # is_last = (count - offset * 10) < 10
            last_index = (count-1) // 10
            return content, 0, last_index
        return callback
    
    @staticmethod
    def get_sentinel_view_callback(dbman: DatabaseManager, scope: str, guild_id: int, sentinel_name: str):
        ITEM_COUNT = 5
        async def callback(irxn: Interaction, state: ScrollerState) -> tuple[str, int, int]:
            offset = state.initial_offset + state.relative_offset
            async with dbman.conn() as db:
                count = await SentinelSuit.selectCountWhere(db, guild_id=guild_id, sentinel_name=sentinel_name)
                if offset * ITEM_COUNT > count:
                    offset = floor(count / 10)
                infos = await SuitInfo.selectAllWhere(db, guild_id, sentinel_name)
            
            item_reps = []
            edges = ("'", "'")
            for index, info in enumerate(infos):
                t_type = SentinelTrigger.TriggerType(info.trigger_type) if info.trigger_type else None
                r_type = SentinelResponse.ResponseType(info.response_type) if info.response_type else None
                temp = f"{acstr(index, 6)} {acstr(info.name, 12)} - {acstr(info.weight, 6, 'r')} : {acstr(bool(info.enabled), 9, 'r')}"
                temp += f"\n{acstr('', 6)} > {acstr(str(t_type), 14)} {acstr(info.trigger_object, 18, edges=edges)}"
                temp += f"\n{acstr('', 6)} > {acstr(str(r_type), 14)} {acstr(info.response_content, 18, edges=edges)} {acstr(info.response_reactions, 20, edges=('(', ')'))}"
                item_reps += [temp]

            header = f"There are {count} suits for the sentinel: {sentinel_name} within the {scope} scope"
            header += f"\n{acstr('Index', 6)} {acstr('Suit Name', 12)} - {acstr('Weight', 6, 'r')} : {acstr('Enabled', 9, 'r')}"
            header += f"\n{acstr('', 6)} {acstr('> Trigger Type', 16)} {acstr('Trigger Object', 18, edges=edges)}"
            header += f"\n{acstr('', 6)} {acstr('> Response Type', 16)} {acstr('Response Content', 18, edges=edges)} {acstr('Response Reactions', 20, edges=('(', ')'))}"
            body = '\n'.join(item_reps)
            content = f"```swift\n{header}\n---\n{body}\n---\n```"

            last_index = floor((count-1) / 10)
            return content, 0, last_index
        return callback

    @view_group.command(name="all", description="view all sentinels on a guild")
    async def view_all(self, interaction: Interaction, scope: SentinelScope):
        message = await respond(interaction)
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        assert guild_id is not None
        scope_str = "local" if scope != 0 else "global"
        callback = self.get_view_all_callback(self.bot.dbman, scope_str, guild_id)
        scroller = Scroller(message, interaction.user, page_callback=callback)
        await scroller.update(interaction)
        
    @view_group.command(name="sentinel", description="view all suits in a sentinel")
    async def view_sentinel(self, interaction: Interaction, scope: SentinelScope, sentinel: Sentinel_Transform):
        message = await respond(interaction)
        if sentinel is None:
            raise SentinelDoesNotExist
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        assert guild_id is not None
        scope_str = "local" if scope != 0 else "global"
        callback = self.get_sentinel_view_callback(self.bot.dbman, scope_str, guild_id, sentinel.name)
        scroller = Scroller(message, interaction.user, callback)
        await scroller.update(interaction)

    @view_group.command(name="suit", description="view the trigger and response associated with a suit")
    async def view_suit(self, interaction: Interaction, scope: SentinelScope, sentinel: Sentinel_Transform, suit: Suit_Transform):
        messsage = await respond(interaction, ephemeral=True)
        if sentinel is None:
            raise SentinelDoesNotExist
        if suit is None:
            raise SuitDoesNotExist
        guild_id = interaction.guild_id if scope == SentinelScope.LOCAL else 0
        assert guild_id is not None
        # scope_str = "local" if scope != 0 else "global"
        async with self.conn() as db:
            info = await SuitInfo.selectWhere(db, guild_id, sentinel.name)
        header = f"Here is the full info for the suit: {suit.name}"
        body = f"Trigger - "
        if info.trigger_type is not None:
            body +=f"\n    > Type : {SentinelTrigger.TriggerType(info.trigger_type)}" + \
                   f"\n    > Object : " + \
                   f"'{info.trigger_object}'" + \
                   f"\nResponse - "
        else:
            body += f"\n   No Trigger"
        if info.response_type is not None:
            body +=f"\n    > Type : {SentinelResponse.ResponseType(info.response_type)}" + \
                   f"\n    > Reactions : ({info.response_reactions})" + \
                   f"\n    > Content : " + \
                   f"'{info.response_content}'"
        else:
            body += f"\n    No Response"
        content = f"```swift\n{header}\n---\n{body}\n---\n```"
        await respond(interaction, content=content, delete_after=30)

async def setup(bot):
    await bot.add_cog(Sentinels(bot))


