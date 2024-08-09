import abc
import sqlite3

import aiosqlite
from dataclasses import dataclass, asdict, astuple
from enum import Enum, Flag, IntFlag, auto
import discord


"""
Potential plans outside of the database file
Still need to maintain internal classes the represent stuff from the database and ways to write back to the database
Dataclasses can represent the various objects and have their own methods to writing to the database
"""


class Database:
    @classmethod
    def get_nested_classes(cls) -> list[type]:
        nested_classes = []
        for name, obj in cls.__dict__.items():
            if isinstance(obj, type):
                nested_classes += [obj]
        return nested_classes

    @classmethod
    def get_nested_row_classes(cls) -> list["Database.Row"]:
        nested_classes = []
        attributes = cls.__dict__.items()
        name: str
        for name, obj in attributes:
            if isinstance(obj, type) and issubclass(obj, Database.Row) and not name.startswith("_"):
                nested_classes += [obj]
        return nested_classes

    @classmethod
    def get_table_trigger_queries(cls) -> list[str]:
        """Returns a list of trigger queries for all nested classes"""
        queries = []
        for row_class in cls.get_nested_row_classes():
            temp = row_class.get_trigger_queries()
            queries += temp
        return queries

    @classmethod
    def get_create_table_queries(cls):
        queries = []
        for row_class in cls.get_nested_row_classes():
            queries += [row_class.Queries.CREATE_TABLE]
        return queries

    @classmethod
    def get_drop_table_queries(cls):
        queries = []
        for row_class in cls.get_nested_row_classes():
            queries += [row_class.Queries.DROP_TABLE]
        return queries

    @classmethod
    def get_queries(cls, query_name: str):
        queries = []
        for row_class in cls.get_nested_row_classes():
            if query := row_class.Queries.__dict__.get(query_name, False):
                queries += [query]
        return queries

    @dataclass
    class Row:
        class Queries:
            CREATE_TABLE = ""
            DROP_TABLE = ""
            UPSERT = ""
            INSERT = ""
            UPDATE = ""
            SELECT = ""
            DELETE = ""
        @classmethod
        def get_trigger_queries(cls):
            """returns a list of queries with 'trigger' in the variable name"""
            queries = []
            if not hasattr(cls, "Queries") and isinstance(getattr(cls, "Queries"), type):
                return queries
            for name, obj in cls.Queries.__dict__.items():
                if isinstance(obj, str) and name.lower().startswith("trigger"):
                    queries += [obj]
            return queries

        @classmethod
        def has_query(cls, field_name: str):
            """returns true if a matching query is found"""
            if not hasattr(cls, "Queries") and isinstance(getattr(cls, "Queries"), type):
                return False
            for name, obj in cls.Queries.__dict__.items():
                if isinstance(obj, str) and name.lower() == field_name.lower():
                    return True

        @classmethod
        def get_query(cls, field_name: str):
            if not hasattr(cls, "Queries") and isinstance(getattr(cls, "Queries"), type):
                return None

        # @classmethod
        # def has_query_class(cls):
        #     cname = "Queries"
        #     return hasattr(cls, cname) and isinstance(getattr(cls, cname), type)

        def __init__(self, *args, **kwargs): pass
        def asdict(self): return asdict(self)

        def astuple(self): return astuple(self)
        @classmethod
        def rowFactory(cls, cur: aiosqlite.Cursor, row: tuple):
            """Instantiates the dataclass from a row in the SQL table"""
            return cls(**{col[0]: row[idx] for idx, col in enumerate(cur.description)})
        # special reflection methods

    def __init__(self, database_path: str):
        self.file_path: str = database_path

    async def createTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            for query in self.get_create_table_queries():
                await db.execute(query)
            await db.commit()

    async def createTriggers(self):
        async with aiosqlite.connect(self.file_path) as db:
            for query in self.get_table_trigger_queries():
                await db.execute(query)
            await db.commit()

    async def migrate_tables(self):
        async with aiosqlite.connect(self.file_path) as db:
            for query in self.get_create_temp_table_queries():
                await db.execute(query)


    async def dropTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            for query in self.get_drop_table_queries():
                await db.execute(query)
            await db.commit()

    async def init(self, drop: bool=False, migrate: bool=False):
        if migrate:
            ...

        if drop: await self.dropTables()
        await self.createTables()
        await self.createTriggers()

class InfoDB(Database):
    @dataclass
    class Guild(Database.Row):
        id: int
        name: str
        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS Guild (
            id INTEGER,
            name TEXT DEFAULT 'Unknown',
            PRIMARY KEY (id))
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS Guild
            """
            TRIGGER_BEFORE_INSERT_GUILD = """
            CREATE TRIGGER IF NOT EXISTS insert_guild_settings_before_insert
            BEFORE INSERT ON Guild
            BEGIN
                INSERT INTO GuildSettings(guild_id)
                VALUES (NEW.id)
                ON CONFLICT (guild_id) DO NOTHING;
            END
            """
            UPSERT = """
            INSERT INTO Guild (id, name)
            VALUES (:id, :name)
            ON CONFLICT (id)
            DO UPDATE SET name = :name
            RETURNING *
            """
            SELECT = """
            SELECT * FROM Guild
            WHERE id = ?
            """
            DELETE = """
            DELETE FROM Guild
            WHERE id = ?
            RETURNING *
            """

        @classmethod
        def fromDiscord(cls, guild=discord.Guild):
            return cls(id=guild.id, name=guild.name)

    @dataclass
    class GuildSettings(Database.Row):
        guild_id: int
        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS GuildSettings(
            guild_id INTEGER,
            PRIMARY KEY (guild_id),
            FOREIGN KEY (guild_id) REFERENCES Guild(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            )
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS GuildSettings
            """
            UPSERT = """
            INSERT INTO GuildSettings (guild_id)
            VALUES (:guild_id)
            ON CONFLICT (id)
            DO NOTHING
            RETURNING *
            """
            QUERY_SELECT = """
            SELECT * FROM GuildSettings
            WHERE guild_id = ?
            """
            DELETE = """
            DELETE FROM GuildSettings
            WHERE guild_id = ?
            RETURNING *
            """

    @dataclass
    class User(Database.Row):
        id: int
        nickname: str

        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS User(
            id INTEGER NOT NULL,
            nickname TEXT DEFAULT NULL,
            PRIMARY KEY (id))
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS User
            """
            QUERY_UPSERT = """
            INSERT INTO User (id)
            VALUES (:id)
            ON CONFLICT (id)
            DO UPDATE SET nickname = :nickname
            """
            QUERY_SELECT = """
            SELECT * FROM User
            WHERE id = ?
            """
            QUERY_DELETE = """
            DELETE FROM User
            WHERE id = ?
            RETURNING *
            """

    async def upsertGuild(self, guild: Guild) -> Guild:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = guild.rowFactory
            new_guild: Database.Guild = await db.execute_fetchall(guild.Queries.UPSERT, guild.asdict())
            await db.commit()
        return new_guild

    async def upsertGuilds(self, guilds: list[Guild]) -> list[Guild]:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = Database.Guild.rowFactory
            guilds: list[Database.Guild] = await db.executemany(Database.Guild.Queries.UPSERT, guilds)
            await db.commit()
        return guilds

    async def upsertGuildSettings(self, guild_settings: GuildSettings) -> GuildSettings:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = guild_settings.rowFactory
            new_settings: Database.GuildSettings = await db.execute_fetchall(guild_settings.Queries.UPSERT, guild_settings.asdict())
            await db.commit()
        return new_settings

    async def fetchGuild(self, guild_id: int) -> Guild:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = Database.Guild.rowFactory
            guild: Database.Guild = await db.execute_fetchall(Database.Guild.Queries.SELECT, (guild_id,))
            await db.commit()
            return guild

    async def deleteGuild(self, guild_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            deleted_guild = await db.execute_fetchall(Database.Guild.Queries.DELETE, (guild_id,))
            await db.commit()
            return deleted_guild

    async def deleteGuildSettings(self, guild_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            deleted_settings = await db.execute_fetchall(Database.GuildSettings.Queries.DELETE, (guild_id,))
            await db.commit()
            return deleted_settings

