from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Literal, List, Callable, Any, cast
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
from common.utils import acstr

logger = setup_logging(__name__)

def StatusType(IntEnum):
    custom = discord.ActivityType.custom
    playing = discord.ActivityType.playing
    streaming = discord.ActivityType.streaming


@dataclass
class Status(Table, schema_version=1, trigger_version=1):
    name: str
    emoji: str
    id: int|None=None
    
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
        INSERT OR IGNORE INTO {Status} (name, emoji)
        VALUES(:name, :emoji)
        """
        db.row_factory = None
        async with db.cursor() as cur:
            await cur.execute(query, self.asdict())
            self.id = cur.lastrowid 
        # await db.execute(query, self.asdict())
        # async with db.execute("SELECT last_insert_rowid()") as cur:
        #     res = await cur.fetchone()
        #     self.id = (await cur.fetchone())[0]
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
    async def selectFromId(cls, db: aiosqlite.Connection, id: int) -> "Status":
        query = f"""
        SELECT * FROM {Status}
        WHERE id = ?
        """
        db.row_factory = Status.row_factory # pyright:ignore reportAttributeAccessIssue
        async with db.execute(query, (id,)) as cur:
            res = await cur.fetchone()
        return res
    
    @classmethod
    async def selectRandom(cls, db: aiosqlite.Connection) -> "Status":
        query = f"""
        SELECT * FROM {Status}
        WHERE id IN (SELECT id FROM {Status} ORDER BY RANDOM() LIMIT 1)
        """
        db.row_factory = Status.row_factory
        async with db.execute(query) as cur:
            res = await cur.fetchone()
        return res
    
    async def delete(self, db: aiosqlite.Connection) -> "Status":
        query = f"""
        DELETE FROM {Status}
        WHERE id = :id
        RETURNING *
        """
        db.row_factory = Status.row_factory # pyright:ignore reportAttributeAccessIssue
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res
        
    
    @classmethod
    async def deleteFromId(cls, db: aiosqlite.Connection, id: int) -> "Status":
        query = f"""
        DELETE FROM {Status}
        WHERE id = ?
        RETURNING *
        """
        db.row_factory = Status.row_factory
        async with db.execute(query, (id,)) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, limit: int=10, offset: int=0) -> list["Status"]:
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
        await self.bot.dbman.setup(table_group=__name__, 
                                   ignore_schema_updates=self.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.config.ignore_trigger_updates,
                                   drop_tables=self.config.drop_tables)
        if self.bot.is_ready():
            await self.on_ready()
    
    @commands.Cog.listener()
    async def on_ready(self):
        async with self.bot.dbman.conn() as db:
            status_id = await PersistentSettings.selectValue(db, key="status_id", default_value=0)
            status_data = await Status.selectFromId(db, id=status_id)
            cycle_status = await PersistentSettings.selectValue(db, key="cycle_status", default_value=0)
            cycle_status_interval = await PersistentSettings.selectValue(db, key="cycle_status_interval", default_value=60)
        if status_data is not None:
            await self.bot.change_presence(activity=status_data.toDiscordActivity())
        if cycle_status == 1:
            self.cycle_status.change_interval(minutes=cycle_status_interval)
            self.cycle_status.start()
        
    # async def change_activity(self, status: Status, persist: bool=True):
    #     await logger.info(f"Changing Activity")
    #     await self.bot.change_presence(activity=status.toDiscordActivity())
    #     if persist:
    #         async with self.bot.dbman.conn() as db:
    #             await PersistentSettings("status_id", value=status.id).upsert(db)
    #             await db.commit()
    #     await logger.info(f"Changed Activity to: {status}")

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
            await PersistentSettings(key="status_id", value=status_data.id).upsert(db)
            await db.commit()
        await self.bot.change_presence(activity=status_data.toDiscordActivity())
        logger.info(f"Changed Actvity to: {status_data}")
        await respond(interaction, "Updated status", delete_after=3)
    
    @set_group.command(name="random", description="Sets the current status from an existing id")
    async def set_random(self, interaction: Interaction):
        await respond(interaction, ephemeral=True)
        async with self.bot.dbman.conn() as db:
            status_data = await Status.selectRandom(db)
            if status_data is None:
                raise errors.CustomCheck("There are no statuses to switch to")
            await PersistentSettings(key="status_id", value=status_data.id).upsert(db)
            await db.commit()
        await self.bot.change_presence(activity=status_data.toDiscordActivity())
        logger.info(f"Changed Actvity to: {status_data}")
        await respond(interaction, "Updated status", delete_after=3)

    @app_commands.command(name="delete", description="Sets the current status from an existing id")
    async def delete_from_id(self, interaction: Interaction, id: int):
        await respond(interaction, ephemeral=True)
        async with self.bot.dbman.conn() as db:
            status_data = await Status.deleteFromId(db, id=id)
            await db.commit()
        if status_data is None:
            raise errors.CustomCheck("There is no status with that id")
        await respond(interaction, "Updated status", delete_after=3)

    @temp_group.command(name="custom", description="sets the bot's custom status without saving it")
    async def temp_custom(self, interaction: Interaction, status: str=None, emoji: str=None):
        await respond(interaction, ephemeral=True) 
        if not (status or emoji):
            raise errors.CustomCheck("You need to pass either a status or emoji")
        status_data = Status(name=status, emoji=emoji)
        await self.bot.change_presence(activity=status_data.toDiscordActivity())
        logger.info(f"Changed Actvity to: {status_data}")
        await respond(interaction, "Updated status", delete_after=3)
        
    @app_commands.command(name="refresh", description="Sets the status to the last save status")
    async def refresh(self, interaction: Interaction):
        await respond(interaction, ephemeral=True)
        async with self.bot.dbman.conn() as db:
            id = (await PersistentSettings.selectValue(db, key="status_id")).value or 0
            status = await Status.selectFromId(db, id=id)
        if status is not None:
            await self.bot.change_presence(activity=status.toDiscordActivity())
            logger.info(f"Changed Actvity to default: {status}")

        
    @app_commands.command(name="view-all", description="See a list of all saved statuses")
    async def view_all(self, interaction: Interaction):
        message = await respond(interaction)
        async def callback(irxn: Interaction, state: ScrollerState) -> tuple[str, int, int]:
            dbman = self.bot.dbman
            offset = state.offset
            async with dbman.conn() as db:
                count = await Status.selectCount(db)
                if offset * 10 > count:
                    offset = count // 10
                items: list[Status] = await Status.selectValue(db, limit=10, offset=offset*10)
            
            reps = []
            for i, status in enumerate(items):
                # index = i + 1 + offset * 10
                temp = f"{acstr(status.id, 6)} {acstr(status.name, 32)} {acstr(status.emoji, 8)}"
                reps.append(temp)

            header = f"{acstr('ID', 6)} {acstr('Status', 32)} {acstr('Emoji', 8)}"
            body = "\n".join(reps)
            content = f"```swift\n{header}\n---\n{body}\n---\n```"
            return content, 0, (count -1 ) // 10
        scroller = Scroller(message=message, user=interaction.user, page_callback=callback)
        await scroller.update(interaction)

    @tasks.loop()
    async def cycle_status(self):
        async with self.bot.dbman.conn() as db:
            status = await Status.selectRandom(db)
        if status is None:
            await self.cycle_status.stop()
        else:
            await self.bot.change_presence(activity=status.toDiscordActivity())
            await PersistentSettings("status_id", value=status.id).upsert(db)
            await db.commit()
            logger.info(f"Changed Activity to: {status}")

    @cycle_status.before_loop
    async def before(self):
        async with self.bot.dbman.conn() as db:
            await PersistentSettings(key="cycle_status", value=1).upsert(db)
            await PersistentSettings(key="cycle_status_interval", value=self.cycle_status.minutes).upsert(db)
            await db.commit()
        logger.info("Started cycling status")

    @cycle_status.after_loop
    async def after(self):
        async with self.bot.dbman.conn() as db:
            await PersistentSettings(key="cycle_status", value=0).upsert(db)
            await db.commit()
        logger.info(f"Stopped cycling status")
    
    @app_commands.command(name="cycle", description="Toggles cycling of the current status")
    @app_commands.describe(minutes=f"How long between status updates in minutes, max = {24 * 60} (24 Hours)")
    async def cycle(self, interaction: Interaction, minutes: Range[int, 15, 24 * 60]=60):
        await respond(interaction, ephemeral=True)
        if self.cycle_status.is_running():
            self.cycle_status.cancel()
            await respond(interaction, "Stopped cycling statuses")
        else:
            async with self.bot.dbman.conn() as db:
                count = await Status.selectCount(db)
            if count > 1:
                self.cycle_status.change_interval(minutes=minutes)
                self.cycle_status.start()
                await respond(interaction, "Started cycling statuses")
            else:
                await respond(interaction, "There are not enough statuses to cycle")

async def setup(bot: Kagami):
    await bot.add_cog(StatusCog(bot))

