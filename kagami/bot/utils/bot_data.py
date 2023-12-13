import os
from dataclasses import dataclass, field
from typing import TypeVar, Type, Union, Self
import wavelink
from discord import TextChannel
from dotenv import load_dotenv, find_dotenv
from wavelink.ext import spotify

from bot.utils.music_helpers import OldPlaylist
from bot.utils.wavelink_utils import WavelinkTrack, buildTrack
from bot.utils.context_vars import CVar

# TODO deprecate this shit once nothing else uses it
class Server:
    def __init__(self, guild_id: [int, str], player=None, json_data=None):
        self.id = str(guild_id)
        self.playlists: dict[str, OldPlaylist] = {}     # name : Playlist
        self.has_player: bool = False
        self.views = {}
        self.soundboard: dict[str, str] = {}
        self.tags = {}
        self.sentinels = {}
        self.fish_mode = False
        if json_data:
            self.playlists = json_data.get("playlists")

    def create_playlist(self, name: str):
        self.playlists[name] = OldPlaylist(name)
        return self.playlists[name]



def default_factory(data_type): return field(default_factory=data_type)


T = TypeVar('T')


@dataclass
class Track:
    encoded: str
    title: str= ""
    duration: int=0

    @classmethod
    def fromDict(cls, data: dict):
        data = {"encoded": data} if isinstance(data, str) else data

        return cls(encoded=data.get("encoded", data),
                   title=data.get("title", ""),
                   duration=data.get("duration", 0))

    def toDict(self):
        return {
            "encoded": self.encoded,
            "title": self.title,
            "duration": self.duration
        }

    async def buildWavelinkTrack(self) -> WavelinkTrack:
        track = await buildTrack(self.encoded)
        return track

    @classmethod
    def listFromDictList(cls, data: list[dict]):
        return [cls.fromDict(track_data) for track_data in data]

    @classmethod
    def fromWavelinkTrack(cls, track: Union[WavelinkTrack, 'Track']):
        if isinstance(track, Track):
            return track
        return cls(encoded=track.encoded, title=track.title, duration=track.duration)



@dataclass
class DictFromToDictMixin:
    @classmethod
    def dictFromDict(cls, data: dict):
        return {key: cls.fromDict(_data) for key, _data in data.items()}

    @staticmethod
    def dictToDict(data: dict):
        return {key: value.toDict() for key, value in data.items()}


@dataclass
class Sound(Track, DictFromToDictMixin):
    start_time: int = 0
    end_time: int = None

    @classmethod
    def fromDict(cls, data: dict):
        data = {"encoded": data} if isinstance(data, str) else data

        encoded = data.get("encoded", data)
        title = data.get("title", "")
        duration = data.get("duration", 0)
        start_time = data.get("start_time", 0)
        end_time = data.get("end_time", None)

        return cls(encoded=encoded,
                   title=title,
                   duration=duration,
                   start_time=start_time,
                   end_time=end_time)


    def toDict(self):
        return{
            "encoded": self.encoded,
            "title": self.title,
            "duration": self.duration,
            "start_time": self.start_time,
            "end_time": self.end_time
        }

@dataclass
class Playlist(DictFromToDictMixin):
    tracks: list[Track] = default_factory(list)
    description: str=""
    duration: int=0

    @classmethod
    def fromDict(cls, data: dict):
        data = {"tracks": data} if isinstance(data, list) else data
        tracks = Track.listFromDictList(data.get("tracks", data))
        duration = data.get("duration", 0)
        return cls(tracks=tracks, duration=duration)

    def toDict(self):
        return {
            "tracks": [track.toDict() for track in self.tracks],
            "duration": self.duration,
            "description": self.description
        }

    def toPageItemDict(self):
        return {

        }

    async def buildTracks(self)->list[WavelinkTrack]:
        tracks = [await track.buildWavelinkTrack() for track in self.tracks]
        return tracks
    @classmethod
    def initFromTracks(cls, tracks: list[WavelinkTrack] | list[Track]):
        new_tracks: list[Track] = []
        duration = 0
        for track in tracks:
            track = Track.fromWavelinkTrack(track)
            new_tracks.append(track)
            duration += track.duration

        return cls(tracks=new_tracks, duration=duration)

    def updateFromTracks(self, tracks: list[WavelinkTrack] | list[Track], ignore_duplicates=True)-> tuple[list[Track], int]:
        tracks_added = []
        added_duration = 0
        for track in tracks:
            track = Track.fromWavelinkTrack(track)
            if ignore_duplicates and track in self.tracks:
                continue
            else:
                self.tracks.append(track)
                self.duration += track.duration
                tracks_added.append(track)
                added_duration += track.duration
        return tracks_added, added_duration

    def updateFromPlaylist(self, playlist: 'Playlist', ignore_duplicates=True):
        self.updateFromTracks(playlist.tracks, ignore_duplicates)

    def removeTracks(self, tracks: list[WavelinkTrack] | list[Track]):
        for track in tracks:
            track = Track.fromWavelinkTrack(track)
            while track in self.tracks:
                self.tracks.remove(track)
                self.duration -= track.duration

    def removeTrackRange(self, index: int, count: int=1) -> tuple[list[Track], int]:
        selected_tracks = self.tracks[index:index+count]
        del self.tracks[index:index+count]
        duration = sum([track.duration for track in selected_tracks])
        self.duration -= duration
        # self.tracks = self.tracks[:index] + self.tracks[track_index + count:]
        return selected_tracks, duration

    def moveTrackRange(self, index: int, new_index: int, count: int=1) -> list[Track]:
        selected_tracks = self.tracks[index:index+count]
        del self.tracks[index:index+count]
        self.tracks = self.tracks[:new_index] + selected_tracks + self.tracks[new_index:]
        return selected_tracks




    def removeTracksFromPlaylist(self, playlist: 'Playlist'):
        self.removeTracks(playlist.tracks)


@dataclass
class Tag(DictFromToDictMixin):
    content: str="No Content"
    author: str="Unknown"
    creation_date: str="Unknown"
    attachments: list[str] = field(default_factory=list)

    @classmethod
    def fromDict(cls, data: dict):
        return cls(**data)

    def toDict(self):
        return {
            "content": self.content,
            "author": self.author,
            "creation_date": self.creation_date,
            "attachments": self.attachments
        }

@dataclass
class Sentinel(DictFromToDictMixin):
    response: str = ""
    reactions: list[str] = default_factory(list)
    uses: int = 0
    enabled: bool = True

    @classmethod
    def fromDict(cls, data: dict):
        return cls(**data)

    def toDict(self):
        return {
            "response": self.response,
            "reactions": self.reactions,
            "uses": self.uses,
            "enabled": self.enabled
        }

@dataclass
class ServerData(DictFromToDictMixin):
    playlists: dict[str, Playlist] = default_factory(dict)
    soundboard: dict[str, Sound] = default_factory(dict)
    tags: dict[str, Tag] = default_factory(dict)
    sentinels: dict[str, Sentinel] = default_factory(dict)
    fish_mode: bool=False
    last_music_command_channel: TextChannel = None

    @classmethod
    def fromDict(cls, data: dict):
        playlists = Playlist.dictFromDict(data.get("playlists", {}))
        soundboard = Sound.dictFromDict(data.get("soundboard", {}))
        tags = Tag.dictFromDict(data.get("tags", {}))
        sentinels = Sentinel.dictFromDict(data.get("sentinels", {}))
        fish_mode = data.get("fish_mode", False)
        return cls(playlists=playlists,
                   soundboard=soundboard,
                   tags=tags,
                   sentinels=sentinels,
                   fish_mode=fish_mode)

    def toDict(self):
        return {
            "playlists": self.dictToDict(self.playlists),
            "soundboard": self.dictToDict(self.soundboard),
            "tags": self.dictToDict(self.tags),
            "sentinels": self.dictToDict(self.sentinels),
            "fish_mode": self.fish_mode
        }

@dataclass
class GlobalData(DictFromToDictMixin):
    # playlists: dict[str, Playlist] = default_factory(dict)
    tags: dict[str, Tag] = default_factory(dict)
    sentinels: dict[str, Sentinel] = default_factory(dict)

    @classmethod
    def fromDict(cls, data: dict):
        tags = Tag.dictFromDict(data.get("tags", {}))
        sentinels = Sentinel.dictFromDict(data.get("sentinels", {}))

        return cls(tags=tags, sentinels=sentinels)

    def toDict(self):
        return {
            "tags": self.dictToDict(self.tags),
            "sentinels": self.dictToDict(self.sentinels)
        }


@dataclass
class BotData(DictFromToDictMixin):
    servers: dict[str, ServerData] = default_factory(dict)
    globals: GlobalData = GlobalData

    @classmethod
    def fromDict(cls, data: dict):
        _globals = GlobalData.fromDict(data.get("globals", {}))
        _servers = ServerData.dictFromDict(data.get("servers", {}))

        return cls(servers=_servers, globals=_globals)

    def toDict(self):
        return {
            "globals": self.globals.toDict(),
            "servers": self.dictToDict(self.servers)
        }


@dataclass
class BotConfiguration:
    token: str
    prefix: str
    owner_id: int
    local_data_path: str
    real_data_path: str
    lavalink: dict[str, str] = None
    spotify: dict[str, str] = None

    @classmethod
    def initFromEnv(cls):
        if not os.environ.get("BOT_TOKEN"):
            print("Couldn't fine Environment Variable `BOT_TOKEN`")
            load_dotenv(find_dotenv())
        env = os.environ
        # print(env)

        return cls(
            token=env.get("BOT_TOKEN"),
            prefix=env.get("COMMAND_PREFIX"),
            owner_id=int(env.get("OWNER_ID")),
            local_data_path="bot/data",
            real_data_path=env.get("DATA_PATH"),
            lavalink={
                "uri": env.get("LAVALINK_URI"),
                "password": env.get("LAVALINK_PASSWORD")
            },
            spotify={
                "client_id": env.get("SPOTIFY_CLIENT_ID"),
                "client_secret": env.get("SPOTIFY_CLIENT_SECRET")
            }
        )





server_data = CVar[ServerData]('server_data', default=ServerData())
# server_data_context_var: ContextVar[ServerData] = ContextVar('server_data', default=ServerData)

