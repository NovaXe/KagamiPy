import asyncio
import traceback
import logging
import typing
from asyncio import Queue
import aiosqlite
from aiosqlite.context import contextmanager
from dataclasses import dataclass, asdict, astuple, fields
from contextlib import asynccontextmanager

from common.logging import setup_logging
from typing import Generator, Iterable, Any

logger = setup_logging(__name__)

"""
Gives some classes and methods for interfacing with an sqlite database in a standard way across cogs
"""

# def validate_syntax(query: str):
#     try:
#         parsed_query = sqlglot.parse_one(query, dialect="sqlite")
#     except sqlglot.ParseError as e:
#         logger.error(f"SQLite Syntax Error for query: {query} -\n{e)
#         raise e
#     return query

# @contextmanager
# async def exec_query(db: aiosqlite.Connection, query: str, *params: Iterable[Any]):
#     """
#     Executes a query after validating the syntax.
#     If the syntax is invalid an error is thrown and the query is not executed. 
#     """
#     if params is None:
#         params = ()
#     # validate_syntax(query)
#     cur: aiosqlite.Cursor = await db.execute(query, params)
#     try: 
#         yield cur
#     finally:
#         await cur.close()

class TableRegistry:
    # __table_class__: type["Table"] # forward declaration resolved after class
    TableType = type["Table"]
    tables: dict[str, TableType] = {}

    @classmethod
    def tableiter(cls, group_name: str=None) -> Generator[tuple[str, TableType], None, None]:
        for table_name, table_class in cls.tables.items():
            if table_class.__table_group__ == group_name or group_name is None:
                yield table_name, table_class

    @classmethod
    def get_tables(cls, group_name: str=None) -> dict[str, TableType]:
        """
        returns a dict of all tables that belong to the given group, if group is None then all tables are returned
        """
        return {k: v for k, v in cls.tables.items()
                if v.__table_group__ == group_name or group_name is None}

    @classmethod
    def register_table(cls, table: type["Table"]):
        logger.debug(f"Registered new Table: {table.__name__}")
        cls.tables[table.__name__] = table

    @classmethod
    def get_table(cls, tablename: str) -> TableType:
        return cls.tables.get(tablename, None)

    @classmethod
    async def create_tables(cls, db: aiosqlite.Connection, group_name: str=None):
        logger.debug(f"Creating tables for group: {group_name}")
        for tablename, tableclass in cls.tableiter(group_name):
            try:
                await tableclass.create_table(db)
            except aiosqlite.OperationalError as e:
                logger.error(f"Issue creating table: {tablename} - {e}", exc_info=True)
                await db.rollback()
                raise
            logger.debug(f"Created Table: {tablename}")

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection, group_name):
        logger.debug(f"Creating triggers for group: {group_name}")
        for tablename, tableclass in cls.tableiter(group_name):
            try:
                await tableclass.create_triggers(db)
            except aiosqlite.OperationalError as e:
                logger.error(f"Issue creating triggers for table: {tablename} - {e}", exc_info=True)
                await db.rollback()
                raise
            logger.debug(f"Created triggers for Table: {tablename}")

    @classmethod
    async def drop_tables(cls, db: aiosqlite.Connection, group_name: str=None):
        logger.debug(f"Dropping tables in group: {group_name}")
        for tablename, tableclass in cls.tableiter(group_name):
            await tableclass.drop_table(db)
            logger.debug(f"Dropped Table: {tablename}")

    @classmethod
    async def drop_triggers(cls, db: aiosqlite.Connection, group_name: str=None):
        logger.debug(f"Dropping triggers in group: {group_name}")
        for tablename, tableclass in cls.tableiter(group_name):
            await tableclass.drop_triggers(db)
            logger.debug(f"Dropped triggers for Table: {tablename}")
    
    @classmethod
    async def update_schemas(cls, db: aiosqlite.Connection, group_name: str=None):
        logger.debug(f"Updating schemas for group: {group_name}")
        for tablename, tableclass in cls.tableiter(group_name):
            if not await tableclass._exists(db):
                logger.debug(f"Skipping schema update for missing table: {tablename}")
                continue
            metadata = await TableMetadata.selectValue(db, table_name=tablename)
            if not metadata:
                metadata = TableMetadata(tablename)
            # current_version = await TableMetadata.selectVersion(db, tablename)
            table_version = tableclass.__schema_version__
            if metadata.schema_version < table_version:
                logger.debug(f"Updating out of date Table: {tablename}")
                await tableclass.update_schema(db)
                logger.debug(f"Updated schema for Table: {tablename}")
                metadata.schema_version = tableclass.__schema_version__
                await metadata.upsert(db)
                logger.debug(f"Updated schema version for Table: {tablename}")
            else:
                logger.debug(f"Schema for Table: {tablename} is already up to date")
            # logger.debug(f"Updated schema version for Table: {tablename}")
    
    @classmethod
    async def update_triggers(cls, db: aiosqlite.Connection, group_name: str=None):
        logger.debug(f"Updating triggers for group: {group_name}")
        for tablename, tableclass in cls.tableiter(group_name):
            if not await tableclass._exists(db):
                logger.debug(f"Skipping trigger update for missing table: {tablename}")
                continue
            metadata = await TableMetadata.selectValue(db, table_name=tablename)
            if not metadata:
                metadata = TableMetadata(tablename)
            
            if metadata.trigger_version < tableclass.__trigger_version__:
                logger.debug(f"Updating out od data triggers on Table: {tablename}")
                await tableclass.drop_triggers(db)
                await tableclass.create_triggers(db)
                logger.debug(f"Updated triggers for Table: {tablename}")
                metadata.trigger_version = tableclass.__trigger_version__
                await metadata.upsert(db)
                logger.debug(f"Updated trigger version for Table: {tablename}")
            else:
                logger.debug(f"Triggers for Table: {tablename} are up to date")

    @classmethod
    async def alter_tables(cls, db: aiosqlite.Connection, group_name: str=None):
        for tablename, tableclass in cls.tableiter(group_name):
            if tableclass.__schema_altered__:
                logger.info(f"Began Alter of Table: {tablename}")
                await tableclass.alter_table(db)
                logger.info(f"Finished Alter of Table: {tablename}")

    @classmethod
    async def drop_unregistered(cls, db: aiosqlite.Connection):
        names = cls.tables.keys()
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
            result = await cur.fetchall()
            existing_names = [e[0] for e in result]
        for name in existing_names:
            if name not in names:
                await db.execute(f"DROP TABLE IF EXISTS {name}")


class TableNameError(ValueError):
    """Raised when a table name is invalid"""
    pass

class TableSubclassMustImplement(NotImplementedError):
    """Raised when a subclass of Table calls an unimplemented method that it must implement to use"""
    def __init__(self, message="Subclasses of Table must implement this method to call it"):
        super().__init__(message)

class TableMeta(type):
    def __new__(mcs, name, bases, class_dict, *args,
                table_registry: type["TableRegistry"]=TableRegistry,
                schema_version: int,
                trigger_version: int,
                table_group: str=..., **kwargs):
        cls = super().__new__(mcs, name, bases, class_dict)
        cls.__table_registry__ = table_registry
        cls.__tablename__ = name
        cls.__schema_version__ = schema_version
        cls.__trigger_version__ = trigger_version
        if table_group is ...:
            cls.__table_group__ = cls.__module__
        elif table_group is None:
            cls.__table_group__ = "unassigned"
            
        # cls.__schema_changed__ = schema_changed
        # cls.__schema_altered__ = schema_altered
        cls.__old_tablename__ = None
        if table_registry is not None:
            table_registry.register_table(cls)
        else:
            logger.warn(f"The table class: {name} has it's registry set to None")
        return cls

    def __str__(cls):
        return cls.__tablename__

    def __field_count(cls):
        """
        Gives the number of dataclass fields, will return 0 if not a dataclass
        """
        if hasattr(cls, "__dataclass_fields__"):
            return len(cls.__dataclass_fields__)
        return 0

@dataclass
class Table(metaclass=TableMeta, schema_version=0, trigger_version=0, table_registry=None):
    @staticmethod
    def group(name: str):
        """
        Decorator for specifying a group a table belongs to
        table_group can also be set in the class initializer
        """
        def decorator(cls):
            cls.__table_group__ = name
            return cls
        return decorator

    # def __init__(self, *args, **kwargs): pass
    @classmethod
    def _row_factory(cls, cur: aiosqlite.Cursor, row: tuple):
        """Instantiates the dataclass from a row in the SQL table"""
        # field_names = {col[0] for col in cur.description}
        # got this stuff from chatgpt because the row factory thing always confused me, I know why it works so it's fine
        valid_fields = {field.name for field in fields(cls)}
        # gets rid of fields that don't exist in the dataclass
        filtered_data = {col[0]: row[idx] for idx, col in enumerate(cur.description) if col[0] in valid_fields}
        default_data = {field: ... for field in valid_fields if field not in filtered_data}
        return cls(**{**default_data, **filtered_data})
        # return cls(**{col[0]: row[idx] for idx, col in enumerate(cur.description)})
    row_factory = _row_factory # just an alias so that when you type it out it doesn't place () at the end in pycharm

    @classmethod
    async def _validate_query(cls, db: aiosqlite.Connection, query: str):
        try:
            await db.execute(f"EXPLAIN {query}")
            return True
        except aiosqlite.DatabaseError as e:
            print(f"Error in query: {e}")
            return False

    @classmethod
    async def _exists(cls, db: aiosqlite.Connection, check_old_name: bool=False) -> bool:
        tablename = cls.__old_tablename__ if check_old_name and cls.__old_tablename__ is not None else cls.__tablename__
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tablename,)) as cur:
            name = await cur.fetchone()
        return name is not None

    @classmethod
    async def _execute_query(cls, db: aiosqlite.Connection, query: str, params: tuple | dict=None):
        is_valid = cls._validate_query(db, query)
        if is_valid:
            await db.execute(query, params)

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        """
        Called to create a table and add it to the database
        """
        await db.execute(f"CREATE TABLE IF NOT EXISTS {cls.__tablename__}(rowid INTEGER PRIMARY KEY)")

    @classmethod
    async def alter_table(cls, db: aiosqlite.Connection):
        """
        Called during the setup phase if the table is marked as altered in the metadata
        """
        raise TableSubclassMustImplement

    @classmethod
    async def drop_table(cls, db: aiosqlite.Connection):
        """
        Called to drop an existing table from the database
        """
        await db.execute(f"DROP TABLE IF EXISTS {cls.__tablename__}")

    @classmethod
    async def create_temp_copy(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE temp_{cls.__tablename__}
        AS SELECT * FROM {cls.__tablename__}
        """
        await db.execute(query)

    @classmethod
    async def insert_from_temp(cls, db: aiosqlite.Connection):
        """
        Depending on what has changed in the schema this may need an override
        """
        query = f"""
        INSERT INTO {cls.__tablename__}
        SELECT * FROM temp_{cls.__tablename__}
        """
        await db.execute(query)

    @classmethod
    async def drop_temp(cls, db: aiosqlite.Connection):
        await db.execute(f"DROP TABLE IF EXISTS temp_{cls.__tablename__}")

    @classmethod
    async def rename_from_old(cls, db: aiosqlite.Connection):
        old_exists = await cls._exists(db, check_old_name=True)
        new_exists = await cls._exists(db)
        if old_exists and not new_exists:
            await db.execute(f"ALTER TABLE {cls.__old_tablename__} RENAME TO {cls.__tablename__}")
            logger.debug(f"DBInterface: Renamed table: {cls.__old_tablename__} to {cls.__tablename__}")
        elif old_exists and new_exists:
            logger.debug(f"Didn't rename table: {cls.__old_tablename__} because table: {cls.__tablename__} already exists")

    @classmethod
    async def update_schema(cls, db: aiosqlite.Connection):
        """
        Override if a custom set of steps is needed
        """
        try:
            await cls.drop_temp(db)
            await cls.create_temp_copy(db)
            await cls.drop_table(db)
            await cls.create_table(db)
            await cls.insert_from_temp(db)
            await cls.drop_temp(db)
        except aiosqlite.OperationalError as e:
            logger.error(f"Issue updating schema for table: {cls.__tablename__}", exc_info=True)
            await db.rollback()
            raise
        logger.debug(f"The schema for table: {cls} was updated and data migrated")



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

    @classmethod
    async def drop_triggers(cls, db: aiosqlite.Connection):
        query = f"""
        SELECT name FROM sqlite_master
        WHERE type = 'trigger' AND tbl_name = '{cls.__tablename__}'
        """
        trigger_names = await db.execute_fetchall(query)
        for name in trigger_names:
            name = name[0]
            await db.execute(f"DROP TRIGGER IF EXISTS {name}")

    def asdict(self): return asdict(self)

    def astuple(self): return astuple(self)

    async def insert(self, db: aiosqlite.Connection):
        """
        Inserts the instance into the table, ignores the row with no error on a conflict
        """
        field_count = self.__class__.__field_count()
        placeholders = ",".join('?' for _ in range(field_count))
        query = f"INSERT OR IGNORE INTO {self.__tablename__} VALUES ({placeholders})"
        await db.execute(query, self.astuple())

    async def upsert(self, db: aiosqlite.Connection) -> "Table":
        """
        Attempts to insert the row and on a conflict updates values for proper insertion
        """
        raise TableSubclassMustImplement

    async def update(self, db: aiosqlite.Connection) -> "Table":
        """
        Updates the row in the table using its primary keys as reference
        """
        raise TableSubclassMustImplement


    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, *args, **kwargs) -> "Table":
        """
        Override to select a row from the table, returning an instance of the Table as the row
        """
        raise TableSubclassMustImplement

    async def select(self, db: aiosqlite.Connection) -> "Table":
        """
        Selects a row from the table using a table instance for key values.
        Override to add functionality
        """
        raise TableSubclassMustImplement
        # return None

    # noinspection PyMethodParameters
    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, *args, **kwargs) -> "Table":
        """
        Override to delete a row from the table, returning an instance of the Table as the deleted row
        """
        raise TableSubclassMustImplement

    async def delete(self, db: aiosqlite.Connection) -> "Table":
        """
        Deletes a row from the table using a table instance for key values.
        Override to add functionality
        """
        raise TableSubclassMustImplement


@dataclass
class TableMetadata(Table, schema_version=1, trigger_version=1):
    table_name: str
    schema_version: int=-1
    trigger_version: int=-1
    
    @classmethod
    def from_table(cls, table: type["Table"]) -> "TableMetadata":
        return cls(
            table_name=table.__tablename__, 
            schema_version=table.__schema_version__, 
            trigger_version=table.__schema_version__
            )

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {TableMetadata}(
            table_name TEXT,
            schema_version INTEGER,
            trigger_version INTEGER,
            PRIMARY KEY (table_name)
        )
        """
        await db.execute(query)
    
    async def insert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT INTO {TableMetadata}(table_name, schema_version, trigger_version)
        VALUES (:table_name, :schema_version, :trigger_version)
        """
        await db.execute(query, self.asdict())

    async def upsert(self, db: aiosqlite.Connection) -> "Table":
        query = f"""
        INSERT INTO {TableMetadata}(table_name, schema_version, trigger_version)
        VALUES(:table_name, :schema_version, :trigger_version)
        ON CONFLICT(table_name) 
        DO UPDATE SET schema_version = :schema_version, trigger_version = :trigger_version
        returning *
        """
        db.row_factory = TableMetadata.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def selectValue(cls, db: aiosqlite.Connection, table_name: str) -> "TableMetadata":
        query = f"""
        SELECT * FROM {TableMetadata}
        WHERE table_name = ?
        """
        db.row_factory = TableMetadata.row_factory
        async with db.execute(query, (table_name,)) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def selectSchemaVersion(cls, db: aiosqlite.Connection, table_name: str) -> int:
        query = f"""
        SELECT schema_version FROM {TableMetadata}
        WHERE table_name = ?
        """
        db.row_factory = aiosqlite.Row
        try:
            async with db.execute(query, (table_name,)) as cur:
                res = await cur.fetchone()
        except aiosqlite.OperationalError as e:
            logger.warn(f"Could not find version for Table: {table_name}")
            res = None
        ver = res["version"] if res is not None else -1
        return ver
    

class ConnectionPool:
    def __init__(self, db_path: str, pool_size: int):
        self.db_path = db_path
        self._pool: Queue[aiosqlite.Connection] = Queue(maxsize=pool_size)
        self._init_pool(pool_size)

    def _init_pool(self, pool_size):
        logger.debug(f"Initializing ConnectionPool: {repr(self)}")
        for _ in range(pool_size):
            self._pool.put_nowait(None) # placeholder for connection
        logger.debug(f"Initialized ConnectionPool: {repr(self)} - Size: {pool_size}")

    async def close(self):
        logger.debug(f"Closing ConnectionPool: {repr(self)}")
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()
            logger.debug(f"Connection closed by pool: {repr(self)} - conn: {repr(conn)}")
        logger.debug(f"Closed ConnectionPool: {repr(self)}")

    async def _create_connection(self) -> aiosqlite.Connection:
        logger.debug(f"Opening Connection")
        conn = await aiosqlite.connect(self.db_path)
        logger.debug(f"Opened Connection: {repr(conn)}")
        return conn

    async def get(self):
        conn = await self._pool.get()
        if conn is None:
            conn = await self._create_connection()
        logger.debug(f"Connection retrieved from pool: {repr(self)} - conn: {repr(conn)}")
        return conn

    async def release(self, conn: aiosqlite.Connection):
        if self._pool.qsize() < self._pool.maxsize:
            await self._pool.put(conn)
            logger.debug(f"Connection released to pool: {repr(self)} - conn: {repr(conn)}")
        else:
            await conn.close()
            logger.debug(f"Connection closed by pool: {repr(self)} - conn: {repr(conn)}")


class ConnectionContext:
    def __init__(self, connection_pool: ConnectionPool, autocommit: bool=False):
        self.pool = connection_pool
        self._conn: aiosqlite.Connection = None
        self.autocommit = autocommit

    async def __aenter__(self) -> aiosqlite.Connection:
        self._conn = await self.pool.get()
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            self._conn.row_factory = None
            await self.pool.release(self._conn)
            if self.autocommit:
                await self._conn.commit()
            self._conn = None
        return True


class ManagerMeta(type):
    def __new__(mcs, name, bases, class_dict, *args,
                table_registry: type["TableRegistry"]=TableRegistry, **kwargs):
        cls = super().__new__(mcs, name, bases, class_dict)
        cls.__table_registry__ = table_registry
        if table_registry is None:
            raise ValueError(f"table_registry for class: {name} cannot be None")
        return cls

    @property
    def registry(cls) -> type["TableRegistry"]:
        return cls.__table_registry__


class DatabaseManager(metaclass=ManagerMeta, table_registry=TableRegistry):
    @property
    def registry(self) -> type["TableRegistry"]:
        return self.__class__.__table_registry__
    
    def __init__(self, db_path: str, pool_size: int=5):
        self.file_path = db_path
        self.pool = ConnectionPool(db_path, pool_size)
        asyncio.run(self._initialize_resources())

    async def _initialize_resources(self):
        logger.debug(f"Initializing resources for Manager: {repr(self)}")
        await self.setup(table_group=__name__)
        logger.debug(f"Initialized resources for Manager: {repr(self)}")

    async def setup(self, table_group: str=None,
                    ignore_schema_updates: bool=False, ignore_trigger_updates: bool=False,
                    drop_tables=False, drop_triggers=False):
        
        async with self.conn() as db:
            """
            Performs automated tables setup with the passed kwargs
            """
            # drop tables if config set
            # update table as long as it isn't forbidden
            # the registry then gets called to attemp to update schemas
            if drop_tables:
                await DatabaseManager.registry.drop_tables(db, group_name=table_group)
            elif not ignore_schema_updates:
                try:
                    # await self.__table_registry__.alter_tables(db, group_name=table_group)
                    await DatabaseManager.registry.update_schemas(db, group_name=table_group)
                except aiosqlite.Error as e:
                    logger.error(f"Table Update error on group {table_group}", exc_info=True)
                    await db.rollback()
                    raise

            if drop_triggers:
                await DatabaseManager.registry.drop_triggers(db, group_name=table_group)
            elif not ignore_trigger_updates:
                try:
                    await self.registry.update_triggers(db, table_group)
                except aiosqlite.Error as e:
                    message = f"Trigger Update error on group: {table_group}"
                    logger.error(message, exc_info=True)
                    await db.rollback()
                    raise
            await DatabaseManager.registry.create_tables(db, table_group)
            await DatabaseManager.registry.create_triggers(db, table_group)
            await db.commit()
        logger.debug(f"Setup Table Group: {table_group}")

    def conn(self, autocommit=False):
        """
        Give a connection context object for use within a context manager statement
        Ex.
        async with db_manager.connection() as conn:
            pass
        """
        return ConnectionContext(self.pool, autocommit)

    async def create_tables(self, table_group: str=None):
        async with self.conn() as db:
            await DatabaseManager.__table_registry__.create_tables(db, table_group)
            await db.commit()

    async def alter_tables(self, table_group: str=None):
        async with self.conn() as db:
            await DatabaseManager.__table_registry__.alter_tables(db, table_group)
            await db.commit()

    async def drop_tables(self, table_group: str=None):
        async with self.conn() as db:
            await DatabaseManager.__table_registry__.drop_tables(db, table_group)
            await db.commit()

    async def drop_triggers(self, table_group: str=None):
        async with self.conn() as db:
            await self.__table_registry__.drop_triggers(db, group_name=table_group)
            await db.commit()


    async def drop_table(self, tablename: str):
        async with self.conn() as db:
            table: type[Table] = self.__table_registry__.get_table(tablename)
            await table.drop_table(db)
            await db.commit()

    async def drop_unregistered(self):
        async with self.conn() as db:
            await self.__table_registry__.drop_unregistered(db)
            await db.commit()

    async def update_tables(self):
        async with self.conn() as db:
            try:
                await self.__table_registry__.alter_tables(db)
                await self.__table_registry__.update_schema(db)
                await db.commit()
            except aiosqlite.Error as e:
                logger.error(f"Table Update error:\n {e}", exc_info=True)
                await db.rollback()
                raise

    __AsyncFunctionType = typing.Callable[[aiosqlite.Connection], typing.Awaitable]
    async def handle(self, functions: tuple[__AsyncFunctionType]) -> list[typing.Any]:
        async with self.conn() as db:
            results = []
            for function in functions:
                result = await function(db)
                results.append(result)
            await db.commit()
        return results
