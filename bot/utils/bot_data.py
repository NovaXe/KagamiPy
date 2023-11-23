from dataclasses import dataclass, field

from bot.utils.music_helpers import OldPlaylist
from bot.utils.wavelink_utils import WavelinkTrack


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


@dataclass
class Track:
    encoded: str
    name: str=""
    duration: int=0

@dataclass
class Playlist:
    tracks: list[Track]
    duration: int=0

    @classmethod
    def init_from_tracks(cls, tracks: list[WavelinkTrack]):
        new_tracks = []
        duration = 0
        for track in tracks:
            new_tracks.append(Track(encoded=track.encoded, name=track.title, duration=track.duration))
            duration += track.duration

        return cls(tracks=new_tracks, duration=duration)

@dataclass
class Tag:
    content: str="No Content"
    author: str="Unknown"
    creation_date: str="Unknown"
    attachments: list[str] = field(default_factory=list)

@dataclass
class Sentinel:
    response: str = ""
    reactions: list[str] = default_factory(list)
    uses: int = 0
    enabled: bool = True

@dataclass
class ServerData:
    playlists: dict[str, Playlist] = default_factory(dict)
    soundboard: dict[str, str] = default_factory(dict)
    tags: dict[str, Tag] = default_factory(dict)
    sentinels: dict[str, Sentinel] = default_factory(dict)
    fish_mode: bool=False


@dataclass
class GlobalData:
    playlists: dict[str, Playlist] = default_factory(dict)
    tags: dict[str, Tag] = default_factory(dict)
    sentinels: dict[str, Sentinel] = default_factory(dict)


@dataclass
class BotData:
    servers: dict[str, ServerData] = default_factory(dict)
    globals: GlobalData = GlobalData



# server_data_context_var: ContextVar[ServerData] = ContextVar('server_data', default=ServerData)


"""
data structure
bot.data



"""