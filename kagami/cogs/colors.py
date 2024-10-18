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





class ColorCog(GroupCog, name="color"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman
    
    
    async def cog_load(self):
        pass
    
    async def on_ready(self):
        pass


async def setup(bot: Kagami):
    bot.add_cog(ColorCog(bot))

