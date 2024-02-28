import aiosqlite
from dataclasses import dataclass
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
    def __init__(self, database_path: str):
        self.file_path: str = database_path

    async def init(self):
        await self.createGuildTables()
        # await self.createGlobalTable()

    async def createGuildTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute("DROP TABLE IF EXISTS GuildSettings")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Guilds (
            id INTEGER PRIMARY KEY,
            name TEXT DEFAULT 'Unknown')
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS GuildSettings (
            guild_id INTEGER,
            FOREIGN KEY(guild_id) REFERENCES Guilds(id))
            """)
            await db.commit()

    async def upsertGuild(self, guild_id: int, guild_name: str):
        """
        Attempts to insert a new guild but if it already exists, simply update the fields
        """
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute_insert("""
            INSERT INTO Guilds (id, name)
            VALUES (:id, :name)
            ON CONFLICT (id)
            DO UPDATE SET name = :name
            """, {"id": guild_id, "name": guild_name})
            await db.commit()

    async def upsertSyncGuilds(self, guilds: list[discord.Guild]):
        async with aiosqlite.connect(self.file_path) as db:
            guild_list = [{"id": guild.id, "name": guild.name} for guild in guilds]
            guild_ids = tuple(guild["id"] for guild in guild_list)
            await db.execute(f"""
            DELETE FROM Guilds
            WHERE id NOT IN {guild_ids}
            """)

            await db.executemany("""
            INSERT INTO Guilds (id, name) 
            VALUES (:id, :name)
            ON CONFLICT(id) 
            DO UPDATE SET name = :name
            """, guild_list)
            await db.commit()

    async def removeGuild(self, guild_id: int):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute("""
            DELETE FROM TABLE
            WHERE id = ?
            """, (guild_id,))
            await db.commit()


    async def createGlobalTable(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS Global (
            )
            """)
            await db.commit()




