import aiosqlite as aiosql
from dataclasses import dataclass


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
group_id INTEGER FOREIGN KEY REFERENCES SentinelGroup.id,
trigger_type INTEGER DEFAULT 0,
trigger TEXT,
response_type INTEGER DEFAULT 0,
response TEXT,

// Creation check \/
CHECK (trigger IS NOT NULL or response IS NOT NULL)
That way you can't put an empty sentinel into the table
"""




async def initializeServerTables(database_file: str):
    async with aiosql.connect(database_file) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS Servers (
        id INTEGER PRIMARY KEY,
        name TEXT DEFAULT 'Unknown')
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS ServerSettings (
        server_id INTEGER FOREIGN KEY REFERENCES Servers.id,
        fish_mode INTEGER DEFAULT 0)
        """)

        await db.commit()





async def addServer(database_file: str, server_id: int, server_name: str):
    async with aiosql.connect(database_file) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS
            
            """)
