import abc

import aiosqlite
from dataclasses import dataclass, asdict, astuple
from enum import Enum, Flag, IntFlag, auto
import discord


"""
Potential plans outside of the database file
Still need to maintain internal classes the represent stuff from the database and ways to write back to the database
Dataclasses can represent the various objects and have their own methods to writing to the database
"""

"""
Writing data,
Editing data,
querying data

Query data -> dataclass
edit dataclass instance
writing data (update the table)
"""

"""
example flow based off of the planned new sentinel system
reminder to not invent patterns but to let them emmerge

On Message ->
SentinelEvent ->
Query global SentinelSettings for overall sentinel rules
Query Server SentinelSettings for general sentinel rules

make decisions based off of the settings

bracnh, reaction or message

branch-reaction: 
iteracte through server sentinels with reaction triggers
do thing

iterate through global sentinels with reaction triggers
do thing

branch-message: 
iterate throgh server message sentinels (priority)
do thing

iterate through global message sentinels (if enabled)
do thing


SentinelGroup Object
id INTEGER AUTO INCREMENT PRIMARY KEY,
name TEXT NOT NULL,

Sentinel Object
id INTEGER AUTO INCREMENT,
group_id INTEGER FOREIGN KEY REFERENCES SentinelGroup(id),
trigger_type INTEGER DEFAULT 0,
trigger TEXT,
response_type INTEGER DEFAULT 0,
response TEXT,

// Creation check \/
CHECK (trigger IS NOT NULL or response IS NOT NULL)
That way you can't put an empty sentinel into the table
"""


"""
SERVER
GLOBAL

Tags
Sentinels
Sounds
Playlists
Tracks
"""

"""
In cog_load, alter the settings tables to add the specific settings
def cog_load():
    await self.bot.database.alter_table("table_name", "")
    
def cog_load():
    async with aiosql.connect(self.bot.config.db_path) as db:
        

"""
# class GuildFlags(IntFlag):
#     enable_sentinels = auto()
#     enable_tags = auto()
#     public_tags = auto()
#     global_tags = auto()
#     fish_mode = auto()

# @dataclass
# class GuildSettings:
#     guild_id: int
#     flags: GuildFlags = (GuildFlags.enable_sentinels |
#                          GuildFlags.enable_tags)
#
#     # other bits of data can be here too



class Database:
    @dataclass
    class Row:
        QUERY_CREATE_TABLE = ""
        QUERY_INSERT = ""
        QUERY_SELECT = ""
        def __init__(self, *args, **kwargs): pass
        def asdict(self): return asdict(self)

        def astuple(self): return astuple(self)
        @classmethod
        def rowFactory(cls, cur: aiosqlite.Cursor, row: tuple):
            """Instantiates the dataclass from a row in the SQL table"""
            return cls(**{col[0]: row[idx] for idx, col in enumerate(cur.description)})

    @dataclass
    class Guild(Row):
        id: int
        name: str
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS Guild (
        id INTEGER,
        name TEXT DEFAULT 'Unknown',
        PRIMARY KEY (id))
        """
        QUERY_INSERT = """
        INSERT INTO Guild (id, name)
        VALUES (:id, :name)
        ON CONFLICT (id)
        DO UPDATE SET name = :name
        RETURNING *
        """
        QUERY_SELECT = """
        SELECT * FROM Guild
        WHERE id = ?
        """
        QUERY_DELETE = """
        DELETE FROM Guild
        WHERE id = ?
        RETURNING *
        """

        @classmethod
        def fromDiscord(cls, guild=discord.Guild):
            return cls(id=guild.id, name=guild.name)

    @dataclass
    class GuildSettings(Row):
        guild_id: int
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS GuildSettings(
        guild_id INTEGER,
        FOREIGN KEY (guild_id) REFERENCES Guild(id)
        ON UPDATE CASCADE ON DELETE CASCADE)
        """
        QUERY_INSERT = """
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
        QUERY_DELETE = """
        DELETE FROM GuildSettings
        WHERE guild_id = ?
        RETURNING *
        """

    def __init__(self, database_path: str):
        self.file_path: str = database_path

    async def init(self):
        await self.dropTables()
        await self.createTables()
        # await self.createGlobalTable()

    async def dropTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute("DROP TABLE IF EXISTS GuildSettings")
            await db.execute("DROP TABLE IF EXISTS Guilds")
            await db.commit()

    async def createTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(Database.Guild.QUERY_CREATE_TABLE)
            await db.execute(Database.GuildSettings.QUERY_CREATE_TABLE)
            await db.commit()

    async def upsertGuild(self, guild: Guild) -> Guild:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = guild.rowFactory
            new_guild: Database.Guild = await db.execute_fetchall(guild.QUERY_INSERT, guild.asdict())
            await db.commit()
        return new_guild

    async def upsertGuilds(self, guilds: list[Guild]) -> list[Guild]:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = Database.Guild.rowFactory
            guilds: list[Database.Guild] = await db.executemany(Database.Guild.QUERY_INSERT, guilds)
            await db.commit()
        return guilds

    async def upsertGuildSettings(self, guild_settings: GuildSettings) -> GuildSettings:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = guild_settings.rowFactory
            new_settings: Database.GuildSettings = await db.execute_fetchall(guild_settings.QUERY_INSERT, guild_settings.asdict())
            await db.commit()
        return new_settings

    async def fetchGuild(self, guild_id: int) -> Guild:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = Database.Guild.rowFactory
            guild: Database.Guild = await db.execute_fetchall(Database.Guild.QUERY_SELECT, (guild_id,))
            await db.commit()
            return guild

    async def deleteGuild(self, guild_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            deleted_guild = await db.execute_fetchall(Database.Guild.QUERY_DELETE, (guild_id,))
            await db.commit()
            return deleted_guild

    async def deleteGuildSettings(self, guild_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            deleted_settings = await db.execute_fetchall(Database.GuildSettings.QUERY_DELETE, (guild_id,))
            await db.commit()
            return deleted_settings

