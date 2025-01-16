from __future__ import annotations
from typing import ClassVar, override, Any, cast, Annotated
from enum import Flag, Enum, IntEnum, IntFlag, auto
import aiosqlite
from aiosqlite import Connection
from dataclasses import dataclass
from wavelink import Playable, Playlist, Node

from discord import guild
from common.database import Table, DatabaseManager
from common.errors import CustomCheck
from common.logging import setup_logging
from common.tables import Guild, GuildSettings, User

logger = setup_logging(__name__)

@dataclass
class MusicSettings(Table, schema_version=1, trigger_version=1):
    guild_id: int
    music_enabled: bool=True
    saving_enabled: bool=True

    @override
    @classmethod
    async def create_table(cls, db: Connection):
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
    async def create_triggers(cls, db: Connection):
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
    async def upsert(self, db: Connection) -> "MusicSettings":
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
        """Never change these, only add on to the end. They're used in the database so 1 must always be 1"""
        session = 1
    _columns: ClassVar[str] = "(guild_id, name, start_index, flags)"

    guild_id: int
    name: str
    start_index: int=0
    flags: Flags=Flags(0)

    def validate_name(self) -> None:
        if self.flags & TrackListDetails.Flags.session and not self.name.isnumeric():
            logger.error(f"TrackList name should be numeric, found {self.name}")
            raise ValueError(f"TrackList name should be numeric, found {self.name}")

    @override
    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {TrackListDetails}(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            start_index INTEGER NOT NULL DEFAULT 0,
            flags INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, name),
            FOREIGN KEY (guild_id) REFERENCSE {Guild}(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        """

    @override
    @classmethod
    async def create_triggers(cls, db: Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackListDetails}_insert_settings_before_insert
            BEFORE INSERT ON {TrackListDetails}
            BEGIN
                INSERT INTO {MusicSettings}(guild_id)
                VALUES(NEW.guild_id)
                ON CONFLICT DO NOTHING;
            END
            """,
            f"""
            CREATE TRIGGER IF NOT EXISTS {TrackListDetails}_delete_old_sessions_before_insert
            BEFORE INSERT ON {TrackListDetails}
            BEGIN
                CASE 
                WHEN (NEW.Flags & {TrackListDetails.Flags.session} != 0)
                    DELETE * FROM {TrackListDetails}
                    WHERE guild_id = NEW.guild_id AND flags & {TrackListDetails.Flags.session} != 0
                    ORDER BY CAST(name AS INTEGER) ASC
                    LIMIT -1 OFFSET 3;
            END
            """
        ]
        for t in triggers:
            await db.execute(t)

    @classmethod
    async def selectWhereName(cls, db: Connection, guild_id: int, name: str) -> "TrackListDetails":
        query = f"""
        SELECT * FROM {TrackListDetails}{TrackListDetails._columns}
        WHERE guild_id = ? AND name = ?
        """
        db.row_factory = TrackListDetails.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query, (guild_id, name)) as cur:
            res: TrackListDetails = await cur.fetchone() # pyright: ignore [reportAssignmentType]
        return res

    @classmethod
    async def selectPriorSession(cls, db: Connection, guild_id: int) -> "TrackListDetails | None":
        query = f"""
        SELECT * FROM {TrackListDetails}{TrackListDetails._columns}
        WHERE guild_id = ? AND ((flags & {TrackListDetails.Flags.session}) == {TrackListDetails.Flags.session})
        ORDER BY CAST(name AS INTEGER) DESC
        """
        db.row_factory = TrackListDetails.row_factory # pyright: ignore [reportAttributeAccessIssue]
        async with db.execute(query, (guild_id,)) as cur:
            res: TrackListDetails | None = await cur.fetchone() # pyright: ignore [reportAssignmentType]
        return res

    @classmethod
    async def selectAllWhereFlag(cls, db: Connection, guild_id: int, flags: Flags) -> list["TrackListDetails"]:
        query = f"""
        SELECT * FROM {TrackListDetails}{TrackListDetails._columns}
        WHERE guild_id = :guild_id AND ((flags & :flags) == :flags)
        """
        db.row_factory = TrackListDetails.row_factory # pyright: ignore [reportAttributeAccessIssue]
        async with db.execute(query, {"guild_id": guild_id, "flags": flags}) as cur:
            res: list[TrackListDetails] = await cur.fetchall() # pyright: ignore [reportAssignmentType]
        return res

    @override
    async def insert(self, db: Connection) -> None:
        self.validate_name()
        query = f"""
        INSERT OR IGNORE INTO {TrackListDetails}{TrackListDetails._columns}
        VALUES (:guild_id, :name, :start_index, :flags)
        """
        await db.execute(query, self.asdict())

    @override
    async def upsert(self, db: Connection) -> None:
        self.validate_name()
        query = f"""
        INSERT {TrackListDetails}{TrackListDetails._columns}
        VALUES (:guild_id, :name, :start_index, :flags)
        ON CONFLICT (guild_id, name)
        DO UPDATE SET
            start_index = :start_index,
            flags = :flags
        """
        await db.execute(query, self.asdict())




@dataclass
class TrackList(Table, schema_version=1, trigger_version=1):
    guild_id: int
    name: str
    index: int # starting at 0, represents order in playlist
    encoded: str # encoded string representing the track from lavalink
    # track_data: bytes

    # async def toWavelink(self, node: Node) -> Playable:
    #     pass

    def validate_name(self) -> bool:
        if not self.name.isnumeric():
            logger.error(f"TrackList name should be numeric, found {self.name}")
            return False
        return True

    @classmethod
    def from_wavelink(cls, track: Playable, guild_id: int, name: str, index: int=0):
        return TrackList(guild_id=guild_id, 
                         name=name,
                         index=index,
                         encoded=track.encoded)

    async def to_wavelink(self, node: Node) -> Playable:
        data = await node.send(path="/v4/decodetrack", params={"encodedTrack": ...}) # pyright: ignore [reportAny]
        return Playable(data) # pyright: ignore [reportAny]

    @classmethod
    async def insert_wavelink_tracks(cls, db: Connection, tracks: list[Playable], guild_id: int, name: str) -> None:
        for i, track in enumerate(tracks):
            await TrackList.from_wavelink(track, guild_id, name, i+1).insert(db)
    
    @override
    @classmethod
    async def create_table(cls, db: Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {TrackList}(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            index INTEGER NOT NULL,
            encoded TEXT NOT NULL,
            UNIQUE (guild_id, name, index),
            FOREIGN KEY (guild_id, name) REFERENCES {TrackListDetails}(guild_id, name)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        """
        await db.execute(query)

    @override
    @classmethod
    async def create_triggers(cls, db: Connection):
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
    async def insert(self, db: Connection) -> int:
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
    async def selectWhere(cls, db: Connection, guild_id: int, name: str, index: int, **kwargs: dict[str, Any]) -> "TrackList":
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
    async def selectAllWhere(cls, db: Connection, guild_id: int, name: str) -> list["TrackList"]:
        query = f"""
        SELECT * FROM {TrackList}(guild_id, name, index, encoded)
        WHERE guild_id = ? AND name = ?
        ORDER BY index
        """
        db.row_factory = TrackList.row_factory # pyright: ignore[reportAttributeAccessIssue]
        async with db.execute(query, (guild_id, name)) as cur:
            res = await cur.fetchall()
        return cast(list[TrackList], res) # don't worry this is fine, row factory makes this fine
    
    @classmethod
    async def selectAllWavelink(cls, db: Connection, node: Node, guild_id: int, name: str) -> list[Playable]:
        tracks: list[TrackList] = await cls.selectAllWhere(db, guild_id, name)
        playable_tracks: list[Playable] = []
        for track in tracks:
            playable_tracks += [await track.to_wavelink(node)]
        return playable_tracks


@dataclass
class FavoriteTrack(Table, schema_version=1, trigger_version=1):
    MAX_DURATION: ClassVar[int] = 5 * 1000 # in milliseconds
    user_id: int
    encoded: str
    start: int # in milliseconds
    end: int

