from typing import override
import aiosqlite

from discord import app_commands, Message, Guild

from discord.ext import commands
from discord.ext.commands import GroupCog, Cog

from bot import Kagami

from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings


# class BotEmoji(Table, schema_version=1, trigger_version=1):
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#             CREATE TABLE IF NOT EXISTS {BotEmoji}(
#             id INTEGER NOT NULL,
#             name TEXT,
#             group_name TEXT,
#             PRIMARY KEY (id)
#         )
#         """
#         await db.execute(query)

# class SwedishFish(Table, schema_version=1, trigger_version=1):
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#             CREATE TABLE IF NOT EXISTS {SwedishFish}(
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             name TEXT NOT NULL,
#             emoji_id INTEGER NOT NULL,
#             emoji_name TEXT,
#             UNIQUE(name)
#         )
#         """
#         await db.execute(query)

# class Fishtistics(Table, schema_version=1, trigger_version=1):
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#             CREATE TABLE IF NOT EXISTS {Fishtistics}(
#             user_id INTEGER NOT NULL,
#             guild_id INTEGER NOT NULL default 0,
#             fish_id INTEGER NOT NULL,
#             PRIMARY KEY(user_id, guild_id),
#             FOREIGN KEY (fish_id) REFERENCES {SwedishFish}.id ON UPDATE CASCADE ON DELETE CASCADE
#         )
#         """
#         await db.execute(query)

class ChatCog(GroupCog, group_name="chat"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman

    @override
    async def cog_load(self) -> None:
        pass


    @GroupCog.listener()
    async def on_message(self):
        pass
    


async def setup(bot: Kagami) -> None:
    await bot.add_cog(ChatCog(bot))


