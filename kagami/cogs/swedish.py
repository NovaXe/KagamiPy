from __future__ import annotations
from typing import override, cast, final
from dataclasses import dataclass
import random
import math

import aiosqlite
from aiosqlite import Connection

from io import BytesIO
from PIL import Image, ImageFile

import discord
from discord import app_commands, Message, Guild
from discord.app_commands import Choice, Transformer, Transform

from discord.app_commands.models import app_command_option_factory
from discord.ext import commands
from discord.ext.commands import GroupCog, Cog

from bot import Kagami, config

from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, BotEmoji, User, PersistentSettings

from common.logging import setup_logging
logger = setup_logging(__name__)

type Interaction = discord.Interaction[Kagami]

FISH_PREFIX = "sf"

@dataclass
class SwedishFishSettings(Table, schema_version=1, trigger_version=1):
    guild_id: int
    channel_id: int
    wallet_enabled: bool=True
    reactions_enabled: bool=False

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SwedishFishSettings}(
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            wallet_enabled INTEGER NOT NULL DEFAULT 1,
            reactions_enabled INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, channel_id),
            FOREIGN KEY (guild_id) REFERENCES {Guild}(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        await db.execute(query)

    @classmethod
    @override
    async def create_triggers(cls, db: Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {SwedishFishSettings}_insert_guild_before_insert
            BEFORE INSERT ON {SwedishFishSettings}
            BEGIN
                INSERT INTO {Guild}(id)
                VALUES (NEW.guild_id)
                ON CONFLICT(id) DO NOTHING;
            END;
            """
        ]
        for trigger in triggers:
            await db.execute(trigger)

    
    async def upsert(self, db: Connection) -> None:
        query = f"""
        INSERT INTO {SwedishFishSettings} (guild_id, channel_id, wallet_enabled, reactions_enabled)
        VALUES (:guild_id, :channel_id, :wallet_enabled, :reactions_enabled)
        ON CONFLICT (guild_id, channel_id)
        DO UPDATE SET wallet_enabled = :wallet_enabled AND reactions_enabled = :reactions_enabled
        """
        await db.execute(query, self.asdict())

    async def select(self, db: Connection) -> SwedishFishSettings | None:
        query = f"""
        SELECT * FROM {SwedishFishSettings}
        WHERE guild_id = :guild_id AND channel_id = :channel_id
        """
        db.row_factory = SwedishFishSettings.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res


@dataclass
class SwedishFish(Table, schema_version=2, trigger_version=1):
    name: str
    emoji_id: int
    value: int=0

    def probability(self) -> float:
        CF = 0.99
        R = random.random() * 0.10 + 0.95
        return max(math.pow(2, 1-self.value)* R, 1) * CF

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SwedishFish} (
            name TEXT NOT NULL,
            emoji_id INTEGER NOT NULL,
            value INTEGER NOT NULL DEFAULT 0,
            UNIQUE (name),
            FOREIGN KEY (emoji_id) REFERENCES {BotEmoji}(id),
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
        SELECT * FROM {SwedishFish}
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
        db.row_factory = aiosqlite.Row 
        async with db.execute(query, (f"%{name}%",)) as cur:
            res = await cur.fetchall()
        return [row["name"] for row in res] 

    async def upsert(self, db: Connection) -> None:
        query = f"""
            INSERT INTO {SwedishFish} (name, emoji_id, value)
            VALUES (:name, :emoji_id, :value)
            ON CONFLICT (name)
            DO UPDATE SET emoji_id = :emoji_id, value = :value
        """
        await db.execute(query, self.asdict())

    async def delete(self, db: Connection) -> None:
        query = f"""
        DELETE FROM {SwedishFish}
        WHERE name = ?
        """
        await db.execute(query, (self.name,))

@dataclass
class FishWallet(Table, schema_version=1, trigger_version=1):
    user_id: int
    guild_id: int
    fish_id: int
    count: int=0

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {FishWallet} (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            fish_id INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (user_id, guild_id, fish_id),
            FOREIGN KEY (fish_id) REFERENCES {SwedishFish}(emoji_id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            FOREIGN KEY (user_id) REFERENCES {User}(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            FOREIGN KEY (guild_id) REFERENCES {SwedishFishSettings}(guild_id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        await db.execute(query)

    @classmethod
    @override
    async def create_triggers(cls, db: aiosqlite.Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {FishWallet}_insert_settings_before_insert
            BEFORE INSERT ON {FishWallet}
            BEGIN
                INSERT INTO {SwedishFishSettings}(id)
                VALUES (NEW.guild_id)
                ON CONFLICT(id) DO NOTHING;
            END;
            """
        ]
        for trigger in triggers:
            await db.execute(trigger)

    @override
    async def upsert(self, db: aiosqlite.Connection) -> None:
        query = f"""
        INSERT INTO {FishWallet} (user_id, guild_id, fish_id, count)
        VALUES (:user_id, guild_id, fish_id, count)
        ON CONFLICT (user_id, guild_id, fish_id)
        DO UPDATE SET count = :count
        """
        return await super().insert(db)

    @classmethod
    async def selectAll(cls, db: Connection, user_id: int, guild_id: int=0, fish_id: int=0) -> list[FishWallet]:
        """
        guild_id == 0 gives across all servers
        fish_id == 0 gives all fish
        """
        query = f"""
        SELECT * FROM {FishWallet}
        WHERE user_id = :user_id
        AND CASE WHEN :guild_id != 0
            THEN guild_id = :guild_id
            ELSE 1
            END
        AND CASE WHEN :fish_id != 0
            THEN fish_id = :fish_id
            ELSE 1
            END
        """
        params = {"user_id": user_id, "guild_id" : guild_id, "fish_id": fish_id}
        db.row_factory = FishWallet.row_factory
        async with db.execute(query, params) as cur:
            res = await cur.fetchall()
        return res
    
    async def select(self, db: Connection) -> FishWallet:
        """
        Returns an updated version of the current row
        """
        query = f"""
        SELECT * FROM {FishWallet}
        WHERE user_id = :user_id
        AND CASE WHEN :guild_id != 0
            THEN guild_id = :guild_id
            ELSE 1
            END
        AND CASE WHEN :fish_id != 0
            THEN fish_id = :fish_id
            ELSE 1
            END
        """
        db.row_factory = FishWallet.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    async def totalValue(self, db: Connection) -> int:
        """
        Gives the total value based off of the current row instance details
        Follows similar selection rules from selectAll
        """
        query = f"""
        SELECT fw.fish_id, fw.count, sf.value, (fw.count * sf.vlaue) as t_value
        SELECT Coalesce(value) FROM {FishWallet} as fw
        INNER JOIN {SwedishFish} as sf
            ON fw.fish_id = sf.emoji_id
        WHERE user_id = :user_id
        AND CASE WHEN :guild_id != 0
            THEN guild_id = :guild_id
            ELSE 1
            END
        AND CASE WHEN :fish_id != 0
            THEN fish_id = :fish_id
            ELSE 1
            END
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res["t_value"] if res else 0


class FishTransformer(Transformer):
    pass

class FishTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction, value: str) -> list[Choice[str]]: # pyright: ignore [reportIncompatibleMethodOverride]
        async with interaction.client.dbman.conn() as db:
            names = await SwedishFish.selectLikeNames(db, value)
        choices = [Choice(name=name, value=name) for name in names][:25]
        return choices

    async def transform(self, interaction: Interaction, value: str) -> SwedishFish: # pyright: ignore [reportIncompatibleMethodOverride]
        async with interaction.client.dbman.conn() as db:
            result = await SwedishFish.selectFromName(db, value)
        return result

VALID_FILE_TYPES = ("png", "jpg", "jpeg", "webp")

@app_commands.guilds(discord.Object(config.admin_guild_id))
class SwedishAdmin(GroupCog, group_name="sf"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    async def cog_load(self) -> None:
        await self.bot.dbman.setup(table_group=__name__)


    @app_commands.command(name="add", description="adds a new fish")
    async def add(self, interaction: Interaction, name: Transform[SwedishFish | None, FishTransformer], image: discord.Attachment, value: int):
        await respond(interaction)
        logger.debug(f"add_new: {image.content_type=}")
        if image.content_type is None:
            await respond(interaction, "Missing or unknown content type")
            return
        ct_fields = image.content_type.split("/")

        if ct_fields[0] != "image":
            await respond(interaction, f"Invalid content type: {ct_fields[0]} is not image")
            return
        elif ct_fields[1].lower() not in VALID_FILE_TYPES:
            await respond(interaction, f"Invalid file type: {ct_fields[1]} is not {", ".join(VALID_FILE_TYPES[:-1])} or {VALID_FILE_TYPES[-1]}")
            return
        
        if name is not None:
            await respond(interaction, "There is already a fish with that name")
            return

        new_fish_name = interaction.namespace["name"]
        # elif image.size > 256_000: # bytes
        #     await respond(interaction, "Image is larger than 256kB")
        
        image_data = await image.read()
        try:
            emoji = await self.bot.create_application_emoji(name=f"{FISH_PREFIX}_{new_fish_name}", image=image_data)
        except discord.HTTPException as e:
            await respond(interaction, f"`{e.text}`")
            return
            
        new_fish = SwedishFish(name=new_fish_name, emoji_id=emoji.id, value=value)
        
        async with self.dbman.conn() as db:
            await BotEmoji.insertFromDiscord(db, emoji)
            await new_fish.upsert(db)
            await db.commit()
        await respond(interaction, f"Added Swedish Fish: {new_fish_name}")

    @app_commands.command(name="edit", description="edits an existing fish")
    async def edit(self, interaction: Interaction, fish: Transform[SwedishFish | None, FishTransformer], image: discord.Attachment | None=None, value: int | None=None) -> None:
        await respond(interaction)
        if image is not None:





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


CHAT_MODES = ("fish", "swedish fish", "reddit")


async def get_sf_reaction(message: discord.Message) -> str
    pass


class Swedish(GroupCog, group_name="swedish-fish"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @override
    async def cog_load(self) -> None:
        pass


    async def on_message(self, message: discord.Message) -> None:
        assert message.guild is not None
        async with self.dbman.conn() as db:
            states = {mode: await ChatMode(mode, message.guild.id).select(db) for mode in CHAT_MODES}

            if states["swedish fish"]:
                pass
            if states["reddit"]:
                pass
        

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
        await respond(interaction, f"{mode} mode is now {r}")
    


async def setup(bot: Kagami) -> None:
    await bot.add_cog(Swedish(bot))
    await bot.add_cog(SwedishAdmin(bot))


