from typing import ClassVar, override, Any, cast
from enum import Flag, Enum, IntEnum, IntFlag, auto
import aiosqlite
from dataclasses import dataclass
from wavelink import Playable, Playlist, Node

from discord import guild
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
class TrackListDetails(Table, schema_version=1, trigger_version=1):
    class Flags(IntFlag):
        session = auto()

    guild_id: int
    name: str
    start_index: int=0
    flags: Flags=Flags(0)

    @override
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {TrackListDetails}(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            start_index INTEGER NOT NULL DEFAULT 0,
            flags INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, name),
            FOREIGN KEY (guild_id) REFERENCSE {Guild}(id)
        """

    @override
    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackListDetails}_insert_settings_before_insert
            BEFORE INSERT ON {TrackListDetails}
            BEGIN
                INSERT INTO {MusicSettings}(guild_id)
                VALUES(NEW.guild_id)
                ON CONFLICT DO NOTHING;
            END
            """
        ]
        for t in triggers:
            await db.execute(t)

    @override
    async def insert(self, db: aiosqlite.Connection) -> None:
        query = f"""
        INSERT OR IGNORE INTO {TrackListDetails}(guild_id, name, start_index, flags)
        VALUES (:guild_id, :name, :start_index, :flags)
        """
        await db.execute(query, self.asdict())

    @override
    async def upsert(self, db: aiosqlite.Connection) -> None:
        query = f"""
        INSERT {TrackListDetails}(guild_id, name, start_index, flags)
        VALUES (:guild_id, :name, :start_index, :flags)
        ON CONFLICT (guild_id, name)
        DO UPDATE SET
            start_index = :start_index,
            flags = :flags
        """
        await db.execute(query, self.asdict())

    @override
    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "TrackListDetails | None":
        query = f"""
        SELECT * FROM {TrackListDetails}(guild_id, name, start_index, flags)
        WHERE guild_id = ? AND name = ?
        """
        async with db.execute(query, (guild_id, name)) as cur:
            res: TrackListDetails = await cur.fetchone() # pyright: ignore [reportAssignmentType]
        return res



@dataclass
class TrackList(Table, schema_version=1, trigger_version=1):
    guild_id: int
    name: str
    index: int # starting at 0, represents order in playlist
    encoded: str # encoded string representing the track from lavalink
    # track_data: bytes

    # async def toWavelink(self, node: Node) -> Playable:
    #     pass

    @classmethod
    def from_wavelink(cls, track: Playable, guild_id: int, name: str, index: int=0):
        return TrackList(guild_id=guild_id, 
                         name=name,
                         index=index,
                         encoded=track.encoded)

    @classmethod
    async def insert_wavelink_tracks(cls, db: aiosqlite.Connection, tracks: list[Playable], guild_id: int, name: str) -> None:
        for i, track in enumerate(tracks):
            await TrackList.from_wavelink(track, guild_id, name, i+1).insert(db)
    
    @override
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {TrackList}(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            index INTEGER NOT NULL,
            encoded TEXT NOT NULL,
            UNIQUE (guild_id, name, index),
            FOREIGN KEY (guild_id) REFERENCSE {Guild}(id)
        """
        await db.execute(query)

    @override
    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackList}_shift_indices_after_insert
            AFTER INSERT ON {TrackList}
            BEGIN
                UPDATE Track
                SET index = index + 1
                WHERE (guild_id = NEW.guild_id) AND (name = NEW.name) AND 
                (index >= NEW.index) AND (rowid != NEW.rowid);
            END;
            """,
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackList}_shift_indices_after_update
            AFTER UPDATE OF index ON {TrackList}
            BEGIN
                UPDATE Track
                SET index = index + 1
                WHERE (guild_id = NEW.guild_id) AND (name = NEW.name) 
                AND (index >= NEW.index) AND (index < OLD.index) AND (rowid != OLD.rowid);
                UPDATE Track
                SET index = index - 1
                WHERE (guild_id = NEW.guild_id) AND (name = NEW.name) 
                AND (index > OLD.index) AND (index <= NEW.index) AND (rowid != OLD.rowid);
            END
            """,
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackList}_insert_details_before_insert
            BEFORE INSERT ON {TrackList}
            BEGIN
                INSERT INTO {TrackListDetails}(guild_id, name)
                VALUES(NEW.guild_id, NEW.name)
                ON CONFLICT DO NOTHING;
            END
            """,
        ]
        for t in triggers:
            await db.execute(t)

    @override
    async def insert(self, db: aiosqlite.Connection) -> int:
        query = f"""
        INSERT INTO {TrackList}(guild_id, name, index, encoded)
        VALUES (
            :guild_id, 
            :name, 
            (
                SELECT Coalesce(Max(index), 0)
                FROM {TrackList} WHERE (guild_id = :guild_id) AND (name = :name)
            ), 
            :encoded
        )
        RETURNING index
        """
        db.row_factory = TrackList.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query) as cur:
            res: TrackList = await cur.fetchone() # pyright: ignore [reportAssignmentType]
        return res.index

    @override
    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str, index: int, **kwargs: dict[str, Any]) -> "TrackList":
        query = f"""
        SELECT * FROM {TrackList}(guild_id, name, index, encoded)
        WHERE guild_id = ? AND name = ? AND index = ?
        """
        db.row_factory = TrackList.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query, (guild_id, name, index)) as cur:
            res = await cur.fetchone()
            assert isinstance(res, TrackList)
        return cast(TrackList, res)

    @classmethod
    async def selectAllWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> list["TrackList"]:
        query = f"""
        SELECT * FROM {TrackList}(guild_id, name, index, encoded)
        WHERE guild_id = ? AND name = ?
        ORDER BY index
        """
        db.row_factory = TrackList.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query, (guild_id, name)) as cur:
            res = await cur.fetchall()
        return cast(list[TrackList], res) # don't worry this is fine, row factory makes this fine


    


@dataclass
class FavoriteTrack(Table, schema_version=1, trigger_version=1):
    MAX_DURATION: ClassVar[int] = 5 * 1000 # in milliseconds
    user_id: int
    encoded: str
    start: int # in milliseconds
    end: int

