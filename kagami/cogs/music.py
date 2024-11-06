from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Literal, List, Callable, Any
)
import PIL as pillow
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
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


class MusicCog(GroupCog, name="m"): 
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


    @app_commands.command(name="join", description="Starts a music session in the voice channel")
    async def join(self, interaction: Interaction) -> None:
        raise NotImplementedError

    @app_commands.command(name="leave", description="Ends the current session")
    async def leave(self, interaction: Interaction) -> None:
        raise NotImplementedError

    @app_commands.command(name="play", description="Queue a track to be played in the voice channel")
    @app_commands.describe(track="search query / song link / playlist link")
    async def play(self, interaction: Interaction, track: str) -> None:
        raise NotImplementedError


    @app_commands.command(name="skip", description="Skip to the next track in the queue")
    async def skip(self, interaction: Interaction, count: int=1) -> None:
        raise NotImplementedError

    @app_commands.command(name="back", description="Skip to the previous track in the queue")
    async def back(self, interaction: Interaction, count: int=1) -> None:
        raise NotImplementedError

    @app_commands.command(name="view-queue", description="View all the tracks in the queue")
    async def view_queue(self, interaction: Interaction) -> None:
        raise NotImplementedError

    @app_commands.command(name="view-history", description="View all track in the history")
    async def view_history(self, interaction: Interaction) -> None:
        raise NotImplementedError




async def setup(bot: Kagami):
    bot.add_cog(MusicCog(bot))

