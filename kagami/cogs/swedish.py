from __future__ import annotations
from typing import override, cast, final, Any
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
        DO UPDATE SET 
            wallet_enabled = :wallet_enabled, 
            reactions_enabled = :reactions_enabled
        """
        await db.execute(query, self.asdict())

    async def delete(self, db: Connection) -> None:
        query = f"""
        DELETE FROM {SwedishFishSettings}
        WHERE guild_id = :guild_id AND channel_id = :channel_id
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

def prob_exp(value: float) -> float:
    CF = 0.99
    R = random.random() * 0.10 + 0.95
    return min(math.pow(2, 1-value)* R, 1) * CF

def prob_quad(value: float) -> float:
    CF = 0.99
    R = random.random() * 0.10 + 0.95
    return min(math.pow(value, -2)* R, 1) * CF

def prob_threehalfs(value: float) -> float:
    CF = 0.99
    R = random.random() * 0.10 + 0.95
    return min(math.pow(value, -1.5)* R, 1) * CF

def prob_fourfifths(value: float) -> float:
    CF = 0.99
    R = random.random() * 0.10 + 0.95
    return min(math.pow(value, -1.25)* R, 1) * CF

@dataclass
class SwedishFish(Table, schema_version=2, trigger_version=1):
    name: str
    emoji_id: int
    value: int=0

    

    def probability(self) -> float:
        return prob_threehalfs(self.value)

    def roll(self) -> bool:
        r = random.random()
        logger.debug(f"roll prob: ({r}, {self.probability()})")
        return r <= self.probability()

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
        ORDER BY value
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
class FishWallet(Table, schema_version=4, trigger_version=6):
    user_id: int
    guild_id: int
    fish_name: str | None
    count: int=0

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {FishWallet} (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            fish_name TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (user_id, guild_id, fish_name),
            FOREIGN KEY (fish_name) REFERENCES {SwedishFish}(name)
                ON UPDATE CASCADE ON DELETE CASCADE 
            FOREIGN KEY (user_id) REFERENCES {User}(id)
                ON UPDATE CASCADE ON DELETE CASCADE
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
                INSERT OR IGNORE INTO {SwedishFishSettings}(guild_id, channel_id)
                VALUES (NEW.guild_id, 0);
            END;
            """
            # ON CONFLICT(guild_id, channel_id) DO NOTHING;
        ]
        for trigger in triggers:
            await db.execute(trigger)

    @override
    async def upsert(self, db: aiosqlite.Connection) -> None:
        query = f"""
        INSERT INTO {FishWallet} (user_id, guild_id, fish_name, count)
        VALUES (:user_id, :guild_id, :fish_name, :count)
        ON CONFLICT (user_id, guild_id, fish_name)
        DO UPDATE SET count = :count
        """
        await db.execute(query, self.asdict())

    @classmethod
    async def selectAll(cls, db: Connection, user_id: int, guild_id: int=0, fish_name: str | None=None) -> list[FishWallet]:
        """
        guild_id == 0 gives across all servers
        fish_name is None gives all fish
        """
        # SELECT * FROM {FishWallet}
        # WHERE user_id = :user_id
        # AND CASE WHEN :guild_id != 0
        #          THEN guild_id == :guild_id
        #          ELSE 1
        #     END
        # AND CASE WHEN :fish_name IS NOT NULL
        #          THEN fish_name == :fish_name
        #          ELSE 1
        #     END
        query = f"""
        SELECT * FROM {FishWallet}
        WHERE user_id = :user_id
        AND (:guild_id == 0 OR guild_id = :guild_id)
        AND (:fish_name IS NULL OR fish_name = :fish_name)
        """
        params = {"user_id": user_id, "guild_id" : guild_id, "fish_name": fish_name}
        db.row_factory = FishWallet.row_factory
        async with db.execute(query, params) as cur:
            res = await cur.fetchall()
        return res
    
    async def list(self, db: Connection) -> list[aiosqlite.Row]:
        """
        Returns data from the querying the pseudo row instance,
        name, emoji_name, emoji_id, value, count, total
        """
        query = f"""
        SELECT 
            sf.name as name, 
            be.name as emoji_name,
            be.id as emoji_id,
            sf.value as value,
            fw.count as count,
            sf.value * fw.count as total
        FROM {FishWallet} AS fw
        INNER JOIN {SwedishFish} AS sf
            ON sf.name = fw.fish_name
        INNER JOIN {BotEmoji} AS be
            ON sf.emoji_id = be.id
        WHERE (:guild_id = 0 OR guild_id = :guild_id)
        AND (:user_id = 0 OR user_id = :user_id)
        ORDER BY sf.value
        """
        db.row_factory = aiosqlite.Row
        logger.debug(f"FishWalle.list(self): {self=}")
        async with db.execute(query, self.asdict()) as cur:
            rows = await cur.fetchall()
        logger.debug(f"FishWallet.list(self): {len(list(rows))=}")
        return list(rows)

    
    async def select(self, db: Connection) -> FishWallet | None:
        """
        Returns an updated version of the current row
        guild_id == 0 => all servers
        fish_name is None => all fish
        """
        query = f"""
        SELECT * FROM {FishWallet}
        WHERE user_id = :user_id
        AND (:guild_id == 0 OR guild_id = :guild_id)
        AND (:fish_name IS NULL OR fish_name = :fish_name)
        """
        db.row_factory = FishWallet.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    async def totalValue(self, db: Connection) -> int:
        """
        DOESN"T WORK
        Gives the total value based off of the current row instance details
        Follows similar selection rules from selectAll
        """
        raise NotImplemented
        query = f"""
        SELECT fw.fish_name, fw.count, sf.value, fw.count * sf.value as value, Sum(value) as t_value
        FROM {FishWallet} as fw
        INNER JOIN {SwedishFish} as sf
            ON fw.fish_name = sf.name
        WHERE user_id = :user_id
        AND (:guild_id == 0 OR guild_id = :guild_id)
        AND (:fish_name IS NULL OR fish_name = :fish_name)
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
            await db.commit()

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

    @app_commands.command(name="list", description="lists the fish in chat")
    async def list(self, interaction: Interaction) -> None:
        await respond(interaction)
        async with self.dbman.conn() as db:
            all_fish = await SwedishFish.selectAll(db)
        out: list[str] = []
        for fish in all_fish:
            emoji = await (await fish.get_emoji(db)).fetch_discord(self.bot)
            out.append(f"{emoji} - {fish.name} - {fish.value}")
        await respond(interaction, "\n".join(out))



class Swedish(GroupCog, group_name="swedish-fish"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @override
    async def cog_load(self) -> None:
        await self.dbman.setup(__name__)

    @GroupCog.listener()
    async def on_message(self, message: discord.Message) -> None:
        assert message.guild is not None
        logger.debug("on_message: enter")
        async with self.dbman.conn() as db:
            settings = await SwedishFishSettings.selectCurrent(db, message.guild.id, message.channel.id)
            logger.debug(f"on_message: settings: {settings}")
            #  or default_settings
            successes = await SwedishFish.gamble(db)
            logger.debug(f"on_message: success_count: {len(successes)}")
            if settings.wallet_enabled:    
                logger.debug(f"on_message: wallet enabled")
                # successes = await SwedishFish.gamble(db)
                for s in successes:
                    default = FishWallet(message.author.id, message.guild.id, s.name)
                    old = await default.select(db) or default
                    logger.debug(f"on_message: old: {old}")
                    old.count += 1 
                    await old.upsert(db)
                    logger.debug("on_message: upserted increment")
            if settings.reactions_enabled:
                logger.debug(f"on_message: reactions_enabled")
                for s in successes:
                    bot_emoji = await s.get_emoji(db)
                    try:
                        emoji = await bot_emoji.fetch_discord(self.bot)
                        await message.add_reaction(emoji)
                        logger.debug(f"on_message: added reaction: {emoji.name}")
                    except discord.HTTPException as e:
                        logger.error(f"Discord emoji for swedish fish {s.name} with id {s.emoji_id} could not be retrieved") 
            await db.commit()
        

    @app_commands.command(name="toggle-reactions", description="toggles the visible reactions, users can still collect fish")
    async def toggle_reactions(self, interaction: Interaction, channel_only: bool=False) -> None:
        await respond(interaction)
        logger.debug(f"toggle_reactions: enter")
        assert interaction.guild is not None
        assert interaction.channel is not None
        channel_id = interaction.channel.id if channel_only else 0
        default = SwedishFishSettings(interaction.guild.id, channel_id)
        logger.debug(f"toggle_reactions: default: {default}")
        async with self.dbman.conn() as db:
            state = await default.select(db)
            logger.debug(f"toggle_reactions: old_state: {state}")
            if state is None:
                state = default
                logger.debug(f"toggle_reactions: state was none, now default, state: {state}")
            state.reactions_enabled = not state.reactions_enabled
            logger.debug(f"toggle_reactions: new_state: {state}")
            await state.upsert(db)
            logger.debug(f"toggle_reactions: upserted")
            await db.commit()

        r = "enabled, you can now see the fish" if state.reactions_enabled else "disabled, you can no longer see the fish"
        await respond(interaction, f"The reactions have been {r}")

    @app_commands.command(name="toggle-wallet", description="this toggles the wallet that allows users to collect fish, but reactions can still show up")
    async def toggle_wallet(self, interaction: Interaction, channel_only: bool=False) -> None:
        await respond(interaction)
        logger.debug(f"toggle_wallet: enter")
        assert interaction.guild is not None
        assert interaction.channel is not None
        channel_id = interaction.channel.id if channel_only else 0
        default = SwedishFishSettings(interaction.guild.id, channel_id)
        logger.debug(f"toggle_wallet: default: {default}")
        async with self.dbman.conn() as db:
            state = await default.select(db)
            logger.debug(f"toggle_wallet: old_state: {state}")
            if state is None:
                state = default
                logger.debug(f"toggle_wallet: state was none, now default, state: {state}")
            state.wallet_enabled = not state.wallet_enabled
            logger.debug(f"toggle_wallet: new_state: {state}")
            await state.upsert(db)
            logger.debug(f"toggle_wallet: upserted")
            await db.commit()
        r = "enabled, you can collect fish again" if state.wallet_enabled else "disabled, no more collecting fish"
        await respond(interaction, f"The wallet has been {r}")

    @app_commands.command(name="clear-channel-settings", description="Clear the settings for this channel")
    async def clear_settings(self, interaction: Interaction) -> None:
        await respond(interaction)
        assert interaction.guild is not None
        assert interaction.channel is not None
        async with self.dbman.conn() as db:
            settings = await SwedishFishSettings(interaction.guild.id, interaction.channel.id).select(db)
            if settings is not None:
                await settings.delete(db)
                await db.commit()

    @app_commands.command(name="settings", description="Queries the settings for the guild and channel")
    async def query_settings(self, interaction: Interaction) -> None:
        await respond(interaction)
        assert interaction.guild is not None
        assert interaction.channel is not None
        async with self.dbman.conn() as db:
            default = SwedishFishSettings(interaction.guild.id, channel_id=0)
            guild_settings = await default.select(db) or default
            channel_settings = await SwedishFishSettings(interaction.guild.id, channel_id=interaction.channel.id).select(db)
            settings = await SwedishFishSettings.selectCurrent(db, interaction.guild.id, interaction.channel.id)
        csw = channel_settings.wallet_enabled if channel_settings else ""
        csr = channel_settings.reactions_enabled if channel_settings else ""
        content = f"Current Settings => wallet: {settings.wallet_enabled}, reactions: {settings.reactions_enabled}" + \
                  f"\nDetails (channel, guild) => wallet: ({csw}, {guild_settings.wallet_enabled}), reactions: ({csr}, {guild_settings.reactions_enabled})"
        await respond(interaction, content)

    @app_commands.command(name="wallet", description="Shows your fish wallet")
    async def wallet(self, interaction: Interaction) -> None:
        await respond(interaction)
        assert interaction.guild is not None
        assert interaction.channel is not None
        async with self.dbman.conn() as db:
            wallet = await FishWallet(interaction.user.id, interaction.guild.id, None).list(db)
            # total = await FishWallet(interaction.user.id, interaction.guild.id, None).totalValue(db)

        uname = interaction.user.name
        pname = f"{uname}'s" if not uname.lower().endswith(("s", "z", "x")) else f"{uname}'"
        c1 = f"{pname} Wallet"
        c2 = len(c1) * "-"
        content = f"`{c1}`\n`{c2}`"
        content += f"\n`emoji - name : value * count = total`"
        total = 0
        for row in wallet:
            rep = f"{discord.PartialEmoji.from_str(f"<:{row["emoji_name"]}:{row["emoji_id"]}>")} - `{row["name"]} : {row["value"]} * {row["count"]} = {row["total"]}`"
            content += f"\n{rep}"
            total += row["total"]
        content += f"\n`{c2}`\n`Net Worth: {total}`"
        await respond(interaction, content)

        




async def setup(bot: Kagami) -> None:
    await bot.add_cog(Swedish(bot))
    await bot.add_cog(SwedishAdmin(bot))



