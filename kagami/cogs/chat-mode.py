from __future__ import annotations
from typing import override, cast, final
from dataclasses import dataclass

import aiosqlite
from aiosqlite import Connection

from io import BytesIO
from PIL import Image, ImageFile

import discord
from discord import app_commands, Message, Guild
from discord.app_commands import Choice, Transformer, Transform

from discord.ext import commands
from discord.ext.commands import GroupCog, Cog

from bot import Kagami, config

from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, BotEmoji, User, PersistentSettings

from common.logging import setup_logging
logger = setup_logging(__name__)

type Interaction = discord.Interaction[Kagami]

@dataclass
class ChatMode(Table, schema_version=2, trigger_version=1):
    name: str
    guild_id: int
    enabled: bool=False

    @classmethod
    @override
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {ChatMode} (
            name TEXT NOT NULL,
            guild_id INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (name, guild_id)
        )
        """
        await db.execute(query)

    async def select(self, db: Connection) -> ChatMode:
        query = f"""
        SELECT * FROM {ChatMode}
        WHERE name = :name AND guild_id = :guild_id
        """
        db.row_factory = ChatMode.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def selectAll(cls, db: Connection, guild_id: int) -> list[ChatMode]:
        query = f"""
        SELECT * FROM {ChatMode}
        WHERE guild_id = :guild_id
        """
        db.row_factory = ChatMode.row_factory
        async with db.execute(query, (guild_id,)) as cur:
            res = await cur.fetchall()
        return res

    async def upsert(self, db: Connection) -> None:
        query = f"""
        INSERT INTO {ChatMode} (name, guild_id, enabled)
        VALUES (:name, :guild_id, :enabled)
        ON CONFLICT (name, guild_id)
        DO UPDATE SET enabled = :enabled
        """
        await db.execute(query, self.asdict())

# CHAT_MODES = ("fish", "reddit")
CHAT_MODES = ("fish", "reddit")

class SimpleReactionModes(GroupCog, group_name="chat"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @override
    async def cog_load(self) -> None:
        await self.dbman.setup(__name__)

    @GroupCog.listener()
    async def on_message(self, message: discord.Message) -> None:
        assert message.guild is not None
        async with self.dbman.conn() as db:
            states = {mode: await ChatMode(mode, message.guild.id).select(db) for mode in CHAT_MODES}
            logger.debug(f"on_message: states: {states}")
            if (f:=states["fish"]) and f.enabled:
                await message.add_reaction("🐟")
            if (r:=states["reddit"]) and r.enabled:
                await message.add_reaction("👍")
                await message.add_reaction("👎")
        

    # async def chat_modes_autocomplete(self, interaction: Interaction, value: str) -> list[Choice[str]]:
    #     choices = [Choice(name=mode, value=mode) for mode in CHAT_MODES][:25]
    #     return choices


    # @app_commands.autocomplete(mode=chat_modes_autocomplete)
    @app_commands.command(name="mode", description="toggle a chat mode") 
    @app_commands.choices(mode=[Choice(name=mode, value=mode) for mode in CHAT_MODES][:25])
    async def mode(self, interaction: Interaction, mode: Choice[str]) -> None:
        await respond(interaction)
        assert interaction.guild is not None
        async with self.dbman.conn() as db:
            state = ChatMode(mode.name, interaction.guild.id, False)
            state = new if (new:=await state.select(db)) else state
            state.enabled = not bool(state.enabled)
            await state.upsert(db)
            await db.commit()
        r = "enabled" if state.enabled else "disabled"
        await respond(interaction, f"{mode.name} mode is now {r}")
    


async def setup(bot: Kagami) -> None:
    await bot.add_cog(SimpleReactionModes(bot))


