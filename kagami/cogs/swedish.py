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
from discord import app_commands, Message, Guild, channel
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

    @classmethod
    async def selectCurrent(cls, db: Connection, guild_id: int, channel_id: int) -> SwedishFishSettings:
        channel_settings = await SwedishFishSettings(guild_id, channel_id).select(db)
        guild_settings = await SwedishFishSettings(guild_id, 0).select(db)
        settings = SwedishFishSettings(guild_id, channel_id)
        if channel_settings is not None:
            settings = channel_settings
        elif guild_settings is not None:
            settings = guild_settings
        return settings


@dataclass
class SwedishFish(Table, schema_version=2, trigger_version=1):
    name: str
    emoji_id: int
    value: int=0

    def probability(self) -> float:
        CF = 0.99
        R = random.random() * 0.10 + 0.95
        return max(math.pow(2, 1-self.value)* R, 1) * CF

    def roll(self) -> bool:
        return random.random() <= self.probability()

    async def get_emoji(self, db: Connection) -> BotEmoji:
        "The same as calling BotEmoji.selectFromID"
        emoji = await BotEmoji.selectFromID(db, self.emoji_id)
        if emoji is None:
            raise ValueError(f"Swedish Fish `{self.name}` is missing an emoji, {self.emoji_id} does not exist in {BotEmoji}")
        return emoji

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SwedishFish} (
            name TEXT NOT NULL,
            emoji_id INTEGER NOT NULL,
            value INTEGER NOT NULL DEFAULT 0,
            UNIQUE (name),
            FOREIGN KEY (emoji_id) REFERENCES {BotEmoji}(id)
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

    @classmethod
    async def selectAll(cls, db: Connection) -> list[SwedishFish]:
        query = f"""
        SELECT * FROM {SwedishFish}
        """
        db.row_factory = SwedishFish.row_factory
        res = await db.execute_fetchall(query)
        return res

    @classmethod
    async def gamble(cls, db: Connection) -> list[SwedishFish]:
        query = f"""
        SELECT * FROM {SwedishFish}
        """
        db.row_factory = SwedishFish.row_factory
        fish: SwedishFish
        out: list[SwedishFish] = []
        async with db.execute(query) as cur:
            async for fish in cur:
                out.append(fish) if fish.roll() else ...
        return out

    # @classmethod
    # async def gamble(cls, db: Connection) -> list[tuple()]
    #     query = f"""
    #     SELECT emoji_id, emoji_name, 
    #     FROM {SwedishFish} as sf
    #     INNER JOIN {BotEmoji} as be
    #         ON sf.emoji_id = be.id
    #     """

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
class FishWallet(Table, schema_version=2, trigger_version=1):
    user_id: int
    guild_id: int
    fish_name: int
    count: int=0

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {FishWallet} (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            fish_name INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (user_id, guild_id, fish_name),
            FOREIGN KEY (fish_name) REFERENCES {SwedishFish}(name)
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
        INSERT INTO {FishWallet} (user_id, guild_id, fish_name, count)
        VALUES (:user_id, guild_id, fish_name, count)
        ON CONFLICT (user_id, guild_id, fish_name)
        DO UPDATE SET count = :count
        """
        return await super().insert(db)

    @classmethod
    async def selectAll(cls, db: Connection, user_id: int, guild_id: int=0, fish_name: str | None=None) -> list[FishWallet]:
        """
        guild_id == 0 gives across all servers
        fish_name is None gives all fish
        """
        query = f"""
        SELECT * FROM {FishWallet}
        WHERE user_id = :user_id
        AND CASE WHEN :guild_id != 0
            THEN guild_id = :guild_id
            ELSE 1
            END
        AND CASE WHEN :fish_name IS NOT NULL
            THEN fish_name = :fish_name
            ELSE 1
            END
        """
        params = {"user_id": user_id, "guild_id" : guild_id, "fish_name": fish_name}
        db.row_factory = FishWallet.row_factory
        async with db.execute(query, params) as cur:
            res = await cur.fetchall()
        return res
    
    async def select(self, db: Connection) -> FishWallet:
        """
        Returns an updated version of the current row
        guild_id == 0 => all servers
        fish_name is None => all fish
        """
        query = f"""
        SELECT * FROM {FishWallet}
        WHERE user_id = :user_id
        AND CASE WHEN :guild_id != 0
            THEN guild_id = :guild_id
            ELSE 1
            END
        AND CASE WHEN :fish_name IS NOT NULL
            THEN fish_name = :fish_name
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
        SELECT fw.fish_name, fw.count, sf.value, (fw.count * sf.vlaue) as t_value
        SELECT Coalesce(value) FROM {FishWallet} as fw
        INNER JOIN {SwedishFish} as sf
            ON fw.fish_name = sf.name
        WHERE user_id = :user_id
        AND CASE WHEN :guild_id != 0
            THEN guild_id = :guild_id
            ELSE 1
            END
        AND CASE WHEN :fish_name IS NOT NULL
            THEN fish_name = :fish_name
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
        if fish is None:
            await respond(interaction, "There is no fish with that name")
            return
        async with self.dbman.conn() as db:
            if image is not None:
                old_emoji = await fish.get_emoji(db)
                image_data = await image.read()
                await old_emoji.delete_discord(self.bot)
                await old_emoji.delete(db)
                emoji = await self.bot.create_application_emoji(name=f"{FISH_PREFIX}_{fish.name}", image=image_data)
                await BotEmoji.insertFromDiscord(db, emoji)
                fish.emoji_id = emoji.id
            fish.value = value if value else fish.value
            await fish.upsert(db)

        await respond(interaction, f"Editted the fish")


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



class Swedish(GroupCog, group_name="swedish-fish"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @override
    async def cog_load(self) -> None:
        pass


    async def on_message(self, message: discord.Message) -> None:
        assert message.guild is not None
        default_settings = SwedishFishSettings(message.guild.id, 0)
        async with self.dbman.conn() as db:
            settings = await SwedishFishSettings.selectCurrent(db, message.guild.id, message.channel.id)
            #  or default_settings
            successes = await SwedishFish.gamble(db)
            if settings.wallet_enabled:    
                # successes = await SwedishFish.gamble(db)
                for s in successes:
                    default = FishWallet(message.author.id, message.guild.id, s.emoji_id)
                    old = await default.select(db) or default
                    old.count +=1 
                    await old.upsert(db)
            if settings.reactions_enabled:
                for s in successes:
                    bot_emoji = await s.get_emoji(db)
                    try:
                        emoji = await bot_emoji.fetch_discord(self.bot)
                        await message.add_reaction(emoji)
                    except discord.HTTPException as e:
                        logger.error(f"Discord emoji for swedish fish {s.name} with id {s.emoji_id} could not be retrieved") 
        

    @app_commands.command(name="toggle-reactions", description="toggles the visible reactions, users can still collect fish")
    async def toggle_reactions(self, interaction: Interaction, guildwide: bool=True) -> None:
        await respond(interaction)
        assert interaction.guild is not None
        assert interaction.channel is not None
        channel_id = 0 if guildwide else interaction.channel.id
        default = SwedishFishSettings(interaction.guild.id, channel_id)
        async with self.dbman.conn() as db:
            state = await default.select(db) or default
            state.reactions_enabled = not state.reactions_enabled
            await state.upsert(db)
            await db.commit()
        r = "enabled, you can now see the fish" if state.wallet_enabled else "disabled, you can no longer see the fish"
        await respond(interaction, f"The reactions have been {r}")

    @app_commands.command(name="toggle-wallet", description="this toggles the wallet that allows users to collect fish, but reactions can still show up")
    async def toggle_reactions(self, interaction: Interaction, guildwide: bool=True) -> None:
        await respond(interaction)
        assert interaction.guild is not None
        assert interaction.channel is not None
        channel_id = 0 if guildwide else interaction.channel.id
        default = SwedishFishSettings(interaction.guild.id, channel_id)
        async with self.dbman.conn() as db:
            state = await default.select(db) or default
            state.wallet_enabled = not state.wallet_enabled
            await state.upsert(db)
            await db.commit()
        r = "enabled, you can collect fish again" if state.wallet_enabled else "disabled, no more collecting fish"
        await respond(interaction, f"The wallet has been {r}")


async def setup(bot: Kagami) -> None:
    await bot.add_cog(Swedish(bot))
    await bot.add_cog(SwedishAdmin(bot))


