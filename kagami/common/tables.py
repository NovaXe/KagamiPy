import discord

from common.database import Table, ManagerMeta
from dataclasses import dataclass
import aiosqlite


@dataclass
class GuildSettings(Table, schema_version=1, trigger_version=1, group_name="common"):
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
class Guild(Table, schema_version=2, trigger_version=2, table_group="common"):
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
class User(Table, schema_version=1, trigger_version=1, table_group="common"):
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
class PersistentSettings(Table, schema_version=1, trigger_version=1, table_group="common"):
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
