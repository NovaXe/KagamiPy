from typing import ClassVar, override
import aiosqlite
from dataclasses import dataclass
from common.database import Table, DatabaseManager
from common.tables import Guild, GuildSettings, User

@dataclass
class MusicSettings(Table, schema_version=1, trigger_version=1):
    guild_id: int
    music_enabled: bool=True
    saving_enabled: bool=True

    @override
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {MusicSettings}(
            guild_id INTEGER NOT NULL,
            music_enabled INTEGER DEFAULT 1,
            saving_enabled INTEGER DEFAULT 1,
            PRIMARY KEY(guild_id),
            FOREIGN KEY(guild_id) REFERENCES {Guild}(id)
            ON UPDATE CASCADE ON DELETE CASCADE
        )
        """
        await db.execute(query)

    @override
    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        trigger = f"""
        CREATE TRIGGER IF NOT EXISTS {MusicSettings}_insert_guild_before_insert
        BEFORE INSERT ON {MusicSettings}
        BEGIN
            INSERT OR IGNORE INTO {Guild}(id)
            VALUES (NEW.guild_id);
        END
        """
        await db.execute(trigger)

    @override
    async def upsert(self, db: aiosqlite.Connection) -> "MusicSettings":
        query = f"""
        INSERT INTO {MusicSettings} (guild_id, music_enabled)
        VALUES (:guild_id, :music_enabled)
        ON CONFLICT (guild_id)
        DO UPDATE SET music_enabled = :music_enabled
        RETURNING *
        """
        db.row_factory = MusicSettings.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query, self.asdict()) as cur:
            result = await cur.fetchone()
        assert isinstance(result, MusicSettings)
        return result

@dataclass
class TrackList(Table, schema_version=1, trigger_version=1):
    guild_id: int
    name: str
    position: int # starting at 1, represents order in playlist
    encoded: str # encoded string representing the track from lavalink
    
    @override
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {TrackList}(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            position INTEGER NOT NULL,
            encoded TEXT NOT NULL,
            UNIQUE (guild_id, name, position),
            FOREIGN KEY (guild_id) REFERENCSE {Guild}(id)
        """
        pass

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackList}_insert_settings_before_insert
            BEFORE INSERT ON {TrackList}
            BEGIN
                INSERT INTO {MusicSettings}(guild_id)
                VALUES(NEW.guild_id)
                ON CONFLICT DO NOTHING;
            END
            """,
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackList}_shift_indices_after_insert
            AFTER INSERT ON {TrackList}
            BEGIN
                UPDATE Track
                SET position = track_index + 1
                WHERE (guild_id = NEW.guild_id) AND (name = NEW.name) AND 
                (position >= NEW.position) AND (rowid != NEW.rowid);
            END;
            """
        ]
        for t in triggers:
            await db.execute(t)


    


@dataclass
class FavoriteTrack(Table, schema_version=1, trigger_version=1):
    MAX_DURATION: ClassVar[int] = 5 * 1000 # in milliseconds
    user_id: int
    encoded: str
    start: int # in milliseconds
    end: int

