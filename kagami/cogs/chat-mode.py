from __future__ import annotations
from typing import override
from dataclasses import dataclass
import aiosqlite

from io import BytesIO
from aiosqlite import Connection
from PIL import Image, ImageFile

from discord import app_commands, Message, Guild

from discord.ext import commands
from discord.ext.commands import GroupCog, Cog

from bot import Kagami

from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings

@dataclass
class BotEmoji(Table, schema_version=1, trigger_version=1):
    id: int
    name: str | None
    group_name: str | None
    image_data: bytes | None

    # def get_image(self) -> ImageFile.ImageFile:
    #     image: ImageFile.ImageFile | None = None 
    #     if self.image_data is not None:
    #         image = Image.open(BytesIO(self.image_data))
    #     return image

    def get_image(self) -> BytesIO | None:
        if self.image_data is not None:
            return BytesIO(self.image_data)
        else:
            return None

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
            CREATE TABLE IF NOT EXISTS {BotEmoji}(
            id INTEGER NOT NULL,
            name TEXT,
            group_name TEXT,
            image_data BLOB,
            PRIMARY KEY (id)
        )
        """
        await db.execute(query)

    @classmethod
    async def selectFromID(cls, db: Connection, id: int) -> BotEmoji:
        query = f"""
        SELECT * FROM {BotEmoji}(id, name, group_name, image_data)
        WHERE id = ?
        """
        db.row_factory = BotEmoji.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query, (id,)) as cur:
            res = await cur.fetchone()
        return res # pyright: ignore[reportReturnType]

    async def insert(self, db: Connection):
        query = f"""
            INSERT OR IGNORE INTO {BotEmoji} (id, name, group_name, image_data)
            VALUES (:id, :name, :group_name, :image_data)
        """
        await db.execute(query, self.asdict())


class SwedishFish(Table, schema_version=1, trigger_version=1):
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
            CREATE TABLE IF NOT EXISTS {SwedishFish}(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            emoji_id INTEGER NOT NULL,
            emoji_name TEXT,
            UNIQUE(name)
        )
        """
        await db.execute(query)


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


