from __future__ import annotations
from typing import override, cast
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

from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings
from common.emoji import BotEmoji


type Interaction = discord.Interaction[Kagami]


FISH_PREFIX = "SF"

@dataclass
class SwedishFish(Table, schema_version=1, trigger_version=1):
    name: str
    emoji_id: int
    value: int

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SwedishFish}(
            name TEXT NOT NULL,
            emoji_id INTEGER NOT NULL,
            UNIQUE (name),
            FOREIGN KEY (emoji_id) REFERENCES {BotEmoji}.id
        )
        """
        await db.execute(query)

    @classmethod
    async def create_triggers(cls, db: Connection):
        triggers = [""]
        for trigger in triggers:
            await db.execute(trigger)

    @classmethod
    async def selectFromName(cls, db: Connection, name: str) -> SwedishFish:
        query = f"""
        SELECT * FROM {SwedishFish}(name, emoji_id, value)
        WHERE name = ?
        """
        db.row_factory = SwedishFish.row_factory
        async with db.execute(query, (name,)) as cur:
            res = await cur.fetchone()
        return res 

    @classmethod
    async def selectLikeNames(cls, db: Connection, name: str) -> list[str]:
        query = f"""
        SELECT name FROM {SwedishFish}
        WHERE (name like ?)
        """
        db.row_factory = Row 
        async with db.execute(query, (f"%{name}%",)) as cur:
            res = await cur.fetchall()
        return [row["name"] for row in res] 

    async def upsert(self, db: Connection) -> None:
        query = f"""
            INSERT INTO {SwedishFish}(id, name, value)
            VALUES (:id, :name, :value)
            ON CONFLICT (name)
            DO UPDATE SET id = :id, value = :value
        """
        await db.execute(query, self.asdict())

    async def delete(self, db: Connection) -> None:
        query = f"""
        DELETE * FROM {SwedishFish}
        WHERE name = ?
        """
        await db.execute(query, (self.name,))


class SwedishFishStatistics(Table, schema_version=1, trigger_version=1):
    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SwedishFishStatistics}(
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            fish_id INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (user_id, guild_id, fish_id),
            FOREIGN KEY (fish_id) REFERENCES {SwedishFish}.id 
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """
        await db.execute(query)

@dataclass
class ChatMode:
    name: str


class FishTransformer(Transformer):
    pass

class FishTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction, value: str) -> list[Choice[str]]: # pyright: ignore [reportIncompatibleMethodOverride]
        async with interaction.client.dbman.conn() as db:
            names = await SwedishFish.selectLikeNames(db, value)
        choices = [Choice(name=name, value=value) for name in names][:25]
        return choices

    async def transform(self, interaction: Interaction, value: str) -> SwedishFish: # pyright: ignore [reportIncompatibleMethodOverride]
        async with interaction.client.dbman.conn() as db:
            result = await SwedishFish.selectFromName(db, value)
        return result

@app_commands.guilds(discord.Object(config.admin_guild_id))
class SwedishCog(GroupCog, group_name="sf"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @app_commands.command(name="add-new", description="adds a new fish")
    @app_commands.rename(fish="new name")
    async def add_new(self, interaction: Interaction, fish: Transform[SwedishFish | None, FishTransformer], image: discord.Attachment, value: int=0):
        await respond(interaction)
        if image.content_type not in ("JPEG", "PNG", "GIF", "WEBP"):
            await respond(interaction, "Invalid Filetype")
            return
        
        if fish is not None:
            await respond(interaction, "There is already a fish with that name")
            return

        new_fish_name = interaction.namespace.fish
        # elif image.size > 256_000: # bytes
        #     await respond(interaction, "Image is larger than 256kB")
        
        image_data = await image.read()
        emoji = await self.bot.create_application_emoji(name=f"{FISH_PREFIX}_{new_fish_name}", image=image_data)
        new_fish = SwedishFish(name=new_fish_name, emoji_id=emoji.id, value=value)
        
        async with self.dbman.conn() as db:
            await BotEmoji.insertFromDiscord(db, emoji)
            await new_fish.upsert(db)
            await db.commit()

        await respond(interaction, f"Added fish: {new_fish_name}")

    @app_commands.command(name="delete", description="deletes fish")
    async def delete(self, interaction: Interaction, fish: Transform[SwedishFish | None, FishTransformer]) -> None:
        await respond(interaction)

        if fish is None:
            await respond(interaction, "That fish does not exist")
            return
        
        async with self.dbman.conn() as db:
            await fish.delete(db)
            await BotEmoji.deleteFromID(db, fish.emoji_id)
            await db.commit()

        await respond(interaction, f"Deleted fish: {fish.name}")




class ChatCog(GroupCog, group_name="chat"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @override
    async def cog_load(self) -> None:
        pass


    @GroupCog.listener()
    async def on_message(self):
        pass

    async def chat_modes_autocomplete(self, interaction: Interaction, value: str) -> list[Choice[str]]:
        chat_modes = ["fish", "swedish fish", "reddit"]
        choices = [Choice(name=mode, value=mode) for mode in chat_modes][:25]
        return choices


    @app_commands.command(name="mode", description="toggle a chat mode") 
    @app_commands.autocomplete(mode=chat_modes_autocomplete)
    async def mode(self, interaction: Interaction, mode: str) -> None:
        await respond(interaction, mode)
    


async def setup(bot: Kagami) -> None:
    await bot.add_cog(ChatCog(bot))


