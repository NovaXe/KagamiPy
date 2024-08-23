import abc
import re
import sqlite3
import typing
import warnings

import aiosqlite
from dataclasses import dataclass, asdict, astuple, fields
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

    @classmethod
    def get_batched_queries(cls, query_names: typing.Iterable[str]) -> dict[str, tuple]:
        batches = {}
        for row_class in cls.get_nested_row_classes():
            query_results = []
            for name in query_names:
                query = row_class.Queries.__dict__.get(name, False)
                if query:
                    query_results += [query]
                else:
                    break
            if len(query_results) == len(query_names):
                class_name = row_class.__name__
                batches[class_name] = tuple(query_results)
        return batches

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

    async def schemaUpdate(self):
        async with aiosqlite.connect(self.file_path) as db:
            try:
                # await db.execute("PRAGMA foreign_keys = OFF;")
                query_order = ("CREATE_TEMP_TABLE",
                               "DROP_TABLE",
                               "CREATE_TABLE",
                               "INSERT_FROM_TEMP_TABLE",
                               "DROP_TEMP_TABLE")
                batched_queries = self.get_batched_queries(query_order)
                for table_name, batch in batched_queries.items():
                    if not await self.queryTableExistance(table_name):
                        continue
                    for qry in batch:
                        await db.execute(qry)

                # await db.execute("PRAGMA foreign_keys = ON;")
            except sqlite3.OperationalError as e:
                raise e
            await db.commit()

    async def queryTableExistance(self, table_name: str):
        async with aiosqlite.connect(self.file_path) as db:
            query = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
            async with db.execute(query) as cur:
                result = await cur.fetchone()
                return bool(result)

    async def dropTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            for query in self.get_drop_table_queries():
                await db.execute(query)
            await db.commit()

    async def init(self, drop: bool=False, schema_update: bool=False):
        if schema_update: await self.schemaUpdate()
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
            db.row_factory = Database.Guild.row_factory
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
            db.row_factory = Database.Guild.row_factory
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


class TableRegistry:
    # __table_class__: type["Table"] # forward declaration resolved after class
    TableType = type["Table"]
    tables: dict[str, TableType] = {}
    @classmethod
    def register_table(cls, table: type["Table"]):
        cls.tables[table.__name__] = table

    @classmethod
    def get_table(cls, tablename: str) -> TableType:
        return cls.tables.get(tablename, None)

    @classmethod
    async def create_tables(cls, db: aiosqlite.Connection):
        for tablename, tableclass in cls.tables.items():
            await tableclass.create_table(db)

    @classmethod
    async def drop_tables(cls, db: aiosqlite.Connection):
        for tablename, tableclass in cls.tables.items():
            await tableclass.drop_table(db)

    @classmethod
    async def drop_unregistered(cls, db: aiosqlite.Connection):
        names = cls.tables.keys()
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
            result = await cur.fetchall()
            existing_names = [e[0] for e in result]
        for name in existing_names:
            if name not in names:
                await db.execute(f"DROP TABLE IF EXISTS {name}")


    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        for tablename, tableclass in cls.tables.items():
            await tableclass.create_triggers(db)


class TableMeta(type):
    def __new__(mcs, name, bases, class_dict, *args,
                table_registry: type["TableRegistry"]=TableRegistry, **kwargs):
        cls = super().__new__(mcs, name, bases, class_dict)
        cls.__table_registry__ = table_registry
        cls.__tablename__ = name
        if table_registry is not None:
            table_registry.register_table(cls)
        else:
            warnings.warn(f"The table class: {name} has it's registry set to None")
        return cls

    def __str__(cls):
        return cls.__tablename__

    def field_count(cls):
        """
        Gives the number of dataclass fields, will return 0 if not a dataclass
        """
        if hasattr(cls, "__dataclass_fields__"):
            return len(cls.__dataclass_fields__)
        return 0


    # def __init__(cls, name, bases, class_dict, *args, **kwargs):
    #     super().__init__(name, bases, class_dict)
    #     if hasattr(cls, "__dataclass_fields__"):
    #         cls._field_count = fields(cls)
    #         # cls._field_count = len(cls.__dataclass_fields__)
    #         pass

class TableNameError(ValueError):
    """Raised when a table name is invalid"""
    pass

@dataclass
class Table(metaclass=TableMeta, table_registry=None):
    # def __init__(self, *args, **kwargs): pass
    @classmethod
    def _row_factory(cls, cur: aiosqlite.Cursor, row: tuple):
        """Instantiates the dataclass from a row in the SQL table"""
        return cls(**{col[0]: row[idx] for idx, col in enumerate(cur.description)})
    row_factory = _row_factory
    # @property
    # @classmethod
    # def __tablename__(cls: type["Table"]) -> str:
    #     return cls._tablename
    #
    # @__tablename__.setter
    # @classmethod
    # def __tablename__(cls: type["Table"], tablename: str):
    #     validation_pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
    #     if re.match(validation_pattern, tablename) is not None:
    #         cls._tablename = tablename
    #     else:
    #         raise TableNameError(
    #             f"Invalid table name: '{tablename}'\n"
    #             f"A valid name must start with a letter or underscore, followed by letters, digits or underscores")

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        await db.execute(f"CREATE TABLE IF NOT EXISTS {cls.__tablename__}(rowid INTEGER PRIMARY KEY)")

    @classmethod
    async def drop_table(cls, db: aiosqlite.Connection):
        await db.execute(f"DROP TABLE IF EXISTS {cls.__tablename__}")

    @classmethod
    async def create_temp_copy(cls, db: aiosqlite.Connection):
        await db.execute(f"CREATE TABLE temp_{cls.__tablename__} "
                         f"AS SELECT * FROM {cls.__tablename__}")

    @classmethod
    async def insert_from_temp(cls, db: aiosqlite.Connection):
        """
        Depending on what has changed in the schema this may need an override
        """
        await db.execute(f"INSERT INTO {cls.__tablename__} "
                         f"SELECT * FROM temp_{cls.__tablename__}")

    @classmethod
    async def drop_temp(cls, db: aiosqlite.Connection):
        await db.execute(f"DROP TABLE IF EXISTS temp_{cls.__tablename__}")


    @classmethod
    async def update_schema(cls, db: aiosqlite.Connection):
        """
        Override if a custom set of steps is needed
        """
        await cls.create_temp_copy(db)
        await cls.drop_table(db)
        await cls.create_table(db)
        await cls.insert_from_temp(db)
        await cls.drop_temp(db)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        """
        Called under the assumption of creating all triggers for a specific table.
        By default, this method does nothing and instead should be replaced when needed.
        Example implementation,
        triggers: list[str] = ["CREATE TRIGGER ...", "CREATE TRIGGER ..."]
        for trigger in triggers:
            await db.execute(trigger)
        """
        pass

    def asdict(self): return asdict(self)

    def astuple(self): return astuple(self)

    async def insert(self, db: aiosqlite.Connection):
        field_count = self.__class__.field_count()
        placeholders = ",".join('?' for _ in range(field_count))
        query = f"INSERT INTO {self.__tablename__} VALUES ({placeholders})"
        await db.execute(query, self.astuple())

    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, *args, **kwargs) -> "Table":
        """
        Override to select a row from the table, returning an instance of the Table as the row
        """
        raise NotImplementedError("Subclasses need to implement this method")

    async def select(self, db: aiosqlite.Connection) -> "Table":
        """
        Selects a row from the table using a table instance for key values.
        Override to add functionality
        """
        raise NotImplementedError("Subclasses need to implement this method")
        # return None

    # noinspection PyMethodParameters
    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, *args, **kwargs) -> "Table":
        """
        Override to delete a row from the table, returning an instance of the Table as the deleted row
        """
        raise NotImplementedError("Subclasses need to implement this method")


    async def delete(self, db: aiosqlite.Connection) -> "Table":
        """
        Deletes a row from the table using a table instance for key values.
        Override to add functionality
        """
        raise NotImplementedError("Subclasses need to implement this method")


class ManagerMeta(type):
    def __new__(mcs, name, bases, class_dict, *args,
                table_registry: type["TableRegistry"]=TableRegistry, **kwargs):
        cls = super().__new__(mcs, name, bases, class_dict)
        cls.__table_registry__ = table_registry
        if table_registry is None:
            raise ValueError(f"table_registry for class: {name} cannot be None")
        return cls


class DatabaseManager(metaclass=ManagerMeta, table_registry=TableRegistry):
    # __registry_class__: type["TableRegistry"] = TableRegistry
    def __init__(self, db_path: str):
        self.file_path = db_path
        self._db: aiosqlite.Connection = None

    async def setup(self):
        async with self as db:
            await self.__table_registry__.create_tables(db)
            await db.commit()

    async def connect(self) -> aiosqlite.Connection:
        return await aiosqlite.connect(self.file_path)

    async def __aenter__(self) -> aiosqlite.Connection:
        self._db = await self.connect()
        return self._db

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def drop_table(self, tablename: str):
        async with self as db:
            table: type[Table] = self.__table_registry__.get_table(tablename)
            await table.drop_table(db)
            await db.commit()

    async def drop_unregistered(self):
        async with self as db:
            await self.__table_registry__.drop_unregistered(db)

    __AsyncFunctionType = typing.Callable[[aiosqlite.Connection], typing.Awaitable]
    async def handle(self, functions: tuple[__AsyncFunctionType]) -> list[typing.Any]:
        async with self as db:
            results = []
            for function in functions:
                result = await function(db)
                results.append(result)
            await db.commit()
        return results
