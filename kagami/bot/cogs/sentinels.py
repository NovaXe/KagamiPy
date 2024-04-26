from abc import ABC
from copy import deepcopy
from dataclasses import dataclass
from enum import IntEnum, auto

import aiosqlite
import discord
import discord.ui
from discord._types import ClientT
from discord.ext import commands
from discord import app_commands, Interaction, InteractionMessage, InteractionResponse
from discord.ext.commands import GroupCog, Cog
from discord. app_commands import AppCommand, Transform, Transformer, Range, Group, Choice, autocomplete

from bot.kagami_bot import Kagami
from bot.utils.bot_data import Server, OldSentinel
from bot.utils.interactions import respond
from bot.utils.ui import MessageScroller
from bot.utils.database import Database
from bot.utils.pages import createPageList, createPageInfoText, CustomRepr
from typing import (
    Literal, Union, List
)


class SentinelDB(Database):
    @dataclass
    class SentinelSettings(Database.Row):
        guild_id: int
        sentinels_enabled: bool = True
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS SentinelSettings(
        guild_id INTEGER NOT NULL,
        sentinels_enabled INTEGER DEFAULT 1,
        FOREIGN KEY(guild_id) REFERENCES GUILD(id) 
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS SentinelSettings
        """
        QUERY_UPSERT = """
        INSERT INTO SentinelSettings (guild_id, sentinels_enabled)
        VALUES(:guild_id, :sentinels_enabled)
        ON CONFLICT (guild_id)
        DO UPDATE SET sentinels_enabled = :sentinels_enabled
        """
        QUERY_SELECT = """
        SELECT * FROM SentinelSettings
        WHERE guild_id = ?
        """
        QUERY_DELETE = """
        DELETE FROM SentinelSettings
        WHERE guild_id = ?
        """

    @dataclass
    class Sentinel(Database.Row):
        guild_id: int
        name: str
        uses: int
        enabled: bool = True
        QUERY_CREATE_TABLE = """
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
        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS Sentinel
        """
        TRIGGER_BEFORE_INSERT_GUILD = """
        CREATE TRIGGER IF NOT EXISTS insert_guild_before_insert
        BEFORE INSERT ON Sentinel
        BEGIN
            INSERT INTO Guild(id)
            VALUES (NEW.guild_id)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_INSERT = """
        INSERT INTO Sentinel(guild_id, name)
        VALUES(:guild_id, :name)
        ON CONFLICT DO NOTHING
        """
        QUERY_INCREMENT_USES = """
        UPDATE Sentinel SET uses = uses + 1
        WHERE guild_id = ? AND name = ?
        """
        QUERY_EDIT = """
        Update Sentinel SET name = :name
        WHERE name = :old_name
        """
        QUERY_SELECT = """
        SELECT * FROM Sentinel
        WHERE guild_id = ? AND name = ?
        """
        QUERY_SELECT_LIKE_NAMES = """
        SELECT name FROM Sentinel
        WHERE (guild_id = ?) AND (name LIKE ?)
        LIMIT ? OFFSET ?
        """

    @dataclass
    class SentinelTrigger(Database.Row):
        class TriggerType(IntEnum):
            word = auto()
            phrase = auto()
            regex = auto()
            reaction = auto()
        guild_id: int
        sentinel_name: str
        type: int
        object: str
        enabled: bool = True
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS SentinelTrigger(
        guild_id INTEGER NOT NULL,
        sentinel_name TEXT NOT NULL,
        type INTEGER NOT NULL DEFAULT 0,
        object TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(guild_id) REFERENCES GUILD(id) 
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(sentinel_name) REFERENCES Sentinel(name)
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS SentinelTrigger
        """
        TRIGGER_BEFORE_INSERT_SENTINEL = """
        CREATE TRIGGER IF NOT EXISTS insert_sentinel_before_insert
        BEFORE INSERT ON SentinelTrigger
        BEGIN
            INSERT INTO Sentinel(guild_id, name)
            VALUES (NEW.guild_id, NEW.sentinel_name)
            ON CONFLICT DO NOTHING;
        END
        """
        TRIGGER_AFTER_INSERT_USES = """
        CREATE TRIGGER IF NOT EXISTS insert_uses_after_insert
        AFTER INSERT ON SentinelTrigger
        BEGIN
            INSERT INTO SentinelTriggerUses(guild_id, trigger_object, user_id)
            VALUES (NEW.guild_id, NEW.object, 0)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_INSERT = """
        INSERT INTO SentinelTrigger (guild_id, sentinel_name, type, object)
        VALUES (:guild_id, :sentinel_name, :type, :object)
        ON CONFLICT DO NOTHING
        """

    # guild_id = 0 is for global uses by users
    # only one instance for each user on a guild or globally
    # user_id = 0 is for all users
    # on sentinel usage, increase its tally for the local guild and global
    # also increase the tally for all users locally and globally (user_id = 0)
    @dataclass
    class SentinelTriggerUses(Database.Row):
        guild_id: str
        trigger_object: str
        user_id: int
        uses: int
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS SentinelTriggerUses(
        guild_id INTEGER NOT NULL,
        trigger_object TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        uses INTEGER DEFAULT 0,
        UNIQUE (guild_id, trigger_object, user_id),
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
    class SentinelResponse(Database.Row):
        class ResponseType(IntEnum):
            message = auto()
            reply = auto()
        guild_id: int
        sentinel_name: str
        type: int
        content: str
        reactions: str # a string which can be split by
        # view: str
        # somehow support
        enabled: bool = True
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS SentinelResponse(
        guild_id INTEGER NOT NULL,
        sentinel_name TEXT NOT NULL,
        type INTEGER NOT NULL,
        content TEXT,
        reactions TEXT,
        enabled INTEGER DEFAULT 1,
        FOREIGN KEY(guild_id) REFERENCES GUILD(id) 
             ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(sentinel_name) REFERENCES Sentinel(name) 
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS SentinelResponse
        """
        TRIGGER_BEFORE_INSERT_SENTINEL = """
        CREATE TRIGGER IF NOT EXISTS insert_sentinel_before_insert
        BEFORE INSERT ON SentinelResponse
        BEGIN
            INSERT INTO Sentinel(guild_id, name)
            VALUES (NEW.guild_id, NEW.sentinel_name)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_INSERT = """
        INSERT INTO SentinelResponse(guild_id, sentinel_name, type, content, reactions)
        VALUES (:guild_id, :sentinel_name, :type, :content, :reactions)
        ON CONFLICT DO NOTHING
        """

    async def init(self, drop: bool=False):
        if drop: await self.dropTables()
        await self.createTables()
        await self.createTriggers()

    async def createTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelSettings.QUERY_CREATE_TABLE)
            await db.execute(SentinelDB.Sentinel.QUERY_CREATE_TABLE)
            await db.execute(SentinelDB.SentinelTrigger.QUERY_CREATE_TABLE)
            await db.execute(SentinelDB.SentinelResponse.QUERY_CREATE_TABLE)
            await db.execute(SentinelDB.SentinelTriggerUses.QUERY_CREATE_TABLE)
            await db.commit()

    async def createTriggers(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.Sentinel.TRIGGER_BEFORE_INSERT_GUILD)
            await db.execute(SentinelDB.SentinelTrigger.TRIGGER_BEFORE_INSERT_SENTINEL)
            await db.execute(SentinelDB.SentinelTrigger.TRIGGER_AFTER_INSERT_USES)
            await db.execute(SentinelDB.SentinelTriggerUses.TRIGGER_BEFORE_INSERT_USER)
            await db.execute(SentinelDB.SentinelResponse.TRIGGER_BEFORE_INSERT_SENTINEL)
            await db.commit()

    async def dropTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.Sentinel.QUERY_DROP_TABLE)
            await db.execute(SentinelDB.SentinelTrigger.QUERY_DROP_TABLE)
            await db.execute(SentinelDB.SentinelResponse.QUERY_DROP_TABLE)
            await db.execute(SentinelDB.SentinelTriggerUses.QUERY_DROP_TABLE)
            await db.commit()

    async def upsertSentinelSettings(self, sentinel_settings: SentinelSettings):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelSettings.QUERY_UPSERT, sentinel_settings.asdict())
            await db.commit()

    async def insertSentinel(self, sentinel: Sentinel) -> bool:
        async with aiosqlite.connect(self.file_path) as db:
            cursor = await db.execute(SentinelDB.Sentinel.QUERY_INSERT, sentinel.asdict())
            row_count = cursor.rowcount
            await db.commit()
        return row_count > 0


    async def insertTrigger(self, trigger: SentinelTrigger):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelTrigger.QUERY_INSERT, trigger.asdict())
            await db.commit()

    async def insertTriggers(self, triggers: list[SentinelTrigger]):
        async with aiosqlite.connect(self.file_path) as db:
            data = [trigger.asdict() for trigger in triggers]
            await db.executemany(SentinelDB.SentinelTrigger.QUERY_INSERT, data)
            await db.commit()

    async def insertResponse(self, response: SentinelResponse):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(SentinelDB.SentinelResponse.QUERY_INSERT, response.asdict())
            await db.commit()

    async def insertResponses(self, responses: list[SentinelResponse]):
        async with aiosqlite.connect(self.file_path) as db:
            data = [response.asdict() for response in responses]
            await db.executemany(SentinelDB.SentinelResponse.QUERY_INSERT, data)
            await db.commit()




    async def fetchSentinel(self, guild_id: int, name: str) -> Sentinel:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = SentinelDB.Sentinel.rowFactory
            result: list[SentinelDB.Sentinel] = await db.execute_fetchall(SentinelDB.Sentinel.QUERY_SELECT,
                                                                          (guild_id, name))
        return result[0] if result else None

    async def fetchSimilarSentinelNames(self, guild_id: int, name: str, limit: int=1, offset: int=0):
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(SentinelDB.Sentinel.QUERY_SELECT_LIKE_NAMES,
                                                         (guild_id, f"%{name}%", limit, offset))
            names = [n[0] for n in names]
        return names


class SentinelScope(IntEnum):
    """
    Since this is an int enum is can be multiplied by a guild id
    if scope = 0 then guild id = 0
    otherwise for 1 it isn't 0
    This is always going to be binary, if not urgently fix everything that uses the multiplication method
    """
    GLOBAL = 0
    LOCAL = 1


# class ScopeTransformer(Transformer):
#     async def autocomplete(self, interaction: Interaction,
#                            current: str) -> list[Choice[str]]:
#


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
                           current: str) -> list[Choice[str]]:
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
        guild_id = interaction.namespace.scope
        if guild_id == 1: guild_id = interaction.guild_id
        bot: Kagami = interaction.client
        db = SentinelDB(bot.config.db_path)
        return await db.fetchSentinel(guild_id=guild_id, name=value)


async def triggerSanityCheck(trigger_type: SentinelDB.SentinelTrigger.TriggerType,
                             trigger_object: str) -> bool:
    assert False


async def triggerSanitizer(trigger_type: SentinelDB.SentinelTrigger.TriggerType,
                           trigger_object: str) -> tuple[SentinelDB.SentinelTrigger.TriggerType, str]:
    assert False


async def responseSanityCheck(response_type: SentinelDB.SentinelResponse.ResponseType,
                              content: str, reactions: str) -> bool:
    assert False


async def responseSanitizer(response_type: SentinelDB.SentinelResponse.ResponseType,
                            content: str,
                            reactions: str) -> tuple[SentinelDB.SentinelResponse.ResponseType, str, str]:
    assert False


class Sentinels(GroupCog, name="s"):
    def __init__(self, bot: Kagami):
        self.bot: Kagami = bot
        self.config = bot.config
        self.database = SentinelDB(bot.config.db_path)

    async def cog_load(self) -> None:
        await self.database.init(drop=self.config.drop_tables)
        pass

    async def cog_unload(self) -> None:
        pass

    async def interaction_check(self, interaction: discord.Interaction[ClientT], /) -> bool:
        return True

    add_group = Group(name="add", description="commands for adding sentinel components")
    remove_group = Group(name="remove", description="commands for removing sentinel components")

    Guild_Transform = Transform[Database.Guild, GuildTransformer]
    Sentinel_Transform = Transform[SentinelDB.Sentinel, SentinelTransformer]


    @commands.is_owner()
    @commands.command(name="migrate_sentinels")
    async def migrateCommand(self, ctx):
        await self.migrateData()
        await ctx.send("Migrated sentinel data")

    async def migrateData(self):
        """
        Old Sentinels are triggered by their name being present as a phrase in the message
        They have a separate response parameter
        data migration missing usage numbers
        upsert into the usage table for each as well
        """
        async def convertSentinel(_guild_id: int, _sentinel_name: str,  _sentinel: OldSentinel
                                  ) -> tuple[SentinelDB.SentinelTrigger, SentinelDB.SentinelResponse]:
            _trigger = SentinelDB.SentinelTrigger(guild_id=_guild_id, sentinel_name=_sentinel_name,
                                                  type=SentinelDB.SentinelTrigger.TriggerType.phrase,
                                                  object=_sentinel_name, enabled=_sentinel.enabled)
            reactions = ";".join(_sentinel.reactions)
            _response = SentinelDB.SentinelResponse(guild_id=_guild_id, sentinel_name=_sentinel_name,
                                                    type=SentinelDB.SentinelResponse.ResponseType.reply,
                                                    content=_sentinel.response, reactions=reactions)
            return _trigger, _response

        for server_id, server in self.bot.data.servers.items():
            server_id = int(server_id)
            try: guild = await self.bot.fetch_guild(server_id)
            except discord.NotFound: continue
            converted_sentinels = [await convertSentinel(server_id, name, sentinel)
                                   for name, sentinel in server.sentinels.items()]
            if len(converted_sentinels):
                triggers, responses = zip(*converted_sentinels)
                await self.database.insertTriggers(triggers)
                await self.database.insertResponses(responses)

        converted_sentinels = [await convertSentinel(0, name, sentinel)
                               for name, sentinel in self.bot.data.globals.sentinels.items()]
        if len(converted_sentinels):
            triggers, responses = zip(*converted_sentinels)
            await self.database.insertTriggers(triggers)
            await self.database.insertResponses(responses)

    @app_commands.rename(trigger_type="type", trigger_object="object")
    @add_group.command(name="trigger", description="add a sentinel trigger")
    async def add_trigger(self, interaction: Interaction, scope: SentinelScope, sentinel: Sentinel_Transform,
                          trigger_type: SentinelDB.SentinelTrigger.TriggerType, trigger_object: str):
        await respond(interaction)
        guild_id = scope * interaction.guild_id
        trigger = SentinelDB.SentinelTrigger(guild_id=guild_id, sentinel_name=interaction.namespace.sentinel,
                                             type=trigger_type, object=trigger_object)
        await self.database.insertTrigger(trigger)
        await respond(interaction, f"Added a trigger to the sentinel `{interaction.namespace.sentinel}`")

    @app_commands.rename(response_type="type")
    @app_commands.describe(reactions="emotes separated by ;")
    @add_group.command(name="response", description="add a sentinel response")
    async def add_response(self, interaction: Interaction, scope: SentinelScope, sentinel: Sentinel_Transform,
                           response_type: SentinelDB.SentinelResponse.ResponseType, content: str="", reactions: str=""):
        await respond(interaction)
        guild_id = scope * interaction.guild_id
        response = SentinelDB.SentinelResponse(guild_id=guild_id, sentinel_name=interaction.namespace.sentinel,
                                               type=response_type, content=content, reactions=reactions)
        await self.database.insertResponse(response)
        await respond(interaction, f"Added a response to the sentinel `{interaction.namespace.sentinel}`")




class OldSentinelTransformer(app_commands.Transformer, ABC):
    def __init__(self, cog: 'OldSentinels', mode: Literal['global', 'local']):
        self.mode = mode
        self.cog: 'OldSentinels' = cog


    async def transform(self, interaction: discord.Interaction, value: str) -> dict[str, dict]:
        source = None
        if self.mode == 'server':
            server: Server = self.cog.bot.fetch_server(interaction.guild_id)
            source = server.sentinels
        elif self.mode == 'global':
            source = self.cog.bot.global_data['sentinels']

        return source[value]

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        source = None
        if self.mode == 'server':
            server: Server = self.cog.bot.fetch_server(interaction.guild_id)
            source = server.sentinels
        elif self.mode == 'global':
            source = self.cog.bot.global_data['sentinels']

        options = [app_commands.Choice(name=sentinel_phrase, value=sentinel_phrase)
                   for sentinel_phrase, sentinel_data in source['sentinels']
                   if current.lower() in sentinel_phrase.lower()][:25]


def createSentinelData(response: str, reactions: list[str]) -> dict:
    return {
            'response': response,
            'reactions': reactions,
            'uses': 0,
            'enabled': True
        }


class OldSentinels(commands.GroupCog, group_name="sentinel"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        # self.globalTransformer = SentinelTransformer(self, 'global')
        # self.localTransformer = SentinelTransformer(self, 'local')
        # self.local_sentinel_autocomplete = self.wrapped_sentinel_autocomplete(mode='global')

    custom_key_reprs = {
        "response": CustomRepr(ignored=True),
        "reactions": CustomRepr(),
        "uses": CustomRepr(),
        "enabled": CustomRepr()
    }



    add_group = app_commands.Group(name="add", description="Create a new sentinel")
    remove_group = app_commands.Group(name="remove", description="Remove a sentinel")
    edit_group = app_commands.Group(name="edit", description="Edit an existing sentinel")
    list_group = app_commands.Group(name="list", description="Lists all sentinels")
    info_group = app_commands.Group(name="info", description="Gets sentinel info")
    toggle_group = app_commands.Group(name="toggle", description="Toggle a sentinel")

    async def sentinel_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        source = None
        if interaction.command.name == 'local':
            server: Server = self.bot.fetch_server(interaction.guild_id)
            source = server.sentinels
        elif interaction.command.name == 'global':
            source = self.bot.global_data['sentinels']

        options = [
                      app_commands.Choice(name=sentinel_phrase, value=sentinel_phrase)
                      for sentinel_phrase, sentinel_data in source.items()
                      if current.lower() in sentinel_phrase.lower()
        ][:25]
        return options


    # Add Commands
    @staticmethod
    async def add_handler(interaction, data, source, sentinel_phrase,  response, reactions):
        if reactions:
            reactions = [reaction for reaction in reactions.split(' ') if reaction]
        else:
            reactions = []

        if response is None:
            response = ''

        new_sentinel = createSentinelData(response, reactions)
        data.update({
            sentinel_phrase: new_sentinel
        })

        if source == 'global':
            await interaction.edit_original_response(content=f'Added the global sentinel `{sentinel_phrase}`')
        elif source == 'local':
            await interaction.edit_original_response(content=f'Added the sentinel `{sentinel_phrase}` to {interaction.guild.name}')
        else:
            await interaction.edit_original_response(content=f"what?")

    @add_group.command(name="global", description="Creates a new global sentinel")
    async def add_global(self, interaction: discord.Interaction, sentinel_phrase: str, response: str=None, reactions: str=None):
        await interaction.response.defer(thinking=True)
        # reactions = re.findall('(<a?:[a-zA-Z0-9_]+:[0-9]+>)', reactions)
        # reaction_names = [f":{re.match(r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>$', reaction).group(2)}:" for reaction in reactions]
        # discord.PartialEmoji.from_str(reaction)
        data = self.bot.global_data['sentinels']
        await self.add_handler(interaction, data, 'global', sentinel_phrase, response, reactions)

    @add_group.command(name="local", description="Creates a new global sentinel")
    async def add_local(self, interaction: discord.Interaction, sentinel_phrase: str, response: str = None, reactions: str = None):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        data = server.sentinels
        await self.add_handler(interaction, data, interaction.guild.name, sentinel_phrase, response, reactions)

    # Remove Commands
    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @remove_group.command(name="global", description="Remove a global sentinel")
    async def remove_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        await interaction.response.defer(thinking=True)
        if sentinel_phrase not in self.bot.global_data['sentinels'].keys():
            await interaction.edit_original_response(content=f"The global sentinel **`{sentinel_phrase}`** doesn't exist")
            return

        self.bot.global_data['sentinels'].pop(sentinel_phrase, None)
        await interaction.edit_original_response(content=f'Removed the global sentinel `{sentinel_phrase}`')
        pass

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @remove_group.command(name="local", description="Remove a local sentinel")
    async def remove_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        await interaction.response.defer(thinking=True)
        if sentinel_phrase not in server.sentinels.keys():
            await interaction.edit_original_response(content=f"The sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        server.sentinels.pop(sentinel_phrase, None)
        await interaction.edit_original_response(content=f'Removed the sentinel `{sentinel_phrase}` from `{interaction.guild.name}`')

    # Edit Commands
    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @edit_group.command(name='global', description='Edit a global sentinel')
    async def edit_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        if sentinel_phrase not in self.bot.global_data['sentinels'].keys():
            await interaction.response.send_message(content=f"The global sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        await interaction.response.send_modal(SentinelEditorModal(self.bot.global_data['sentinels'], sentinel_phrase))

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @edit_group.command(name='local', description='Edit a local sentinel')
    async def edit_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if sentinel_phrase not in server.sentinels.keys():
            await interaction.response.send_message(content=f"The sentinel **`{sentinel_phrase}`** doesn't exist on `{interaction.guild.name}`")
            return
        await interaction.response.send_modal(SentinelEditorModal(self.bot.fetch_server(interaction.guild_id).sentinels, sentinel_phrase))

    # Toggle Commands
    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @toggle_group.command(name='global', description='Toggle the active status of a global sentinel')
    async def toggle_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        if sentinel_phrase not in self.bot.global_data['sentinels'].keys():
            await interaction.response.send_message(
                content=f"The global sentinel **`{sentinel_phrase}`** doesn't exist")
            return

        previous_state = self.bot.global_data['sentinels'][sentinel_phrase]['enabled']
        self.bot.global_data['sentinels'][sentinel_phrase]['enabled'] = not previous_state
        await interaction.response.send_message(
            content=f"The sentinel **`{sentinel_phrase}`** is now `{'enabled' if not previous_state else 'disabled'}`")

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @toggle_group.command(name='local', description='Toggle the active status of a local sentinel')
    async def toggle_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if sentinel_phrase not in server.sentinels.keys():
            await interaction.response.send_message(
                content=f"The sentinel **`{sentinel_phrase}`** doesn't exist on `{interaction.guild.name}`")
            return
        previous_state = server.sentinels[sentinel_phrase]["enabled"]
        server.sentinels[sentinel_phrase]["enabled"] = not previous_state
        await interaction.response.send_message(
            content=f"The sentinel **`{sentinel_phrase}`** is now `{'enabled' if not previous_state else 'disabled'}`")

    # List Commands
    async def list_handler(self, interaction, data, source):
        data = self.cleanSentinelData(data)
        total_count = len(data)
        info_text = createPageInfoText(total_count, source, 'data', 'sentinels')
        pages = createPageList(info_text=info_text,
                               data=data,
                               total_item_count=total_count,
                               custom_reprs=self.custom_key_reprs)

        # pages = self.create_sentinel_pages('global', self.bot.global_data['sentinels'])
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(content=pages[0], view=view)

    @list_group.command(name='global', description="List all global sentinels")
    async def list_global(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        data: dict = self.bot.global_data['sentinels']
        await self.list_handler(interaction, data, 'global')

    @list_group.command(name='local', description="List all local sentinels")
    async def list_local(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        data: dict = server.sentinels
        await self.list_handler(interaction, data, interaction.guild.name)

    # Info Commands
    @staticmethod
    async def info_handler(interaction, source, sentinel_phrase, sentinel_data):
        reactions = []
        if _reactions := sentinel_data['reactions']:
            for reaction in _reactions:
                partial_emoji = discord.PartialEmoji.from_str(reaction)
                if partial_emoji.is_custom_emoji():
                    name = f':{partial_emoji.name}:'  # {partial_emoji.id}
                else:
                    name = partial_emoji.name
                reactions.append(name)
        else:
            reactions.append('None')
        reactions = f"[ {' '.join(reactions)} ]"

        content = f'```swift\n' \
                  f'{source.capitalize()} Sentinel Info: {sentinel_phrase}\n' \
                  f'──────────────────────────────────────\n' \
                  f'Reactions:  {reactions}\n' \
                  f'Uses:       {sentinel_data["uses"]}\n' \
                  f'Enabled:    {sentinel_data["enabled"]}' \
                  f'```'

        await interaction.edit_original_response(content=content)

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @info_group.command(name='global', description='Gets the info of a global sentinel')
    async def info_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        await interaction.response.defer(thinking=True)
        if sentinel_phrase not in self.bot.global_data['sentinels'].keys():
            await interaction.edit_original_response(content=f"The global sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        sentinel_data = self.bot.global_data['sentinels'][sentinel_phrase]
        await self.info_handler(interaction, 'global', sentinel_phrase, sentinel_data)

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @info_group.command(name='local', description='Gets the info of a local sentinel')
    async def info_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if sentinel_phrase not in server.sentinels.keys():
            await interaction.edit_original_response(content=f"The sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        sentinel_data = server.sentinels[sentinel_phrase]
        await self.info_handler(interaction, 'local', sentinel_phrase, sentinel_data)

    # Sentinel Event
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return
        server: Server = self.bot.fetch_server(message.guild.id)

        await self.process_sentinel_event(message, self.bot.global_data['sentinels'])
        await self.process_sentinel_event(message, server.sentinels)

    @staticmethod
    async def process_sentinel_event(message: discord.Message, sentinels):
        content = message.content.lower()
        # if content := content.split(' '):
        #     pass

        for sentinel_phrase, sentinel_data in sentinels.items():
            if sentinel_phrase.lower() in content:
                if not sentinels[sentinel_phrase]['enabled']:
                    return  # Ignore if disabled
                if reactions := sentinel_data['reactions']:
                    for reaction in reactions:
                        if reaction != 'None':
                            await message.add_reaction(reaction)
                if response := sentinel_data['response']:
                    await message.reply(content=response)
                sentinel_data['uses'] += 1



    @staticmethod
    def cleanSentinelData(sentinels: dict):
        clean_sentinels = deepcopy(sentinels)
        for sentinel, sentinel_data in clean_sentinels.items():
            clean_reactions = []
            if sentinel_data['reactions']:
                for reaction in sentinel_data['reactions']:
                    partial_emoji = discord.PartialEmoji.from_str(reaction)
                    if partial_emoji.is_custom_emoji():
                        name = f':{partial_emoji.name}:'  # {partial_emoji.id}
                    else:
                        name = partial_emoji.name
                    clean_reactions.append(name)
            else:
                clean_reactions.append('None')

            sentinel_data["reactions"] = clean_reactions
        return clean_sentinels





class SentinelEditorModal(discord.ui.Modal, title='Edit Sentinels'):
    def __init__(self, sentinel_source, sentinel_phrase):
        super().__init__()
        self.sentinel_source = sentinel_source
        self.original_sentinel_phrase = sentinel_phrase
        self.sentinel_phrase.default = sentinel_phrase
        self.response.default = sentinel_source[sentinel_phrase]['response']
        self.reactions_txt.default = ','.join(sentinel_source[sentinel_phrase]['reactions'])

    sentinel_phrase = discord.ui.TextInput(label='Phrase', placeholder='Enter the phrase the bot will listen for')
    response = discord.ui.TextInput(label="Response", placeholder='Enter the response to the sentinel event', required=False)
    reactions_txt = discord.ui.TextInput(label="Reactions", placeholder="Type your reactions like this :emote: :emote:", required=False)


    async def on_submit(self, interaction: discord.Interaction) -> None:
        data: dict = self.sentinel_source[self.original_sentinel_phrase]
        self.sentinel_source.pop(self.original_sentinel_phrase, None)

        data.update({
            'response': self.response.value,
            'reactions': [f'{emote}' for emote in self.reactions_txt.value.split(',') if emote]
        })


        self.sentinel_source.update({
            self.sentinel_phrase.value: data
        })


        # new_data = self.sentinel_source[self.sentinel_phrase].update({
        #     'response': self.response.value,
        #     'reactions': [f':{emote}:' for emote in self.reactions_txt.value.split(':') if emote]
        # })



        # self.sentinel_source.update({
        #     self.sentinel_phrase.value: {
        #         'response': self.response.value,
        #         'reactions': [f':{emote}:' for emote in self.reactions_txt.value.split(':') if emote],
        #     }
        # })
        await interaction.response.send_message(content=f'Edited the sentinel `{self.original_sentinel_phrase}`'
                                                        f' {f"now called {self.sentinel_phrase.value}" if self.original_sentinel_phrase != self.sentinel_phrase.value else ""}')




async def setup(bot):
    await bot.add_cog(OldSentinels(bot))
    await bot.add_cog(Sentinels(bot))

