from __future__ import annotations
from typing import cast, override
import discord

from common.database import Table, ManagerMeta
from dataclasses import dataclass
import aiosqlite
from aiosqlite import Connection
from io import BytesIO


@dataclass
class GuildSettings(Table, schema_version=1, trigger_version=1):
    guild_id: int
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {GuildSettings}(
            guild_id INTEGER,
            PRIMARY KEY (guild_id),
            FOREIGN KEY (guild_id) REFERENCES {Guild}(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        await db.execute(query)

    async def upsert(self, db: aiosqlite.Connection) -> "GuildSettings":
        query = f"""
        INSERT INTO {GuildSettings} (guild_id)
        VALUES (:guild_id)
        ON CONFLICT (id)
        DO NOTHING
        RETURNING *
        """
        db.row_factory = GuildSettings.row_factory
        async with db.execute(query, self.asdict()) as cur:
            result = cur.fetchone()
        return result

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, guild_id: int) -> "GuildSettings":
        query = f"""
        SELECT * FROM {GuildSettings}
        WHERE guild_id = ? 
        """
        # Hi! I am so smart, I am coding so well
        db.row_factory = GuildSettings.row_factory
        async with db.execute(query, (guild_id,)) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int) -> "GuildSettings":
        query = f"""
        DELETE FROM {GuildSettings}
        WHERE guild_id = ?
        RETURNING *
        """
        db.row_factory = GuildSettings.row_factory
        async with db.execute(query, (guild_id,)) as cur:
            result = cur.fetchone()
        return result

@dataclass
class Guild(Table, schema_version=2, trigger_version=2):
    id: int
    name: str

    @classmethod
    def fromDiscord(cls, guild=discord.Guild):
        return Guild(id=guild.id, name=guild.name)

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {Guild}(
            id INTEGER,
            name TEXT DEFAULT 'Unknown',
            PRIMARY KEY (id)
        )
        """
        await db.execute(query)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        trigger = f"""
        CREATE TRIGGER IF NOT EXISTS {Guild}_insert_settings_before_insert
        BEFORE INSERT ON {Guild}
        BEGIN
            INSERT OR IGNORE INTO {GuildSettings}(guild_id)
            VALUES (NEW.id);
        END;
        """
        await db.execute(trigger)

    async def upsert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT INTO {Guild} (id, name)
        VALUES (:id, :name)
        ON CONFLICT (id)
            DO UPDATE SET name = :name
        RETURNING *
        """
        await db.execute(query, self.asdict())

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, guild_id: int) -> "Guild":
        query = f"""
        SELECT * FROM {Guild}
        WHERE id = ?
        """
        db.row_factory = Guild.row_factory
        async with db.execute(query, (guild_id)) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int) -> "Guild":
        query = f"""
        DELETE FROM {Guild}
        WHERE id = ?
        RETURNING *
        """
        db.row_factory = Guild.row_factory
        async with db.execute(query, (guild_id)) as cur:
            result = await cur.fetchone()
        return result

@dataclass
class User(Table, schema_version=1, trigger_version=1):
    id: int
    nickname: str   
    
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {User}(
            id INTEGER NOT NULL,
            nickname TEXT DEFAULT NULL,
            PRIMARY KEY (id)
        )
        """
        await db.execute(query)

    async def upsert(self, db: aiosqlite.Connection) -> "User":
        query = f"""
        INSERT INTO {User}(id)
        VALUES (:id)
        ON CONFLICT (id)
        DO UPDATE SET nickname = :nickname
        """
        db.row_factory = User.row_factory
        async with db.execute(query, self.asdict()) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, id: int) -> "User":
        query = f"""
        SELECT * FROM {User}
        WHERE id ?
        """
        db.row_factory = User.row_factory
        async with db.execute(query, (id,)) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, id: int) -> "User":
        query = f"""
        DELETE FROM {User}
        WHERE id = ?
        RETURNING *
        """
        db.row_factory = User.row_factory
        async with db.execute(query, (id,)) as cur:
            res = await cur.fetchone()
        return res

@dataclass
class PersistentSettings(Table, schema_version=1, trigger_version=1):
    key: str
    value: str | int | float
    
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {PersistentSettings}(
            key TEXT PRIMARY KEY,
            value
        )
        """
        await db.execute(query)
    
    async def upsert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT INTO {PersistentSettings}(key, value)
        VALUES (:key, :value)
        ON CONFLICT (key)
        DO UPDATE SET value = :value
        """
        await db.execute(query, self.asdict())
    
    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, key: str, default_value=None):
        query = f"""
        SELECT value FROM {PersistentSettings}
        WHERE key = ?
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (key,)) as cur:
            res = await cur.fetchone()
        return res[0] if res else default_value


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
            CREATE TABLE IF NOT EXISTS {BotEmoji} (
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
        SELECT * FROM {BotEmoji}
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

    


