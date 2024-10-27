from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Literal, List, Callable, Any
)

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from discord.ext.commands import GroupCog
from discord.app_commands import Transform, Transformer, Group, Choice, Range

from bot import Kagami
from common import errors
from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, PersistentSettings
from common.paginator import Scroller, ScrollerState
from utils.depr_db_interface import Database
from common.utils import acstr


# @dataclass
# class ColorRole(Table, schema_version=1, trigger_version=1):
#     guild_id: int
#     role_id: int
#     group_name: str="default"
#     role_name: str
#     hex: str
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#         CREATE TABLE IF NOT EXISTS {ColorRole}(
#             guild_id INTEGER NOT NULL,
#             role_id INTEGER NOT NULL,
#             group_name TEXT,
#             role_name TEXT,
#             hex TEXT,
#             PRIMARY KEY(guild_id, role_id),
#             FOREIGN KEY(guild_id) REFERENCES {Guild}.id
#         )
#         """
#         await db.execute(query)
    
#     @classmethod
#     async def create_triggers(cls, db: aiosqlite.Connection):
#         triggers = [
#             f"""
#             CREATE TRIGGER IF NOT EXISTS {ColorRole}_insert_guild_before_insert
#             BEFORE INSERT ON {ColorRole}
#             BEGIN
#                 INSERT OR IGNORE INTO {Guild}(id)
#                 VALUES (NEW.guild_id);
#             END
#             """,
#             f"""
#             CREATE TRIGGER IF NOT EXISTS {ColorRole}_insert_default-group_before_insert
#             BEFORE INSERT ON {ColorRole}
#             BEGIN
#                 INSERT OR IGNORE INTO {ColorGroup}(guild_id, name, type)
#                 VALUES (NEW.guild_id, 'everyone')
#             """
#         ]
#         await db.execute(trigger)
        
        
#     async def upsert(self, db: aiosqlite.Connection) -> "ColorRole":
#         query = f"""
#         INSERT INTO {ColorRole}(guild_id, role_id, group_name, role_name, hex)
#         VALUES (:guild_id, :role_id, :group_name, :role_name, :hex)
#         ON CONFLCIT (guild_id, role_id)
#         DO UPDATE SET
#             group_name = :group_name,
#             role_name = :role_name,
#             hex = :hex
#         RETURNING *
#         """
#         db.row_factory = ColorRole.row_factory
#         async with db.execute(query, self.asdict()) as cur:
#             res = await cur.fetchone()
#         return res

# TODO Decide on what implemented to use

@dataclass
class ColorSettings(Table, schema_version=1, trigger_version=1):
    guild_id: int
    prefix: str
    
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {ColorSettings}(
            guild_id INTEGER NOT NULL,
            prefix TEXT
        )
        """
        await db.execute(query)
        
    @classmethod
    async def selectPrefixWhere(cls, db: aiosqlite.Connection, guild_id: int) -> str:
        query = f"""
        SELECT prefix FROM {ColorSettings}
        WHERE guild_id = ?
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (guild_id,)) as cur:
            res = await cur.fetchone()
        return res["prefix"] if res else None 
    
    async def upsert(self, db: aiosqlite.Connection) -> "ColorSettings":
        query = f"""
        INSERT INTO {ColorSettings}(guild_id, prefix)
        VALUES (:guild_id, :prefix)
        ON CONFLICT (guild_id)
        DO UPDATE SET
            prefix = :prefix
        RETURNING *
        """
        db.row_factory = ColorSettings.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res


# @dataclass
# class ColorRoles(Table, schema_version=1, trigger_version=1):
#     guild_id: int
#     group_name: int
#     role_id: int=None
#     regex: str=None
    
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#         CREATE TABLE IF NOT EXISTS {ColorRoles}(
#             guild_id INTEGER NOT NULL,
#             group_name TEXT NOT NULL,
#             role_id INTEGER,
#             regex TEXT,
#             FOREIGN KEY(guild_id) REFERENCES {Guild}.id
#         )
#         """
#         await db.execute(query)


# @dataclass
# class ColorPreview(Table, schema_version=1, trigger_version=1):
#     guild_id: int
#     group_name: str
#     image_data: bytes
    
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#         CREATE TABLE IF NOT EXISTS {ColorPreview}(
#             guild_id INTEGER NOT NULL,
#             group_name TEXT NOT NULL,
#             iamge_data BLOB,
#             PRIMARY KEY (guild_id, group_name),
#             FOREIGN KEY (guild_id) REFERENCES {Guild}.id
#         )
#         """
#         await db.execute(query)
    
#     def getImage(self):
#         pass # use pillow to convert bytes to an image
    

# @dataclass
# class ColorGroup(Table, schema_version=1, trigger_version=1):
#     guild_id: int
#     name: str
#     permitted_role_id: int=0
    
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#         CREATE TABLE IF NOT EXISTS {ColorGroup}(
#             guild_id INTEGER NOT NULL,
#             name TEXT NOT NULL,
#             permitted_role_id INTEGER,
#             PRIMARY KEY (guild_id, name),
#             FOREIGN KEY (guild_id) REFERENCES {Guild}.id
#         )
#         """

#     @classmethod
#     async def create_triggers(cls, db: aiosqlite.Connection):
#         trigger = f"""
#         CREATE TRIGGER IF NOT EXISTS {ColorGroup}_insert_guild_before_insert
#         BEFORE INSERT ON {ColorGroup}
#         BEGIN
#             INSERT OR IGNORE INTO {Guild}(id)
#             VALUES (NEW.guild_id);
#         END
#         """
#         await db.execute(trigger)
        
#     async def upsert(self, db: aiosqlite.Connection):
#         query = f"""
#         INSERT INTO {ColorGroup}(guild_id, name, permitted_role_id)
#         VALUES(:guild_id, :name, :permitted_role_id)
#         ON CONFLICT (guild_id, name)
#         DO UPDATE SET
#             permitted_role_id = :permitted_role_id
#         RETURNING *
#         """
#         db.row_factory = ColorGroup.row_factory
#         raise NotImplementedError

#     @classmethod
#     async def selectNamesWheres(cls, db: aiosqlite.Connection, guild_id: int, limit: int=25, offset: int=0) -> list[str]:
#         query = f"""
#         SELECT name FROM {ColorGroup} WHERE guild_id = ?
#         LIMIT ? OFFSET ?
#         """
#         db.row_factory = aiosqlite.Row
#         async with db.execute(query, (guild_id, limit, offset)) as cur:
#             res = await cur.fetchall()
#         return [row["name"] for row in res]
    
#     @classmethod
#     async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "ColorGroup":
#         query = f"""
#         SELECT * FROM {ColorGroup}
#         WHERE
#             guild_id = ?,
#             name = ?
#         """
#         db.row_factory = ColorGroup.row_factory
#         async with db.execute(query, (guild_id, name)) as cur:
#             res = await cur.fetchone()
#         return res


# class GroupTransformer(Transformer):
#     async def autocomplete(self, interaction: Interaction[Kagami], value: str) -> List[Choice[str]]:
#         async with interaction.client.dbman.conn() as db:
#             groups = await ColorGroup.selectNamesWhere(db, interaction.guild_id)
#         return [Choice(g, g) for g in groups]
    
#     async def transform(self, interaction: Interaction[Kagami], value: str) -> str:
#         async with interaction.client.dbman.conn() as db:
#             group = await ColorGroup.selectWhere(db, interaction.guild_id, value)
#         return group

# Group_Transform = Transform[ColorGroup, GroupTransformer]

@app_commands.default_permissions(manage_roles=True)
class ColorCogAdmin(GroupCog, name="color"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman
    
    # @app_commands.command(name="register", description="registers a new arbitrary color role")
    # async def register(self, interation: Interaction, role: discord.Role, group: Group_Transform="everyone"):
    #     await respond(interation, ephemeral=True)
    #     async with self.bot.dbman.conn() as db:
    #         raise NotImplementedError


class ColorCog(GroupCog, name="color"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman
    
    
    async def cog_load(self):
        await self.bot.dbman.setup(table_group=__name__,
                                   drop_tables=self.bot.config.drop_tables,
                                   drop_triggers=self.bot.config.drop_triggers,
                                   ignore_schema_updates=self.bot.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.bot.config.ignore_trigger_updates)

        pass
    
    async def on_ready(self):
        pass
    
    @app_commands.command(name="preview", description="Generates an image preview of all colors on the server")
    async def preview(self, interaction: Interaction):
        await respond(interaction)
        raise NotImplementedError

    
    


async def setup(bot: Kagami):
    bot.add_cog(ColorCog(bot))

