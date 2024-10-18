from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Literal, List, Callable, Any
)

import aiosqlite
import discord
from discord.ext import commands
from discord import app_commands, Interaction
from discord.ext.commands import GroupCog
from discord.app_commands import Transform, Transformer, Group, Choice

from bot import Kagami
from common import errors
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, PersistentSettings
from common.paginator import Scroller, ScrollerState
from utils.depr_db_interface import Database
from common.utils import acstr

def StatusType(IntEnum):
    custom = discord.ActivityType.custom
    playing = discord.ActivityType.playing
    streaming = discord.ActivityType.streaming


@dataclass
class Status(Table, table_group="status", schema_version=1, trigger_version=1):
    name: str
    emoji: str
    id: int=None
    
    def toDiscordActivity(self):
        emoji = discord.PartialEmoji.from_str(self.emoji) if self.emoji else None
        return discord.CustomActivity(name=self.name, emoji=emoji)
        
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {Status}(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            emoji TEXT
        )
        """
        await db.execute(query)
        
    async def insert(self, db: aiosqlite.Connection) -> "Status":
        query = f"""
        INSERT OR IGNORE INTO {Status}(name, emoji)
        VALUES(:name, :emoji)
        """
        db.row_factory = None
        await db.execute(query, self.asdict())
        async with db.execute("SELECT last_insert_rowid()") as cur:
            self.id = (await cur.fetchone())[0]
        return self

    @classmethod
    async def selectCount(cls, db: aiosqlite.Connection) -> int:
        query = f"""
        SELECT COUNT(*) FROM {Status}
        """
        db.row_factory = None
        async with db.execute(query) as cur:
            res = await cur.fetchone()
        return res[0] if res else 0
    
    @classmethod
    async def selectFromId(cls, db: aiosqlite.Connection, id: int):
        query = f"""
        SELECT * FROM {Status}
        WHERE id = ?
        """
        db.row_factory = Status.row_factory
        async with db.execute(query, (id,)) as cur:
            res = await cur.fetchone()
        return res
    
    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, limit: int=10, offset: int=0) -> list["Status"]:
        query = f"""
        SELECT * FROM {Status}
        ORDER BY id
        LIMIT ? OFFSET ?
        """
        db.row_factory = Status.row_factory
        async with db.execute(query, (limit, offset)) as cur:
            res = await cur.fetchall()
        return res


class StatusCog(GroupCog, name="status"): 
    def __init__(self, bot: Kagami):
        self.bot: Kagami = bot 
        self.config = bot.config

    async def cog_load(self):
        await self.bot.dbman.setup(table_group="status", 
                                   ignore_schema_updates=self.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.config.ignore_trigger_updates,
                                   drop_tables=self.config.drop_tables)
        if self.bot.is_ready():
            await self.on_ready()
    
    @commands.Cog.listener()
    async def on_ready(self):
        async with self.bot.dbman.conn() as db:
            status_id = (await PersistentSettings.selectWhere(db, key="status_id")).value or 0
            status_data = await Status.selectFromId(db, id=status_id)
        if status_data is not None:
            await self.bot.change_presence(activity=status_data.toDiscordActivity())

    set_group = Group(name="set", description="Sets a custom status and saves it to the list of statuses")
    save_group = Group(name="save", description="Saves a status to the list of statuses")
    temp_group = Group(name="temp", description="Sets a status without saving it")

    @save_group.command(name="custom", description="Saves a custom status to the bot")
    async def save_custom(self, interaction: Interaction, status: str=None, emoji: str=None):
        await respond(interaction, ephemeral=True)
        if not (status or emoji):
            raise errors.CustomCheck("You need to pass either a status or emoji")
        data = Status(name=status, emoji=emoji)
        async with self.bot.dbman.conn() as db:
            await data.insert(db)
            await db.commit()
        await respond(interaction, f"Added custom status to the bot", delete_after=3)

    @set_group.command(name="custom", description="Adds a custom status and immediately updates the bot pressence")
    async def set_custom(self, interaction: Interaction, status: str=None, emoji: str=None):
        await respond(interaction, ephemeral=True)
        if not (status or emoji):
            raise errors.CustomCheck("You need to pass either a status or emoji")
        status_data = Status(name=status, emoji=emoji)
        async with self.bot.dbman.conn() as db:
            status_data = await status_data.insert(db)
            await PersistentSettings(key="status_id", value=status_data.id).upsert(db)
            await db.commit()
        await self.bot.change_presence(activity=status_data.toDiscordActivity())
        await respond(interaction, f"Set status and saved for later", delete_after=3)
        
    @set_group.command(name="from-id", description="Sets the current status from an existing id")
    async def set_from_id(self, interaction: Interaction, id: int):
        await respond(interaction, ephemeral=True)
        async with self.bot.dbman.conn() as db:
            status_data = await Status.selectFromId(db, id=id)
        if status_data is None:
            raise errors.CustomCheck("There is no status with that id")
        await self.bot.change_presence(activity=status_data.toDiscordActivity())
        await respond(interaction, "Updated status", delete_after=3)

    @app_commands.command(name="set-temp", description="sets the bot's status ")
    async def temp_custom(self, interaction: Interaction, status: str=None, emoji: str=None):
        await respond(interaction, ephemeral=True) 
        if not (status or emoji):
            raise errors.CustomCheck("You need to pass either a status or emoji")
        data = Status(name=status, emoji=emoji)
        await self.bot.change_presence(activity=data.toDiscordActivity())
        await respond(interaction, "Updated status", delete_after=3)
    
    @app_commands.command(name="view-all", description="See a list of all saved statuses")
    async def view_all(self, interaction: Interaction):
        message = await respond(interaction)
        async def callback(irxn: Interaction, state: ScrollerState) -> tuple[str, int]:
            offset = state.offset
            async with self.bot.dbman.conn() as db:
                count = await Status.selectCount(db)
                if offset * 10 > count:
                    offset = count // 10
                items: list[Status] = await Status.selectWhere(db, limit=10, offset=offset*10)
            
            reps = []
            for i, status in enumerate(items):
                # index = i + 1 + offset * 10
                temp = f"{acstr(status.id, 6)} {acstr(status.name, 32)} {acstr(status.emoji, 8)}"
                reps.append(temp)

            header = f"{acstr('ID', 6)} {acstr('Status', 32)} {acstr('Emoji', 8)}"
            body = "\n".join(reps)
            content = f"```swift\n{header}\n---\n{body}\n---\n```"
            return content, count // 10
        scroller = Scroller(message=message, user=interaction.user, page_callback=callback)
        await scroller.update(interaction)




async def setup(bot: Kagami):
    await bot.add_cog(StatusCog(bot))

