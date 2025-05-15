from __future__ import annotations
from typing import override, cast, final, Any
from dataclasses import dataclass
import random
import math
import sys

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
    async def selectLikeNames(cls, db: Connection, name: str, limit: int=-1, offset: int=0) -> list[str]:
        query = f"""
        SELECT name FROM {SwedishFish}
        WHERE (name like ?)
        LIMIT ? OFFSET ?
        """
        db.row_factory = aiosqlite.Row 
        async with db.execute(query, (f"%{name}%", limit, offset)) as cur:
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
class SwedishFishWallet(Table, schema_version=5, trigger_version=6):
    user_id: int
    guild_id: int
    fish_name: str | None
    count: int=0


    @classmethod
    def from_member(cls, member: discord.Member, fish_name: str|None=None, count: int=0) -> SwedishFishWallet:
        return SwedishFishWallet(user_id=member.id,
                                 guild_id=member.guild.id,
                                 fish_name=fish_name,
                                 count=count)

    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {SwedishFishWallet} (
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
            CREATE TRIGGER IF NOT EXISTS {SwedishFishWallet}_insert_settings_before_insert
            BEFORE INSERT ON {SwedishFishWallet}
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
        INSERT INTO {SwedishFishWallet} (user_id, guild_id, fish_name, count)
        VALUES (:user_id, :guild_id, :fish_name, :count)
        ON CONFLICT (user_id, guild_id, fish_name)
        DO UPDATE SET count = :count
        """
        await db.execute(query, self.asdict())

    @classmethod
    async def selectAll(cls, db: Connection, user_id: int, guild_id: int=0, fish_name: str | None=None) -> list[SwedishFishWallet]:
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
        SELECT * FROM {SwedishFishWallet}
        WHERE user_id = :user_id
        AND (:guild_id == 0 OR guild_id = :guild_id)
        AND (:fish_name IS NULL OR fish_name = :fish_name)
        """
        params = {"user_id": user_id, "guild_id" : guild_id, "fish_name": fish_name}
        db.row_factory = SwedishFishWallet.row_factory
        async with db.execute(query, params) as cur:
            res = await cur.fetchall()
        return res

    async def selectLikeNames(self, db: Connection, limit: int=-1, offset: int=0) -> list[str]:
        """
        Returns just the names of the fish for the specific query
        """
        query = f"""
        SELECT fw.fish_name as name 
        FROM {SwedishFishWallet} as fw
        INNER JOIN {SwedishFish} as sf
            ON sf.name = fw.fish_name
        WHERE   (:guild_id = 0 OR guild_id = :guild_id)
        AND     (:user_id = 0 OR user_id = :user_id) 
        AND     (fish_name LIKE :fish_name)
        ORDER BY sf.value ASC
        LIMIT :limit OFFSET :offset
        """
        params = self.asdict()
        params["fish_name"] = f"%{self.fish_name}%"
        params.update({"limit": limit, "offset": offset})
        async with db.execute(query, params) as cur:
            res = await cur.fetchall()
        return [row["name"] for row in res]

    async def selectRowsWithLikeNames(self, db: Connection, limit: int=-1, offset: int=0) -> list[SwedishFishWallet]:
        """
        Returns just the names of the fish for the specific query
        """
        query = f"""
        SELECT fw.* 
        FROM {SwedishFishWallet} as fw
        INNER JOIN {SwedishFish} as sf
            ON sf.name = fw.fish_name
        WHERE   (:guild_id = 0 OR guild_id = :guild_id)
        AND     (:user_id = 0 OR user_id = :user_id) 
        AND     (fish_name LIKE :fish_name)
        ORDER BY sf.value ASC
        LIMIT :limit OFFSET :offset
        """
        db.row_factory = SwedishFishWallet.row_factory
        params = self.asdict()
        params["fish_name"] = f"%{self.fish_name}%"
        params.update({"limit": limit, "offset": offset})
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
        FROM {SwedishFishWallet} AS fw
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

    async def take(self, db: Connection) -> SwedishFishWallet | None:
        """
        Take a certain number of fish from a wallet
        this subtracts the fish from the wallet itself and if not returned are gone
        """
        query = f"""
        INSERT INTO {SwedishFishWallet}(guild_id, user_id, fish_name, count)
        VALUES (:guild_id, :user_id, :fish_name, 0)
        ON CONFLICT (guild_id, user_id, fish_name)
        DO UPDATE SET
            count = count - MIN(MAX(:count, 0), count)
        WHERE
            guild_id = :guild_id
            AND user_id = :user_id
            AND fish_name = :fish_name
        RETURNING *
        """
        db.row_factory = SwedishFishWallet.row_factory
        old = await self.select(db)
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        if res is not None and old is not None:
            res.count = old.count - res.count 
        return res

    async def give(self, db: Connection) -> SwedishFishWallet | None:
        """
        Take a certain number of fish from a wallet
        this subtracts the fish from the wallet itself and if not returned are gone
        """
        query = f"""
        INSERT INTO {SwedishFishWallet}(guild_id, user_id, fish_name, count)
        VALUES (:guild_id, :user_id, :fish_name, :count)
        ON CONFLICT (guild_id, user_id, fish_name)
        DO UPDATE SET
            count = count + :count
        WHERE
            guild_id = :guild_id
            AND user_id = :user_id
            AND fish_name = :fish_name
        RETURNING guild_id, user_id, fish_name, :count AS count
        """
        db.row_factory = SwedishFishWallet.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
            # logger.debug(f"wallet give {res=}")
        return res

            
    async def select(self, db: Connection) -> SwedishFishWallet | None:
        """
        Returns an updated version of the current row
        guild_id == 0 => all servers
        fish_name is None => all fish
        """
        query = f"""
        SELECT * FROM {SwedishFishWallet}
        WHERE user_id = :user_id
        AND (:guild_id == 0 OR guild_id = :guild_id)
        AND (:fish_name IS NULL OR fish_name = :fish_name)
        """
        db.row_factory = SwedishFishWallet.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    async def netValue(self, db: Connection, limit: int=10, offset: int=0) -> list[aiosqlite.Row]:
        """
        Gives the net worth of each user as specific by the pseudo row
        Follows similar selection rules from selectAll
        """
        query = f"""
        SELECT user_id, Sum(fw.count * sf.value) as total
        FROM {SwedishFishWallet} as fw
        INNER JOIN {SwedishFish} as sf
            ON fw.fish_name = sf.name
        WHERE (:user_id = 0 OR user_id = :user_id)
        AND (:guild_id = 0 OR guild_id = :guild_id)
        AND (:fish_name IS NULL OR fish_name = :fish_name)
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT :limit OFFSET :offset
        """
        db.row_factory = aiosqlite.Row
        params = self.asdict()
        params.update({"limit": limit, "offset": offset})
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return list(rows)

    async def totalValue(self, db: Connection) -> int:
        """
        Give the total wealth across all users in the pseudo row query
        Follows similar selection rules from selectAll
        """
        query = f"""
        SELECT Sum(fw.count * sf.value) as total
        FROM {SwedishFishWallet} as fw
        INNER JOIN {SwedishFish} as sf
            ON fw.fish_name = sf.name
        WHERE (:guild_id = 0 OR guild_id = :guild_id)
        AND (:fish_name IS NULL OR fish_name = :fish_name)
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res["total"] if res is not None else 0 


class Transformer_Fish(Transformer):
    async def autocomplete(self, interaction: Interaction, value: str) -> list[Choice[str]]: # pyright: ignore [reportIncompatibleMethodOverride]
        async with interaction.client.dbman.conn() as db:
            names = await SwedishFish.selectLikeNames(db, value, limit=25)
        choices = [Choice(name=name, value=name) for name in names]
        return choices

    async def transform(self, interaction: Interaction, value: str) -> SwedishFish | None: # pyright: ignore [reportIncompatibleMethodOverride]
        async with interaction.client.dbman.conn() as db:
            result = await SwedishFish.selectFromName(db, value)
        return result


class Transformer_UserFish(Transformer):
    async def autocomplete(self, interaction: Interaction, value: str) -> list[Choice[str]]: # pyright: ignore [reportIncompatibleMethodOverride]
        # logger.debug(f"Transformer_UserFish.autocomplete: Enter with value: {value}")
        assert interaction.guild is not None
        # logger.debug(f"Transformer_UserFish.autocomplete: Post assertion")
        pseudo = SwedishFishWallet(interaction.user.id, interaction.guild.id, value)
        async with interaction.client.dbman.conn() as db:
            fishes = await pseudo.selectRowsWithLikeNames(db, limit=25)
        # logger.debug(f"Transformer_UserFish.autocomplete: Got fishes, count: {len(fishes)}")
        choices = [Choice(name=name, value=name) 
                   for fish in fishes 
                   if (name := fish.fish_name) is not None]
        # logger.debug(f"Transformer_UserFish.autocomplete: Created choices")
        interaction.extras["fishes"] = fishes
        return choices

    async def transform(self, interaction: Interaction, value: str) -> SwedishFishWallet | None: # pyright: ignore [reportIncompatibleMethodOverride]
        assert interaction.guild is not None
        pseudo = SwedishFishWallet(interaction.user.id, 
                                   interaction.guild.id, 
                                   value)
        async with interaction.client.dbman.conn() as db:
            fish = await pseudo.select(db)
        return fish

class Transformer_UserFishCount(Transformer[Kagami]):
    """
    Requires a previous command field called fish
    Other names may potentially be added
    """
    @override
    async def autocomplete(self, interaction: Interaction, value: str | int | float) -> list[Choice[str]]: 
        logger.debug(f"UserFishCount - autocomplete: enter")
        assert interaction.guild is not None
        logger.debug(f"UserFishCount - autocomplete: passed assert")
        try:
            value = int(value)
        except ValueError:
            value = 0
        fish_name = interaction.namespace["fish"]
        logger.debug(f"UserFishCount - autocomplete: {fish_name=}")
        pseudo = SwedishFishWallet(interaction.user.id, 
                                   interaction.guild.id, 
                                   fish_name)
        async with interaction.client.dbman.conn() as db:
            fish = await pseudo.select(db)
        logger.debug(f"UserFishCount - autocomplete: {fish=}")
        
        if fish is None:
            logger.debug(f"UserFishCount - autocomplete: Fish is none")
            return [Choice(name=f"Invalid Fish", value="0")]
        max_choice = Choice(name=f"Max: {fish.count}", value=f"{fish.count}")
        logger.debug(f"UserFishCount - autocomplete: {max_choice=}")
        # value = int(value) if isinstance(value, str) and value.isdigit() else 0
        logger.debug(f"UserFishCount - {value=}")
        logger.debug(f"UserFishCount - {value<fish.count=}")

        if value < fish.count:
            v = f"{value}"
            choices = [Choice(name=v, value=v), max_choice]
            # logger.debug(f"UserFishCount - autocomplete: {choices=}")
            return choices
        else:
            return [max_choice]

    @override
    async def transform(self, interaction: Interaction, value: str | float | int) -> int: 
        assert interaction.guild is not None
        try:
            value = int(value)
        except ValueError:
            value = 0
        fish_name = interaction.namespace["fish"]
        logger.debug(f"UserFishCount - transform: {fish_name=}")
        pseudo = SwedishFishWallet(interaction.user.id, 
                                   interaction.guild.id, 
                                   fish_name)
        async with interaction.client.dbman.conn() as db:
            fish = await pseudo.select(db)
        logger.debug(f"UserFishCount - transform: {fish=}")
        # value = int(value) if isinstance(value, str) and value.isdigit() else 0
        if fish is not None:
            return min(max(value, 0), fish.count)
        else:
            return 0


VALID_FILE_TYPES = ("png", "jpg", "jpeg", "webp")

@app_commands.guilds(discord.Object(config.admin_guild_id))
class Cog_SwedishDev(GroupCog, group_name="sf"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    async def cog_load(self) -> None:
        pass

    @app_commands.command(name="add", description="adds a new fish")
    async def add(self, interaction: Interaction, name: Transform[SwedishFish | None, Transformer_Fish], image: discord.Attachment, value: int):
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
    async def edit(self, interaction: Interaction, fish: Transform[SwedishFish | None, Transformer_Fish], image: discord.Attachment | None=None, value: int | None=None) -> None:
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
    async def delete(self, interaction: Interaction, fish: Transform[SwedishFish | None, Transformer_Fish]) -> None:
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

@app_commands.default_permissions(manage_expressions=True)
class Cog_SwedishGuildAdmin(GroupCog, group_name="fish-admin"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @app_commands.command(name="toggle-reactions", description="toggles the visible reactions, users can still collect fish")
    async def toggle_reactions(self, interaction: Interaction, channel_only: bool=False) -> None:
        await respond(interaction, ephemeral=True)
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
        await respond(interaction, f"The reactions have been {r}", ephemeral=True, delete_after=5)

    @app_commands.command(name="toggle-wallet", description="this toggles the wallet that allows users to collect fish, but reactions can still show up")
    async def toggle_wallet(self, interaction: Interaction, channel_only: bool=False) -> None:
        await respond(interaction, ephemeral=True)
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
        await respond(interaction, f"The wallet has been {r}", ephemeral=True, delete_after=5)

    @app_commands.command(name="clear-channel-settings", description="Clear the settings for this channel")
    async def clear_settings(self, interaction: Interaction) -> None:
        await respond(interaction, ephemeral=True)
        assert interaction.guild is not None
        assert interaction.channel is not None
        async with self.dbman.conn() as db:
            settings = await SwedishFishSettings(interaction.guild.id, interaction.channel.id).select(db)
            if settings is not None:
                await settings.delete(db)
                await db.commit()
        await respond(interaction, f"Cleared settings for the channel, ressetting to guild default", delete_after=5)

    @app_commands.command(name="settings", description="Queries the settings for the guild and channel")
    async def query_settings(self, interaction: Interaction) -> None:
        await respond(interaction, ephemeral=True)
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
        await respond(interaction, content, delete_after=5)

class Cog_SwedishUser(GroupCog, group_name="fish"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.dbman = bot.dbman

    @GroupCog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.webhook_id is not None:
            return
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
                    default = SwedishFishWallet(message.author.id, message.guild.id, s.name)
                    old = await default.select(db) or default
                    logger.debug(f"on_message: old: {old}")
                    old.count += 1 
                    await old.upsert(db)
                    logger.debug("on_message: upserted increment")
            if settings.reactions_enabled and message.author != self.bot.user:
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
        

    @app_commands.command(name="give", description="Give fish to another user")
    async def give(self, interaction: Interaction, user: discord.Member, fish: Transform[SwedishFishWallet | None, Transformer_UserFish], quantity: Transform[int, Transformer_UserFishCount]) -> None:
        await respond(interaction, ephemeral=True)
        assert isinstance(interaction.user, discord.Member)
        if fish is None:
            await respond(interaction, "You cannot give away fish you do not have", ephemeral=True, delete_after=5)  
            return
        request = SwedishFishWallet.from_member(interaction.user, fish.fish_name, quantity)
        async with interaction.client.dbman.conn() as db:
            taken = await request.take(db)
            if taken is None:
                await respond(interaction, f"Something went wrong, could not transfer fish from you", ephemeral=True, delete_after=5)
                return
            # logger.debug(f"fish-give: {taken=}")
            taken.user_id = user.id
            given = await taken.give(db)
            # logger.debug(f"fish-give: {given=}")
            if given is None:
                await respond(interaction, f"Something went wrong, could not transfer fish to other user", ephemeral=True, delete_after=5)
                return
            await db.commit()
        await respond(interaction, f"Gave {given.count} {given.fish_name} fish to {user.name}", ephemeral=True, delete_after=3)


    @app_commands.command(name="wallet", description="Shows your fish wallet")
    @app_commands.rename(all_servers="global")
    @app_commands.describe(all_servers="If true, displays your wallet across all servers the bot is on")
    async def wallet(self, interaction: Interaction, all_servers: bool=False, show_others: bool=False) -> None:
        await respond(interaction, ephemeral=not show_others)
        assert interaction.guild is not None
        assert interaction.channel is not None
        guild_id = 0 if all_servers else interaction.guild.id
        async with self.dbman.conn() as db:
            wallet = await SwedishFishWallet(interaction.user.id, guild_id, None).list(db)
            # total = await FishWallet(interaction.user.id, interaction.guild.id, None).totalValue(db)

        uname = interaction.user.name
        pname = f"{uname}'s" if not uname.lower().endswith(("s", "z", "x")) else f"{uname}'"
        ws = f"{interaction.guild.name}" if not all_servers else "Globally"
        c1 = f"{pname} Wallet ({ws})"
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

    
    @app_commands.command(name="top", description="Shows the most valuable users")
    @app_commands.describe(all_servers="Shows the most valuable users across all servers")
    @app_commands.rename(all_servers="global")
    async def top(self, interaction: Interaction, all_servers: bool=False, show_others: bool=False) -> None:
        await respond(interaction, ephemeral=not show_others)
        assert interaction.guild is not None
        assert interaction.channel is not None
        async with self.dbman.conn() as db:
            guild_id = 0 if all_servers else interaction.guild.id
            # wallet = await FishWallet(0, guild_id, None).list(db)
            top = await SwedishFishWallet(0, guild_id, None).netValue(db)
            total = await SwedishFishWallet(0, guild_id, None).totalValue(db)
            # total = await FishWallet(interaction.user.id, interaction.guild.id, None).totalValue(db)
        uname = interaction.user.name
        pname = f"{uname}'s" if not uname.lower().endswith(("s", "z", "x")) else f"{uname}'"
        ws = f"{interaction.guild.name}" if not all_servers else "Globally"
        c1 = f"Fishiest Fiends ({ws})"
        c2 = len(c1) * "-"
        content = f"`{c1}`\n`{c2}`"
        content += f"\n`user - net worth`"
        page_total = 0
        for row in top:
            # rep = f"{discord.PartialEmoji.from_str(f"<:{row["emoji_name"]}:{row["emoji_id"]}>")} - `{row["name"]} : {row["value"]} * {row["count"]} = {row["total"]}`"
            try:
                user = await self.bot.fetch_user(row["user_id"])
            except discord.NotFound:
                continue
            rep = f"`{user.name} - {row["total"]}`"
            content += f"\n{rep}"
            page_total += row["total"]
        content += f"\n`{c2}`\n`Page Wealth / Global Wealth: {page_total} / {total}`"
        await respond(interaction, content)




async def setup(bot: Kagami) -> None:
    await bot.add_cog(Cog_SwedishUser(bot))
    await bot.add_cog(Cog_SwedishGuildAdmin(bot))
    await bot.add_cog(Cog_SwedishDev(bot))
    await bot.dbman.setup(__name__)



