from __future__ import annotations
from typing import override
from dataclasses import dataclass
import aiosqlite

from io import BytesIO
from aiosqlite import Connection
from PIL import Image, ImageFile

import discord
from discord import app_commands, Message, Guild

from discord.ext import commands
from discord.ext.commands import GroupCog, Cog

from bot import Kagami

from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings

# @dataclas
# class BotEmojiGroup(Table, schema_version=1, trigger_version=1):
#     name: str
#     alias: str
# 
#     @classmethod
#     async def create_table(cls, db: aiosqlite.Connection):
#         query = f"""
#         CREATE TABLE IF NOT EXISTS {BotEmojiGroup}(
#             name TEXT NOT NULL
#             alias TEXT NOT NULL
#         )
#         """
#         return await super().create_table(db)

@dataclass
class BotEmoji(Table, schema_version=1, trigger_version=1):
    id: int
    name: str
    # prefix: str
    image_data: bytes

    # def get_image(self) -> ImageFile.ImageFile:
    #     image: ImageFile.ImageFile | None = None 
    #     if self.image_data is not None:
    #         image = Image.open(BytesIO(self.image_data))
    #     return image

    def get_image_file(self) -> discord.File | None:
        if self.image_data is not None:
            with BytesIO(self.image_data) as f:
                file = discord.File(fp=f)
            return file
        else:
            return None

    # def get_name(self) -> str:
    #     return f"{self.prefix}_{self.name}"

    @classmethod
    async def from_discord(cls, emoji: discord.Emoji) -> BotEmoji:
        data = await emoji.read()
        return BotEmoji(id=emoji.id, name=emoji.name, image_data=data)

    @classmethod
    async def create_table(cls, db: Connection):
        # query = f"""
        #     CREATE TABLE IF NOT EXISTS {BotEmoji}(
        #     id INTEGER NOT NULL,
        #     name TEXT NOT NULL,
        #     group TEXT NOT NULL DEFAULT '',
        #     image_data BLOB,
        #     PRIMARY KEY (id)
        # )
        # """
        query = f"""
            CREATE TABLE IF NOT EXISTS {BotEmoji}(
            id INTEGER NOT NULL,
            name TEXT NOT NULL,
            image_data BLOB,
            PRIMARY KEY (id),
            UNIQUE (name)
        )
        """
        await db.execute(query)

    @classmethod
    async def selectFromID(cls, db: Connection, id: int) -> BotEmoji:
        query = f"""
        SELECT * FROM {BotEmoji}(id, name, image_data)
        WHERE id = ?
        """
        db.row_factory = BotEmoji.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query, (id,)) as cur:
            res = await cur.fetchone()
        return res # pyright: ignore[reportReturnType]

    @override
    async def insert(self, db: Connection):
        query = f"""
            INSERT OR IGNORE INTO {BotEmoji} (id, name, group, image_data)
            VALUES (:id, :name, :image_data)
        """
        await db.execute(query, self.asdict())

    @override
    async def delete(self, db: Connection):
        query = f"""
            DELETE * FROM {BotEmoji}
            WHERE id = ?
        """
        await db.execute(query, (self.id,))


    @classmethod
    async def deleteFromID(cls, db: Connection, id: int):
        query = f"""
            DELETE * FROM {BotEmoji}
            WHERE id = ?
        """
        await db.execute(query, (id,))

    @classmethod
    async def insertFromDiscord(cls, db: Connection, emoji: discord.Emoji) -> BotEmoji:
        converted = await BotEmoji.from_discord(emoji)
        await converted.insert(db)
        return converted

    


