from math import ceil
from dataclasses import dataclass
from math import ceil
from typing import (Literal, Any, Union, List)

import aiosqlite
import discord
import wavelink
from discord import (app_commands, Interaction, VoiceChannel, Message, Member, VoiceState)
from discord.app_commands import Group, Transformer, Transform, Choice, Range
from discord.ext import (commands)
from discord.ext.commands import GroupCog, Cog
from discord.ui import Modal, TextInput
from discord.utils import MISSING
from wavelink import TrackEventPayload
from wavelink.exceptions import WavelinkException, InvalidLavalinkResponse

from bot.ext.ui.custom_view import MessageInfo
from bot.ext.ui.page_scroller import PageScroller, PageGenCallbacks, ITL
from bot.utils import bot_data
from bot.utils.database import Database

OldPlaylist = bot_data.Playlist
old_server_data = bot_data.server_data
OldTrack = bot_data.Track
# context vars
from bot.kagami_bot import bot_var

from bot.utils.music_utils import (
    attemptHaltResume,
    createNowPlayingWithDescriptor, createQueuePage, secondsToTime, respondWithTracks, addedToQueueMessage)
from bot.utils.wavelink_utils import createNowPlayingMessage, searchForTracks, buildTrack
from bot.utils.player import Player, player_instance
from bot.utils.wavelink_utils import WavelinkTrack
from bot.kagami_bot import Kagami
from bot.ext.ui.music import PlayerController
from bot.ext.responses import (PersistentMessage, MessageElements)
from bot.utils.interactions import respond
from bot.ext import errors
from bot.utils.pages import EdgeIndices, getQueueEdgeIndices, InfoTextElem, InfoSeparators, CustomRepr, \
    PageBehavior, createSinglePage, PageIndices
from bot.utils.utils import similaritySort


# General functions for music and playlist use
async def searchAndQueue(voice_client: Player, search):
    tracks, source = await searchForTracks(search, 1)
    await voice_client.waitAddToQueue(tracks)
    return tracks, source


async def joinVoice(interaction: Interaction, voice_channel: VoiceChannel):
    voice_client: Player = interaction.guild.voice_client
    if voice_client:
        await voice_client.move_to(voice_channel)
        voice_client = interaction.guild.voice_client
    else:
        voice_client = await voice_channel.connect(cls=Player())
    return voice_client


async def attemptToJoin(interaction: Interaction, voice_channel: VoiceChannel = None, send_response=True, ephemeral=False):
    voice_client: Player = interaction.guild.voice_client
    user_vc = user_voice.channel if (user_voice := interaction.user.voice) else None
    voice_channel = voice_channel or user_vc
    if not voice_channel: raise errors.NoVoiceChannel

    if voice_client and voice_client.channel == voice_channel:
        raise errors.AlreadyInVC("I'm already in the voice channel")

    if voice_client:
        pass
    # raise errors.AlreadyInVC

    else:
        if send_response: await respond(interaction, "Joining...", ephemeral=ephemeral, delete_after=0.5)
        voice_client = await joinVoice(interaction, voice_channel)
    return voice_client


def requireVoiceclient(begin_session=False, defer_response=True, ephemeral=False):
    async def predicate(interaction: Interaction):
        if defer_response: await respond(interaction, ephemeral=ephemeral)
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            if begin_session:
                await attemptToJoin(interaction, send_response=False, ephemeral=ephemeral)
                return True
            else:
                raise errors.NoVoiceClient
        else:
            return True

    return app_commands.check(predicate)


def requireOptionalParams(params=list[str], min_count: int=1):
    async def predicate(interaction: Interaction):
        count = 0
        for param in params:
            if param in interaction.namespace:
                count += 1
            if count >= min_count: return True
        else:
            raise errors.MissingParameters(f"Command requires at least `{min_count}` of the following parameters\n"
                                           f"`{params}`")

    return app_commands.check(predicate)


def setCommandChannel():
    async def predicate(interaction: Interaction):
        old_server_data.value.last_music_command_channel = interaction.channel
        return True
    return app_commands.check(predicate)


# def deferResponse():
#     async def predicate(interaction: Interaction):
#         await respond(interaction)
#         return True
#     return app_commands.check(predicate)
class MusicDB(Database):
    @dataclass
    class MusicSettings(Database.Row):
        guild_id: int
        music_enabled: bool = True
        playlists_enabled: bool = True
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS MusicSettings(
        guild_id INTEGER NOT NULL,
        music_enabled INTEGER DEFAULT 1,
        playlists_enabled INTEGER DEFAULT 1,
        PRIMARY KEY (guild_id),
        FOREIGN KEY(guild_id) REFERENCES Guild(id)
            ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        TRIGGER_BEFORE_INSERT_GUILD = """
        CREATE TRIGGER IF NOT EXISTS MusicSettings_insert_guild_before_insert
        BEFORE INSERT ON MusicSettings
        BEGIN
            INSERT INTO Guild(id)
            values(NEW.guild_id)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_UPSERT = """
        INSERT INTO MusicSettings (guild_id, music_enabled, playlists_enabled)
        VALUES (:guild_id, :music_enabled, :playlists_enabled)
        ON CONFLICT (guild_id)
        DO UPDATE SET music_enabled = :music_enabled, playlists_enabled = :playlists_enabled
        """
        QUERY_SELECT = """
        SELECT * FROM MusicSettings
        WHERE guild_id = ?
        """
        QUERY_DELETE = """
        DELETE FROM MusicSettings
        WHERE guild_id = ?
        """

    @dataclass
    class Playlist(Database.Row):
        guild_id: int
        name: str
        description: str = None
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS Playlist(
        guild_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT NULL,
        PRIMARY KEY (guild_id, name),
        FOREIGN KEY (guild_id) REFERENCES Guild(id) 
        ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        TRIGGER_BEFORE_INSERT_SETTINGS = """
        CREATE TRIGGER IF NOT EXISTS Playlist_insert_settings_before_insert
        BEFORE INSERT ON Playlist
        BEGIN
            INSERT INTO MusicSettings(id)
            values(NEW.guild_id)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_INSERT = """
        INSERT INTO Playlist (guild_id, name, description)
        VALUES (:guild_id, :name, :description)
        ON CONFLICT DO NOTHING
        """
        QUERY_UPSERT = """
        INSERT INTO Playlist (guild_id, name, description)
        VALUES (:guild_id, :name, :description)
        ON CONFLICT (guild_id, name)
        DO UPDATE SET description = :description
        """
        QUERY_UPDATE = """
        UPDATE Playlist SET name = :new_name, description = :new_description
        WHERE guild_id = :guild_id AND name = :name
        """
        QUERY_SELECT = """
        SELECT * FROM Playlist
        WHERE guild_id = ? AND name = ?
        """
        QUERY_DELETE = """
        DELETE FROM Playlist
        WHERE guild_id = ? AND name = ?
        RETURNING *
        """
        QUERY_SELECT_MULTIPLE = """
        SELECT * FROM Playlist
        WHERE guild_id = ?
        LIMIT ? OFFSET ?
        """
        QUERY_SELECT_ALL = """
        SELECT * FROM Playlist
        WHERE guild_id = ?
        """
        QUERY_DELETE_MULTIPLE = """
        DELETE FROM Playlist
        WHERE ROWID in (
            SELECT ROWID FROM Playlist 
            WHERE guild_id = ? 
            LIMIT ? OFFSET ?
        ) RETURNING *
        """
        QUERY_SELECT_LIKE = """
        SELECT * FROM Playlist
        WHERE guild_id = ? AND name LIKE ?
        LIMIT ? OFFSET ?
        """
        QUERY_SELECT_LIKE_NAMES = """
        SELECT name FROM Playlist
        WHERE (guild_id = ?) AND (name LIKE ?)
        LIMIT ? OFFSET ?
        """

    @dataclass
    class Track(Database.Row):
        guild_id: int
        playlist_name: str
        title: str
        duration: int
        encoded: str
        uri: str
        track_index: int = None
        # Constant representing an execution query for the track table
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS Track(
        guild_id INTEGER NOT NULL,
        playlist_name TEXT NOT NULL,
        track_index INTEGER NOT NULL,
        title TEXT DEFAULT '',
        duration INTEGER DEFAULT 0,
        encoded TEXT NOT NULL,
        uri TEXT DEFAULT '',
        FOREIGN KEY(guild_id, playlist_name) REFERENCES Playlists(guild_id, name)
        ON UPDATE CASCADE ON DELETE CASCADE)
        """ # PRIMARY KEY(guild_id, playlist_name, track_index),

        QUERY_BEFORE_INSERT_TRIGGER = """
        CREATE TRIGGER IF NOT EXISTS Track_shift_indices_before_insert
        BEFORE INSERT ON Track
        BEGIN
            UPDATE Track
            SET track_index = track_index + 1
            WHERE (guild_id = NEW.guild_id) AND (playlist_name = NEW.playlist_name) AND (track_index >= NEW.track_index);
        END;
        """ # AND rowid != NEW.rowid
        QUERY_AFTER_INSERT_TRIGGER = """
        CREATE TRIGGER IF NOT EXISTS Track_shift_indices_before_insert
        AFTER INSERT ON Track
        BEGIN
            UPDATE Track
            SET track_index = track_index + 1
            WHERE (guild_id = NEW.guild_id) AND (playlist_name = NEW.playlist_name) AND 
            (track_index >= NEW.track_index) AND (rowid != NEW.rowid);
        END;
        """
        QUERY_BEFORE_UPDATE_TRIGGER_FLIPFLOP_METHOD = """
        CREATE TRIGGER IF NOT EXISTS Track_shift_indices_before_update
        BEFORE UPDATE OF track_index ON Track
        BEGIN
            UPDATE Track
            SET track_index = -1 * (track_index + 1)
            WHERE (guild_id = NEW.guild_id) AND (playlist_name = NEW.playlist_name) 
            AND (track_index >= NEW.track_index) AND (track_index < OLD.track_index);
            UPDATE Track
            SET track_index = -1 * (track_index - 1)
            WHERE (guild_id = NEW.guild_id) AND (playlist_name = NEW.playlist_name) 
            AND (track_index > OLD.track_index) AND (track_index <= NEW.track_index);
        END;
        """ # AND (rowid != OLD.rowid)
        QUERY_AFTER_UPDATE_TRIGGER_FLIPFLOP_METHOD = """
        CREATE TRIGGER IF NOT EXISTS Track_shift_indices_after_update
        AFTER UPDATE OF track_index ON Track
        BEGIN
            UPDATE Track
            SET track_index = -1 * track_index
            WHERE (guild_id = NEW.guild_id) AND (playlist_name = NEW.playlist_name) AND (track_index < 0);
        END;
        """
        QUERY_AFTER_UPDATE_TRIGGER = """
        CREATE TRIGGER IF NOT EXISTS Track_shift_indices_after_update
        AFTER UPDATE OF track_index ON Track
        BEGIN
            UPDATE Track
            SET track_index = track_index + 1
            WHERE (guild_id = NEW.guild_id) AND (playlist_name = NEW.playlist_name) 
            AND (track_index >= NEW.track_index) AND (track_index < OLD.track_index) AND (rowid != OLD.rowid);
            UPDATE Track
            SET track_index = track_index - 1
            WHERE (guild_id = NEW.guild_id) AND (playlist_name = NEW.playlist_name) 
            AND (track_index > OLD.track_index) AND (track_index <= NEW.track_index) AND (rowid != OLD.rowid);
        END
        """
        QUERY_SHIFT_INDICES_RIGHT = """
        UPDATE Track
        SET track_index = track_index + 1
        WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name) 
        AND (track_index >= :new_index) AND (track_index < :old_index)
        """
        QUERY_SHIFT_INDICES_LEFT = """
        UPDATE Track
        SET track_index = track_index - 1
        WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name) 
        AND (track_index > :old_index) AND (track_index <= :new_index)
        """
        QUERY_AFTER_DELETE_TRIGGER = """
        CREATE TRIGGER IF NOT EXISTS Track_shift_indices_before_delete
        AFTER DELETE ON Track
        BEGIN
        UPDATE Track
        SET track_index = track_index - 1
        WHERE (guild_id = OLD.guild_id) AND (playlist_name = OLD.playlist_name) AND (track_index > OLD.track_index);
        END
        """
        QUERY_INSERT = """
        INSERT INTO Track (guild_id, playlist_name, title, duration, encoded, uri, track_index)
        VALUES (:guild_id, :playlist_name, :title, :duration, :encoded, :uri,
            (
                SELECT COALESCE(MAX(track_index), 0) + 1 
                FROM Track WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name)
            )
        )
        RETURNING track_index
        """
        QUERY_INSERT_AT = """
        INSERT INTO Track (guild_id, playlist_name, title, duration, encoded, uri, track_index)
        VALUES (:guild_id, :playlist_name, :title, :duration, :encoded, :uri, :track_index)
        """
        QUERY_APPEND_IF_UNIQUE = """
        INSERT INTO Track (guild_id, playlist_name, title, duration, encoded, uri, track_index)
        SELECT :guild_id, :playlist_name, :title, :duration, :encoded, :uri, (
                SELECT COALESCE(MAX(track_index), 0) + 1 
                FROM Track WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name)
            )
        WHERE NOT EXISTS (
            SELECT 1 FROM Track
            WHERE guild_id = :guild_id AND playlist_name = :playlist_name AND encoded = :encoded
        ) RETURNING *
        """
        QUERY_UPDATE = """
        UPDATE Track
        SET title=:title, duration=:duration, encoded=:encoded
        WHERE (guild_id=:guild_id) AND (playlist_name=:playlist_name) AND (track_index=:track_index)
        """
        QUERY_SHIFT_INDEXES = """
        UPDATE Track 
        SET track_index = 
        CASE 
            WHEN ( (:new_index > :track_index) AND (track_index >= :track_index) AND (track_index <= :new_index) ) 
            THEN (track_index + :count)
            WHEN ( (:new_index < :track_index) AND (track_index <= :track_index) AND (track_index >= :new_index) )
            THEN (track_index - :count) 
        END
        WHERE guild_id = :guild_id
        AND playlist_name = :playlist_name;
        """
        _QUERY_MOVE = """
        UPDATE Track SET track_index = track_index + :new_index - :track_index
        WHERE guild_id = :guild_id
        AND playlist_name = :playlist_name
        AND track_index >= :track_index
        AND track_index < :new_index + :count
        """
        QUERY_MOVE_SINGLE = """
        UPDATE Track
        SET track_index = :new_index
        WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name) AND (track_index = :track_index)
        """
        QUERY_MOVE = """
        UPDATE Track 
        SET track_index = track_index + (:new_index - :track_index)
        WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name) 
        AND (track_index >= :track_index) AND (track_index < :track_index + :count)
        """
        QUERY_SELECT_MULTIPLE = """
        SELECT * FROM Track
        WHERE (guild_id = ?) AND (playlist_name = ?)
        LIMIT ? OFFSET ?
        """
        QUERY_SELECT_WITH_ENCODED = """
        SELECT * FROM Track
        WHERE (guild_id = ?) AND (playlist_name = ?) AND (encoded = ?)
        """
        QUERY_CHECK_DUPLICATE = """
        SELECT EXISTS(
        SELECT 1 FROM Track 
        WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name) AND (encoded = :encoded)
        )
        """
        QUERY_SELECT_ALL = """
        SELECT * FROM Track
        WHERE (guild_id = ?) AND (playlist_name = ?)
        """
        QUERY_DELETE_BULK = """
        DELETE FROM Track
        WHERE ROWID in (
            SELECT ROWID FROM Track 
            WHERE guild_id = ? AND playlist_name = ? 
            LIMIT ? OFFSET ?
        ) RETURNING *
        """
        QUERY_DELETE = """
        DELETE FROM Track
        WHERE (guild_id = :guild_id) AND (playlist_name = :playlist_name) AND (track_index >= :track_index) AND (track_index < :track_index + :count)
        RETURNING *
        """

        @classmethod
        def fromWavelink(cls, guild_id: int, playlist_name: str, track: WavelinkTrack):
            return cls(guild_id=guild_id,
                       playlist_name=playlist_name,
                       title=track.title,
                       duration=track.duration,
                       encoded=track.encoded,
                       uri=track.uri)

    class MusicDisabled(errors.CustomCheck):
        MESSAGE = "The music feature is disabled"

    class PlaylistsDisabled(errors.CustomCheck):
        MESSAGE = "The playlist feature is not enabled"

    class PlaylistNotFound(errors.CustomCheck):
        MESSAGE = "There is no playlist with that name"

    class PlaylistAlreadyExists(errors.CustomCheck):
        MESSAGE = "There is already a playlist with that name"

    async def init(self, drop=False):
        if drop: await self.dropTables()
        await self.createTables()
        await self.createTriggers()

    async def dropTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute("DROP TABLE IF EXISTS Playlist")
            await db.execute("DROP TABLE IF EXISTS Track")
            await db.execute("DROP TABLE IF EXISTS MusicSettings")
            await db.commit()

    async def createTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(MusicDB.MusicSettings.QUERY_CREATE_TABLE)
            await db.execute(MusicDB.Playlist.QUERY_CREATE_TABLE)
            await db.execute(MusicDB.Track.QUERY_CREATE_TABLE)
            await db.commit()

    async def createTriggers(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(MusicDB.MusicSettings.TRIGGER_BEFORE_INSERT_GUILD)
            await db.execute(MusicDB.Playlist.TRIGGER_BEFORE_INSERT_SETTINGS)
            await db.execute(MusicDB.Track.QUERY_AFTER_INSERT_TRIGGER)

            # await db.execute(MusicDB.Track.QUERY_BEFORE_UPDATE_TRIGGER)
            await db.execute(MusicDB.Track.QUERY_AFTER_UPDATE_TRIGGER)
            await db.execute(MusicDB.Track.QUERY_AFTER_DELETE_TRIGGER)
            await db.commit()

    async def insertPlaylist(self, playlist: Playlist) -> bool:
        async with aiosqlite.connect(self.file_path) as db:
            cursor = await db.execute(MusicDB.Playlist.QUERY_INSERT, playlist.astuple())
            row_count = cursor.rowcount
            await db.commit()
        return row_count > 0

    async def updatePlaylist(self, guild_id: int, playlist_name: str, new_playlist: Playlist):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(MusicDB.Playlist.QUERY_UPDATE, {
                "guild_id": guild_id, "name": playlist_name,
                "new_name": new_playlist.name, "new_description": new_playlist.description
            })
            await db.commit()

    async def upsertPlaylist(self, playlist: Playlist):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(playlist.QUERY_UPSERT, playlist.asdict())
            await db.commit()

    async def insertTrack(self, track: Track):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(track.QUERY_INSERT, track.asdict())
            await db.commit()

    async def insertTracks(self, tracks: list[Track]):
        tracks = [track.asdict() for track in tracks]
        async with aiosqlite.connect(self.file_path) as db:
            await db.executemany(MusicDB.Track.QUERY_INSERT, tracks)
            await db.commit()

    async def appendTracksNoDuplicates(self, tracks: list[Track]) -> tuple[int, int]:
        """
        Uses a select statement to somehow make sure that a duplicate track isn't added
        May or may not work and may or may not break on the return
        TODO make sure this works
        """
        # tracks = [dict(track.asdict().items()[:-1]) for track in tracks]
        tracks = [track.asdict() for track in tracks]
        async with aiosqlite.connect(self.file_path) as db:
            # db.row_factory = aiosqlite.Cursor.row_factory
            unique_tracks = []
            for track in tracks:
                query_result = await db.execute_fetchall(MusicDB.Track.QUERY_CHECK_DUPLICATE, track)
                is_duplicate = list(query_result)[0][0]
                if not is_duplicate: unique_tracks.append(track)
            await db.executemany(MusicDB.Track.QUERY_INSERT, unique_tracks)
            await db.commit()
            # cursor: aiosqlite.Cursor = await db.executemany(MusicDB.Track.QUERY_APPEND_IF_UNIQUE, tracks)
            # unique_tracks: MusicDB.Track = await cursor.fetchall()
        return len(unique_tracks), sum([t["duration"] for t in unique_tracks])
        # """
        # INSERT INTO Track (guild_id, playlist_name, title, duration, encoded)
        # VALUES (:guild_id, :playlist_name, :title, :duration, :encoded)
        # """

    async def upsertMusicSettings(self, music_settings: MusicSettings):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(music_settings.QUERY_UPSERT, music_settings.asdict())
            await db.commit()

    async def fetchMusicSettings(self, guild_id: int) -> MusicSettings:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.MusicSettings.rowFactory
            settings = await db.execute_fetchall(MusicDB.MusicSettings.QUERY_SELECT, (guild_id,))
            settings = settings[0]
            # await db.commit()
        return settings

    async def fetchPlaylist(self, guild_id: int, playlist_name: str) -> Playlist:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Playlist.rowFactory
            playlist: list[MusicDB.Playlist] = await db.execute_fetchall(MusicDB.Playlist.QUERY_SELECT, (guild_id, playlist_name))
            if playlist: playlist: MusicDB.Playlist = playlist[0]
            await db.commit()
        return playlist

    async def fetchPlaylists(self, guild_id: int, playlist_name: str, limit: int=1, offset: int=0) -> list[Playlist]:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Playlist.rowFactory
            playlists: list[MusicDB.Playlist] = await db.execute_fetchall(MusicDB.Playlist.QUERY_SELECT_MULTIPLE,
                                                                          (guild_id, playlist_name, offset, limit))
        return playlists

    async def fetchSimilarPlaylists(self, guild_id: int, playlist_name: str, limit: int = 1, offset: int = 0) -> list[Playlist]:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Playlist.rowFactory
            playlists: list[MusicDB.Playlist] = await db.execute_fetchall(MusicDB.Playlist.QUERY_SELECT_MULTIPLE,
                                                                          (guild_id, f"%{playlist_name}%", offset, limit))
        return playlists

    async def fetchSimilarPlaylistNames(self, guild_id: int, playlist_name: str, limit: int = 1, offset: int = 0
                                        ) -> list[str]:
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(MusicDB.Playlist.QUERY_SELECT_LIKE_NAMES,
                                                         (guild_id, f"%{playlist_name}%", limit, offset))
            names = [n[0] for n in names]
        return names

    async def fetchTracks(self, guild_id: int, playlist_name: str, limit: int=1, offset: int=0) -> list[Track]:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Track.rowFactory
            if limit:
                query = MusicDB.Track.QUERY_SELECT_MULTIPLE
                bindings = (guild_id, playlist_name, limit, offset)
            else:
                query = MusicDB.Track.QUERY_SELECT_ALL
                bindings = (guild_id, playlist_name)
            tracks: list[MusicDB.Track] = await db.execute_fetchall(query, bindings)
        return tracks

    async def deletePlaylist(self, guild_id: int, playlist_name: str):
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Playlist.rowFactory
            playlist: list[MusicDB.Playlist] = await db.execute_fetchall(MusicDB.Playlist.QUERY_DELETE,
                                                                         (guild_id, playlist_name))
            playlist: MusicDB.Playlist = playlist[0]
            await db.commit()
        return playlist

    async def deleteTrack(self, guild_id: int, playlist_name: str, track_index: int, track_count: int) -> Track:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Track.rowFactory
            params = {"guild_id": guild_id,
                      "playlist_name": playlist_name,
                      "track_index": track_index,
                      "count": 1}
            result: list[MusicDB.Track] = await db.execute_fetchall(MusicDB.Track.QUERY_DELETE, params)
            track = result[0]
            await db.commit()
        return track
            # need to fix the indices of the tracks that are left either do it in the delete query or afterward

    async def deleteTracks(self, guild_id: int, playlist_name: str, track_positions: list[int]) -> list[Track]:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Track.rowFactory
            tracks = []
            for idx in track_positions:
                params = {"guild_id": guild_id,
                          "playlist_name": playlist_name,
                          "track_index": idx,
                          "count": 1}
                result = await db.execute_fetchall(MusicDB.Track.QUERY_DELETE, params)
                tracks.append(result)
            await db.commit()
        return tracks

    async def moveTrack(self, guild_id: int, playlist_name: str, track_index: int,
                                            new_index: int, track_count: int): # single_query_method
        async with aiosqlite.connect(self.file_path) as db:
            params = {"guild_id": guild_id,
                      "playlist_name": playlist_name,
                      "track_index": track_index,
                      "new_index": new_index}
            await db.execute(MusicDB.Track.QUERY_MOVE_SINGLE, params)
            await db.commit()

    async def moveTrackDeleteInsert(self, guild_id: int, playlist_name: str, track_index: int,
                        new_index: int, track_count: int): # DeleteInsertMethod
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = MusicDB.Track.rowFactory
            delete_params = {"guild_id": guild_id,
                             "playlist_name": playlist_name,
                             "track_index": track_index,
                             "count": 1}
            result: list[MusicDB.Track] = await db.execute_fetchall(MusicDB.Track.QUERY_DELETE, delete_params)
            track: MusicDB.Track = result[0]
            shift_params = {"guild_id": guild_id,
                            "playlist_name": playlist_name,
                            "old_index": track_index,
                            "new_index": new_index}
            track.track_index = new_index

            # if new_index < track_index:
            #     await db.execute(MusicDB.Track.QUERY_SHIFT_INDICES_RIGHT, shift_params)
            # elif new_index > track_index:
            #     await db.execute(MusicDB.Track.QUERY_SHIFT_INDICES_LEFT, shift_params)
            params = track.asdict()
            await db.execute(MusicDB.Track.QUERY_INSERT_AT, params)
            await db.commit()


class Music(GroupCog,
            group_name="m",
            description="commands relating to music playback"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        self.database = MusicDB(bot.config.db_path)

    # music_group = app_commands.Group(name="m", description="commands relating to music playback")
    music_group = app_commands
    # music_group = Group(name="m", description="commands relating to the music player")





    # await db.execute("""
    #             CREATE TABLE IF NOT EXISTS Tracks(
    #             playlist_id INTEGER FOREIGN KEY REFERENCE Playlists.id
    #             id INTEGER AUTO INCREMENT
    #             title TEXT DEFAULT 'Untitled'
    #             duration INTEGER DEFAULT 0
    #             encoded TEXT NOT NULL)
    #             """)

    """
    Insert a new server, do this as soon as possible so that 
    fetch a server whenever it is needed using a discord 
    """

    async def cog_load(self) -> None:
        await self.database.init(drop=self.bot.config.drop_tables)
        # await self.migrateMusicData()

    @commands.is_owner()
    @commands.command(name="migrate_music")
    async def migrateCommand(self, ctx):
        await self.migrateMusicData()
        await ctx.send("migrated music probably")

    async def migrateMusicData(self):
        async def convertTracks(_guild_id: int, _playlist_name: str, _tracks: list[OldTrack]) -> list[MusicDB.Track]:
            new_tracks: list[MusicDB.Track] = []
            for track in _tracks:
                try:
                    wavelink_track = await buildTrack(track.encoded)
                    _track = MusicDB.Track.fromWavelink(guild_id=_guild_id, playlist_name=_playlist_name,
                                                        track=wavelink_track)
                    new_tracks.append(_track)
                except InvalidLavalinkResponse as e:
                    print(e)
                    print(_playlist_name, track.title)

            return new_tracks

        for server_id, server in self.bot.data.servers.items():
            server_id = int(server_id)
            try: guild = await self.bot.fetch_guild(server_id)
            except discord.NotFound: continue
            music_settings = MusicDB.MusicSettings(guild_id=guild.id, music_enabled=True, playlists_enabled=True)
            await self.database.upsertMusicSettings(music_settings)

            await self.database.upsertGuild(self.database.Guild.fromDiscord(guild))
            for playlist_name, playlist in server.playlists.items():
                new_playlist = MusicDB.Playlist(server_id, playlist_name, playlist.description)
                tracks = await convertTracks(server_id, playlist_name, playlist.tracks)
                await self.database.upsertPlaylist(new_playlist)
                await self.database.insertTracks(tracks)

    async def cog_unload(self) -> None:
        pass
        # await self.migrateMusicData()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        message = f"Node: <{node.id}> is ready"
        print(message)
        await self.bot.logToChannel(message)

    # guild.voice_client = player
    # same fucking thing, don't forget it

    # Auto Queue Doesn't work for me
    # Make queue automatically cycle
    @music_group.command(name="join",
                         description="joins the voice channel")
    async def m_join(self, interaction: Interaction, voice_channel: VoiceChannel = None):
        await respond(interaction, ephemeral=True)
        voice_client: Player = await attemptToJoin(interaction, voice_channel, ephemeral=True)


    @music_group.command(name="leave",
                         description="leaves the voice channel")
    async def m_leave(self, interaction: Interaction):
        await respond(interaction, ephemeral=True)
        voice_client: Player = interaction.guild.voice_client
        if not voice_client: raise errors.NotInVC

        await respond(interaction, "Leaving...", delete_after=0.5, ephemeral=True)
        await voice_client.disconnect()

    @requireVoiceclient(begin_session=True)
    @music_group.command(name="play",
                         description="plays the given song or adds it to the queue")
    async def m_play(self, interaction: Interaction, search: str = None):
        voice_client: Player = interaction.guild.voice_client
        # await respond(interaction)
        if not search:
            if voice_client.is_paused():
                await voice_client.resume()
                await respond(interaction, "Resumed music playback", delete_after=3)
                # await respond(interaction, ("Resumed music playback")
            else:
                await attemptHaltResume(interaction, send_response=True)
        else:
            tracks, _ = await searchAndQueue(voice_client, search)
            track_count = len(tracks)
            duration = sum([track.duration for track in tracks])
            info_text = addedToQueueMessage(track_count, duration)
            await respondWithTracks(self.bot, interaction, tracks, info_text=info_text)
            await attemptHaltResume(interaction)



    @requireVoiceclient(ephemeral=True)
    @music_group.command(name="skip",
                         description="skips the current track")
    async def m_skip(self, interaction: Interaction, count: int = 1):
        voice_client: Player = interaction.guild.voice_client

        # if not voice_client: raise errors.NotInVC
        skipped_count = await voice_client.cycleQueue(count)
        comparison_count = abs(count) if count > 0 else abs(count) + 1

        if skipped_count < comparison_count:
            await voice_client.stop(halt=True)
        else:
            if voice_client.halted:
                await voice_client.stop()
            else:
                # if voice_client.queue.history.count:
                await voice_client.beginPlayback()
                # else:
                #     await voice_client.cyclePlayNext()

        await respond(interaction, f"Skipped {'back ' if count < 0 else ''}{skipped_count} tracks")

    @requireVoiceclient(defer_response=False)
    @music_group.command(name="nowplaying",
                         description="shows the current song")
    async def m_nowplaying(self, interaction: Interaction, minimal: bool=None, move_status: bool=True):
        voice_client: Player = interaction.guild.voice_client
        # await respond(interaction, ephemeral=True)



        if voice_client.now_playing_message:
            msg_channel_id = voice_client.now_playing_message.channel_id

            # kill the fucker
            await voice_client.now_playing_message.halt()
            voice_client.now_playing_message = None

            async def disableRespond(): await respond(interaction, "`Disabled status message`", ephemeral=True, delete_after=3)

            if move_status:
                if interaction.channel.id != msg_channel_id:
                    await respond(interaction, f"`Moved status message to {interaction.channel.name}`", ephemeral=True, delete_after=3)
                elif minimal is not None:
                    await respond(interaction, f"`{'Enabled' if minimal else 'Disabled'} minimal mode`", ephemeral=True, delete_after=3)
                else:
                    await disableRespond()
                    return
            else:
                await disableRespond()
                return
        else:
            await respond(interaction, "`Enabled status message`", ephemeral=True, delete_after=3)

        message: Message = await interaction.channel.send(createNowPlayingWithDescriptor(voice_client, True, True))

        message_info = MessageInfo(id=message.id,
                                   channel_id=message.channel.id)
        if minimal:
            sep = False
            view=MISSING
        else:
            sep = True
            view = PlayerController(bot=self.bot,
                                    message_info=message_info,
                                    timeout=None)

        message_elems = MessageElements(content=message.content,
                                        view=view)

        def callback(guild_id: int, channel_id: int, message_elems: MessageElements) -> str:
            guild = self.bot.get_guild(guild_id)
            message = createNowPlayingWithDescriptor(voice_client=guild.voice_client,
                                                     formatting=False,
                                                     position=True)
            message_elems.content = message
            return message_elems

        # voice_client.now_playing_message = PersistentMessage(
        #     self.bot,
        #     guild_id=interaction.guild_id,
        #     message_info=message_info,
        #     message_elems=message_elems,
        #     seperator=sep,
        #     refresh_callback=callback,
        #     persist_interval=5)

        np_message = PersistentMessage(
            self.bot,
            guild_id=interaction.guild_id,
            message_info=message_info,
            message_elems=message_elems,
            seperator=sep,
            refresh_callback=callback,
            persist_interval=5)
        voice_client.now_playing_message = np_message

        np_message.begin()


    @requireVoiceclient()
    @music_group.command(name="queue",
                         description="shows the previous and upcoming tracks")
    async def m_queue(self, interaction: Interaction, clientside: bool=False):
        voice_client: Player = interaction.guild.voice_client

        # assert isinstance(interaction.response, InteractionResponse)
        og_response = await respond(interaction)
        # og_response = await interaction.original_response()
        message_info = MessageInfo(og_response.id,
                                   og_response.channel.id)

        # def pageGen(_voice_client: Player, page_index: int) -> str:
        #     if _voice_client:
        #         return createQueuePage(_voice_client.queue, page_index)
        #     else:
        #         return None
        #
        # def edgeIndices(_voice_client: Player) -> EdgeIndices:
        #     if _voice_client:
        #         return getEdgeIndices(_voice_client.queue)
        #     else:
        #         return None

        def pageGen(interaction: Interaction, page_index: int) -> str:
            voice_client: Player
            if voice_client := interaction.guild.voice_client:
                return createQueuePage(voice_client, page_index)
            else:
                return None

        def edgeIndices(interaction: Interaction) -> EdgeIndices:
            voice_client: Player
            if voice_client := interaction.guild.voice_client:
                return getQueueEdgeIndices(voice_client.queue)
            else:
                return None

        # partialPageGen = partial(pageGen, _voice_client=voice_client)
        # partialEdgeIndices = partial(edgeIndices, _voice_client=voice_client)
        #
        #
        # page_callbacks = PageGenCallbacks(genPage=partialPageGen,
        #                                   getEdgeIndices=partialEdgeIndices)

        page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)

        view = PageScroller(bot=self.bot,
                            message_info=message_info,
                            page_callbacks=page_callbacks,
                            timeout=300)
        home_text = pageGen(interaction=interaction, page_index=0)

        await respond(interaction, content=home_text, view=view)

    @requireVoiceclient()
    @music_group.command(name="loop",
                         description="changes the loop mode, Off->All->Single")
    async def m_loop(self, interaction: Interaction, mode: Player.LoopType = None):
        voice_client: Player = interaction.guild.voice_client
        # TODO Loop needs to work properly

        voice_client.changeLoopMode(mode)
        await respond(interaction, f"Loop Mode:`{mode}`", delete_after=3)

    @requireVoiceclient()
    @music_group.command(name="stop",
                         description="Halts the playback of the current track, resuming restarts")
    async def m_stop(self, interaction: Interaction):
        await respond(interaction)
        # TODO Stop implements stopping via calling the halt function
        voice_client: Player = interaction.guild.voice_client
        await voice_client.stop(halt=True)
        await respond(interaction, "Stopped the Player", delete_after=3)

    @requireVoiceclient()
    @music_group.command(name="seek",
                         description="Seeks to the specified position in the track in seconds")
    async def m_seek(self, interaction: Interaction, position: float):
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        pos_milliseconds = position * 1000
        await voice_client.seek(pos_milliseconds)
        np, _ = voice_client.currentlyPlaying()
        duration_text = secondsToTime(np.length//1000)
        if pos_milliseconds > np.length:
            new_pos = duration_text
        else:
            new_pos = secondsToTime(position)

        await respond(interaction, f"**Jumped to `{new_pos} / {duration_text}`**", delete_after=3)

# TODO make pop act similarly to the playlist pop with a message scroller response
    @requireVoiceclient()
    @music_group.command(name="pop",
                         description="Removes a track from the queue")
    async def m_pop(self, interaction: Interaction, position: int, source: Literal["history", "queue"]=None):
        await respond(interaction)
        # TODO Extend support for alternate queues, ie next up queue and soundboard queue
        voice_client: Player = interaction.guild.voice_client
        index = position - 1

        queue_source = "unknown queue"

        if position <= 0:
            queue_source = "history"
            track = voice_client.queue.history[index]
            del voice_client.queue.history[index]
        else:
            queue_source = "queue"
            track = voice_client.queue[index]
            del voice_client.queue[index]

        track_text = createNowPlayingMessage(track, position=None, formatting=False, show_arrow=False, descriptor_text='')
        reply = f"Removed `{track_text}` from `{queue_source}`"
        await respond(interaction, reply, delete_after=3)

    @requireVoiceclient()
    @music_group.command(name="pause",
                         description="Pauses the music player")
    async def m_pause(self, interaction: Interaction):
        # Pause calls the pause function from the player, functions as a toggle
        # This never needs to do anything fancy ever
        voice_client: Player = interaction.guild.voice_client
        if voice_client.is_paused():
            await voice_client.resume()
            message = "Resumed the player"
        else:
            await voice_client.pause()
            message = "Paused the player"

        await respond(interaction, message, delete_after=3)

    @requireVoiceclient()
    @music_group.command(name="resume",
                         description="Resumes the music player")
    async def m_resume(self, interaction: Interaction):
        # Resume which just calls resume on the player, effectively pause toggle alias
        voice_client: Player = interaction.guild.voice_client
        if voice_client.is_paused():
            await voice_client.resume()
            await respond(interaction, "Resumed playback", delete_after=3)
        else:
            await attemptHaltResume(voice_client, send_response=True)

    @requireVoiceclient()
    @music_group.command(name="replay",
                         description="Restarts the current song")
    async def m_replay(self, interaction: Interaction):
        # Contextually handles replaying based off of the current track progress
        # Tweak the replay vs restart cutoff based off feedback
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        np, pos = voice_client.currentlyPlaying()

        cutoff_pos = 15  # seconds
        if pos//1000 < cutoff_pos:
            await voice_client.cycleQueue(-1)
            await voice_client.beginPlayback()
            message = "Replaying the previous track"
        else:
            await voice_client.seek(0)
            message = "Restarted the current track"
        await respond(interaction, message, delete_after=3)



    @requireVoiceclient()
    @music_group.command(name="clear",
                         description="Clears the selected queue")
    async def m_clear(self, interaction: Interaction, choice: Literal["queue", "history"]):
        # TODO Support multiple queue types, up next queue and soundboard queue for example
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        if choice == "queue":
            voice_client.queue.clear()
        elif choice == "history":
            voice_client.queue.history.clear()

        await respond(interaction, f"Cleared {choice}", delete_after=3)



    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackEventPayload):
        player: Player = payload.player

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: TrackEventPayload):
        voice_client: Player = payload.player
        reason = payload.reason

        if voice_client.halted:
            return

        if reason == "REPLACED":
            # triggers on a skip when not halted
            # await voice_client.beginPlayback()
            return
        elif reason == "FINISHED":
            # triggers on actually finishing

            # Using early returns to create a priority order
            # if halted do jack shit
            # then handle interruptions

            if voice_client.interrupted:
                await voice_client.resumeInteruptedTrack()
                return

            await voice_client.cyclePlayNext()
        elif reason == "STOPPED:":
            # triggers on a typical skip where the track is stopped
            # via Player.stop()
            pass

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        music_settings = await self.database.fetchMusicSettings(interaction.guild_id)
        if not music_settings.music_enabled:
            raise MusicDB.MusicSettings
        old_server_data.value = self.bot.getServerData(interaction.guild_id)
        if interaction.guild.voice_client and not isinstance(interaction.guild.voice_client, Player):
            raise errors.WrongVoiceClient("`Incorrect command for Player, Try /<command> instead`")

        old_server_data.value.last_music_command_channel = interaction.channel
        # await self.bot.database.upsertGuild(interaction.guild)
        return True

    @Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        voice_client: Player = member.guild.voice_client
        server_data = self.bot.getServerData(member.guild.id)
        bc = before.channel
        ac = after.channel

        joined_channel = (not bc) and ac  # there is no before channel but there is an after channel
        left_channel = bc and (not ac)  # there is no after channel but there was a before channel
        moved_channel = (bc and ac) and (bc != ac)  # there is a before and after but they are different channels

        if member == self.bot.user:  # the member is the bot
            if joined_channel:
                message = f"I joined `{ac.name}`"
            elif left_channel:
                message = f"I left `{bc.name}`"
                if len(bc.members) == 0: message += f" because it was empty"
            elif moved_channel:
                message = f"I moved from `{bc.name}` to `{ac.name}`"
            else:
                return  # other voice state changed

            last_channel = server_data.last_music_command_channel
            if last_channel: await last_channel.send(message, delete_after=8)
        else:
            # member is not the bot
            if voice_client:
                # only do if there is an active voice client
                if bc == voice_client.channel and (left_channel or moved_channel):
                    # someone has left the player channel
                    if len(bc.members) - 1 == 0:
                        await voice_client.disconnect()
                    else:
                        # someone left but there are still enough people
                        pass
                else:
                    # could include other cases besides just leaving the player channel
                    pass
            else: # unrelated to the voice client
                pass


class PlaylistTransformer(Transformer):
    async def autocomplete(self,
                           interaction: Interaction, value: str, /
                           ) -> list[Choice[str]]:
        bot: Kagami = interaction.client
        db = MusicDB(bot.config.db_path)
        names = await db.fetchSimilarPlaylistNames(guild_id=interaction.guild_id,
                                                   playlist_name=value,
                                                   limit=25)
        # names = list(map(lambda n: n[0], names))
        # Equivalent map statement
        # names = [n[0] for n in names]
        choices = [Choice(name=name, value=name) for name in names]
        return choices

    async def transform(self, interaction: Interaction, value: str, /) -> MusicDB.Playlist:
        bot: Kagami = interaction.client
        db = MusicDB(bot.config.db_path)
        playlist = await db.fetchPlaylist(guild_id=interaction.guild_id,
                                          playlist_name=value)
        # if playlist is None: raise MusicDB.PlaylistNotFound
        return playlist


# TODO Confirmation dialogues sent ephemerally for deletions and edits and such, anything important like that
class PlaylistCog(GroupCog,
                  group_name="p",
                  description="commands relating to music playlists"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        self.database = MusicDB(bot.config.db_path)
        # self.playlist_transform = Transform[Playlist, PlaylistTransformer(bot=bot)]

    create = Group(name="create", description="creating playlists")
    add = Group(name="add", description="adding tracks to playlists")
    # remove = Group(name="remove", description="removing tracks or playlists")
    view = Group(name="view", description="view playlists and tracks")
    edit = Group(name="edit", description="edit playlist info and tracks")
    tracks = Group(name="tracks", description="handles playlist tracks")

    Playlist_Transformer = Transform[MusicDB.Playlist, PlaylistTransformer]

    @create.command(name="new",
                    description="create a new empty playlist")
    # @app_commands.rename(playlist_tuple="playlist")
    async def p_create_new(self, interaction: Interaction,
                           playlist: Playlist_Transformer,
                           description: str=""):
        await respond(interaction, ephemeral=True)
        if playlist: raise MusicDB.PlaylistAlreadyExists
        else:
            playlist = MusicDB.Playlist(guild_id=interaction.guild_id,
                                        name=interaction.namespace.playlist,
                                        description=description)
        await self.database.insertPlaylist(playlist)

        # if not (await self.database.insertPlaylist(playlist)): raise errors.PlaylistAlreadyExists
        await respond(interaction, f"Created playlist `{playlist.name}`", ephemeral=True, delete_after=3)

    @requireVoiceclient()
    @create.command(name="queue",
                    description="creates a new playlist using the current queue as a base")
    async def p_create_queue(self, interaction: Interaction,
                             playlist: Playlist_Transformer,
                             description: str=""):
        await respond(interaction, ephemeral=True)
        if playlist: raise MusicDB.PlaylistAlreadyExists
        else:
            playlist = MusicDB.Playlist(guild_id=interaction.guild_id,
                                        name=interaction.namespace.playlist,
                                        description=description)

        voice_client: Player = interaction.guild.voice_client
        # voice_client = player_instance.value
        wavelink_tracks = voice_client.allTracks()
        tracks = [MusicDB.Track.fromWavelink(guild_id=playlist.guild_id, playlist_name=playlist.name, track=track)
                  for track in wavelink_tracks]
        await self.database.insertPlaylist(playlist)
        await self.database.insertTracks(tracks)
        info_text = f"Created playlist `{playlist.name}` with `{len(tracks)} tracks`"
        await respond(interaction, info_text)
        # await respond(interaction, f"```swift"
        #                            f"{info_text}\n"
        #                            f"```")
        # await respondWithTracks(bot=self.bot, interaction=interaction, tracks=tracks, info_text=info_text)


    @app_commands.command(name="delete",
                          description="deletes a playlist")
    async def p_delete(self, interaction: Interaction,
                       playlist: Playlist_Transformer):
        await respond(interaction, ephemeral=True)
        if not playlist: raise MusicDB.PlaylistNotFound
        # voice_client = interaction.guild.voice_client
        await self.database.deletePlaylist(guild_id=interaction.guild_id,
                                           playlist_name=playlist.name)
        await respond(interaction, f"**Deleted Playlist `{playlist.name}`**", delete_after=3)

    @requireVoiceclient(begin_session=True)
    @app_commands.command(name="play",
                          description="play a playlist")
    async def p_play(self, interaction: Interaction,
                     playlist: Playlist_Transformer,
                     interrupt: bool=False):
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client

        if not playlist: raise MusicDB.PlaylistNotFound

        tracks = await self.database.fetchTracks(guild_id=interaction.guild_id,
                                                 playlist_name=playlist.name,
                                                 limit=None)
        track_count = len(tracks)
        duration = sum([track.duration for track in tracks])
        for track in tracks:
            wavelink_track = await buildTrack(track.encoded)
            await voice_client.waitAddToQueue(wavelink_track)

        await respond(interaction, f"Added {track_count} tracks "
                                   f"with a duration of {secondsToTime(duration//1000)} "
                                   f"from playlist `{playlist.name}`", delete_after=5)
        # info_text = addedToQueueMessage(track_count, duration)
        # await respondWithTracks(self.bot, interaction, tracks)
        await attemptHaltResume(interaction)

    # TODO Alias play command without the m before it in global space for ease of use

    @requireVoiceclient()
    @add.command(name="queue",
                 description="adds the queue to a playlist")
    async def p_add_queue(self, interaction: Interaction,
                          playlist: Playlist_Transformer,
                          allow_duplicates: bool=False):
        await respond(interaction)
        if not playlist: raise MusicDB.PlaylistNotFound
        voice_client: Player = interaction.guild.voice_client
        wavelink_tracks = voice_client.allTracks()
        tracks = [MusicDB.Track.fromWavelink(interaction.guild_id, playlist.name, track) for track in wavelink_tracks]

        if allow_duplicates:
            await self.database.insertTracks(tracks)
            track_count = len(tracks)
            duration = sum([t.duration for t in tracks])
        else:
            track_count, duration = await self.database.appendTracksNoDuplicates(tracks)

        await respond(interaction, f"Added `{track_count}` tracks with a duration of `{secondsToTime(duration//1000)}`"
                                   f"to the playlist: {playlist.name}", delete_after=3)


        # TODO create a list of the tracks added for both add_queue and add_track

        # Potentially fetch individual tracks with fetch_one() and use waitAddQueue

        # tracks, duration = playlist.updateFromTracks(tracks, allow_duplicates)
        # info_text = f"Added {len(tracks)} with duration: {secondsToTime(duration // 1000)} " \
        #             f"to the playlist: {interaction.namespace.playlist}"
        #
        #
        # await respondWithTracks(bot=self.bot, interaction=interaction, tracks=tracks, info_text=info_text)

    @add.command(name="tracks",
                 description="adds tracks to a playlists")
    async def p_add_track(self, interaction: Interaction,
                          playlist: Playlist_Transformer,
                          search: str, allow_duplicates: bool=False):
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        wavelink_tracks, _ = await searchForTracks(search)
        tracks = [MusicDB.Track.fromWavelink(interaction.guild_id, playlist.name, track) for track in wavelink_tracks]
        if allow_duplicates:
            await self.database.insertTracks(tracks)
            track_count = 1
            duration = sum([track.duration for track in tracks])
        else:
            track_count, duration = await self.database.appendTracksNoDuplicates(tracks)

        info_text = f"Added {len(wavelink_tracks)} with duration: {secondsToTime(duration//1000)} " \
                    f"to the playlist: {playlist.name}"
        await respond(interaction, info_text, delete_after=3)
        # await respondWithTracks(bot=self.bot, interaction=interaction, tracks=wavelink_tracks, info_text=info_text)

    @view.command(name="all",
                  description="view all playlists")
    async def p_view_all(self, interaction: Interaction):

        await respond(interaction, "This command is currently non functional", delete_after=3)
        # TODO reimplement this command using sql

        """
        og_response = await respond(interaction)
        
        def pageGen(interaction: Interaction, page_index: int) -> str:
            server_data = self.bot.getServerData(interaction.guild_id)


            first_item_index = page_index*10
            playlists = dict(list(server_data.playlists.items())[first_item_index:first_item_index+10])

            data = {
                playlist_name: {
                    "tracks": len(playlist.tracks),
                    "duration": secondsToTime(playlist.duration//1000)
                }
                for playlist_name, playlist in playlists.items()
            }
            # return createSinglePage()
            playlist_count = len(playlists)

            info_text = f"{interaction.guild.name} has {playlist_count} playlists"
            info_text_elem = InfoTextElem(
                text=info_text,
                loc=ITL.TOP,
                separators=InfoSeparators(bottom="────────────────────────────────────────")
            )
            left, right = edgeIndices(interaction)

            page = createSinglePage(
                data=data,
                infotext=info_text_elem,
                first_item_index=page_index*10 + 1,
                page_position=PageIndices(left, page_index, right),
                custom_reprs={
                    "encoded": CustomRepr(ignored=True)
                },
                behavior=PageBehavior(max_key_length=40)
            )
            return page

        def edgeIndices(interaction: Interaction) -> EdgeIndices:
            playlist_count = len(old_server_data.value.playlists)
            page_count = ceil(playlist_count/10)
            return EdgeIndices(left=0, right=page_count-1)


        page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)
        view = PageScroller(bot=self.bot,
                            message_info=MessageInfo(id=og_response.id,
                                                     channel_id=og_response.channel.id),
                            page_callbacks=page_callbacks,
                            timeout=300)
        home_text = pageGen(interaction=interaction, page_index=0)
        await respond(interaction, content=home_text, view=view)
        """

    @view.command(name="tracks",
                  description="view all tracks in a playlist")
    async def p_view_tracks(self, interaction: Interaction,
                            playlist: Playlist_Transformer):
        await respond(interaction, "This command is currently non functional", delete_after=3) # TODO reimplement this command using sql
        #
        """
        og_response = await respond(interaction)
        playlist_name = interaction.namespace.playlist

        def pageGen(interaction: Interaction, page_index: int) -> str:
            server_data = self.bot.getServerData(interaction.guild_id)
            playlist = server_data.playlists.get(playlist_name)
            first_item_index = page_index*10
            tracks = playlist.tracks[first_item_index: first_item_index+10]
            data = {track.title: {"duration": secondsToTime(track.duration // 1000)}
                    for track in tracks}

            track_coount = len(playlist.tracks)
            duration = playlist.duration
            info_text = f"{playlist_name} has {track_coount} tracks and a runtime of {secondsToTime(duration // 1000)}\n" \
                        f"{playlist.description or '-no description'}"
            info_text_elem = InfoTextElem(
                text=info_text,
                loc=ITL.TOP,
                separators=InfoSeparators(bottom="────────────────────────────────────────")
            )

            left, right = edgeIndices(interaction)

            page = createSinglePage(
                data=data,
                infotext=info_text_elem,
                first_item_index=page_index * 10 + 1,
                page_position=PageIndices(left, page_index, right),
                behavior=PageBehavior(max_key_length=50)
            )
            return page

        def edgeIndices(interaction: Interaction) -> EdgeIndices:
            server_data = self.bot.getServerData(interaction.guild_id)
            playlist = server_data.playlists.get(playlist_name)
            track_count = len(playlist.tracks)
            page_count = ceil(track_count / 10)
            return EdgeIndices(left=0, right=page_count - 1)

        page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)
        view = PageScroller(bot=self.bot,
                            message_info=MessageInfo(id=og_response.id,
                                                     channel_id=og_response.channel.id),
                            page_callbacks=page_callbacks,
                            timeout=300)
        home_text = pageGen(interaction=interaction, page_index=0)
        await respond(interaction, content=home_text, view=view)
        # await respondWithTracks(self.bot, interaction, playlist.tracks, info_text=info_text, timeout=120)
        """

    @edit.command(name="details",
                  description="edits playlist details eg. title & description")
    @app_commands.rename(new_playlist="name")
    async def p_edit_details(self, interaction: Interaction,
                             playlist: Playlist_Transformer, new_playlist: Playlist_Transformer=None, description: str=None):
        # await respond(interaction, ephemeral=True)
        await respond(interaction, delete_after=3)
        if not playlist: raise MusicDB.PlaylistNotFound
        if new_playlist: raise MusicDB.PlaylistAlreadyExists
        if not description: description = playlist.description
        name = interaction.namespace.name or playlist.name
        description = description or playlist.description
        new_playlist = self.database.Playlist(guild_id=interaction.guild_id,
                                              name=name,
                                              description=description)

        await self.database.updatePlaylist(guild_id=interaction.guild_id, playlist_name=playlist.name, new_playlist=new_playlist)
        await respond(interaction, "Successfully edited the playlist", delete_after=3)

    @tracks.command(name="move", description="move tracks within a playlist")
    async def p_tracks_move(self, interaction: Interaction, playlist: Playlist_Transformer,
                            track_pos: Range[int, 1, None], new_pos: Range[int, 1, None], count: Range[int, 1, None]=1):
        if not playlist: raise errors.PlaylistNotFound

        await respond(interaction)
        guild_id = interaction.guild_id
        playlist_name = interaction.namespace.playlist
        await self.database.moveTrack(guild_id=guild_id, playlist_name=playlist_name,
                                      track_index=track_pos, new_index=new_pos, track_count=count)
        await respond(interaction, f"`Moved {count} tracks`", delete_after=5)

    @tracks.command(name="delete", description="delete tracks within a playlist")
    async def p_tracks_delete(self, interaction: Interaction, playlist: Playlist_Transformer,
                              track_pos: Range[int, 1, None], count: Range[int, 1, None]=1):
        await respond(interaction, "Comming with music rewrite", delete_after=5)
        guild_id = interaction.guild_id
        playlist_name = interaction.namespace.playlist

        tracks: list[MusicDB.Track] = await self.database.deleteTrack(guild_id, playlist_name, track_pos, count)
        await respond(interaction, f"`Removed {len(tracks)} tracks from {playlist_name}`", delete_after=5)


    def setContextVars(self, interaction: Interaction):
        old_server_data.value = self.bot.getServerData(interaction.guild_id)
        player_instance.value = interaction.guild.voice_client
        pass

    async def interaction_check(self, interaction: Interaction):
        music_settings = await self.database.fetchMusicSettings(interaction.guild_id)
        if not music_settings.playlists_enabled:
            raise MusicDB.PlaylistsDisabled

        self.setContextVars(interaction)
        old_server_data.value.last_music_command_channel = interaction.channel
        # await self.bot.database.upsertGuild(interaction.guild)
        return True
    # async def autocomplete_check


# class SimpleEditModal(Modal):
#     def __init__(self, title: str, fields: dict[str, str], optional: list[str]=None):
#         super().__init__(title=title)
#         if not optional: optional = []
#
#         self.fields = fields
#         for field_name, default_value in fields.items():
#             field = TextInput(label=field_name, default=default_value, required=(field_name not in optional))
#             self.add_item(field)
#             if len(self.children) == 5:
#                 break
#
#
#     async def on_submit(self, interaction: Interaction) -> None:
#         item: TextInput
#         self.fields.update({item.label: item.value for item in self.children})
#         await respond(interaction)


async def setup(bot):
    music_cog = Music(bot)
    playlist_cog = PlaylistCog(bot)
    await bot.add_cog(music_cog)
    await bot.add_cog(playlist_cog)
