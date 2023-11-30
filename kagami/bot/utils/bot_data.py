from dataclasses import dataclass, field

from bot.utils.music_helpers import OldPlaylist
from bot.utils.wavelink_utils import WavelinkTrack
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


@dataclass
class Track:
    encoded: str
    name: str=""
    duration: int=0

    @classmethod
    def fromWavelinkTrack(cls, track: WavelinkTrack | Track) -> Track:
        if isinstance(track, Track):
            return track
        return cls(encoded=track.encoded, name=track.title, duration=track.duration)



@dataclass
class Playlist:
    tracks: list[Track]
    duration: int=0

    @classmethod
    def initFromTracks(cls, tracks: list[WavelinkTrack] | list[Track]) -> Playlist:
        new_tracks: list[Track] = []
        duration = 0
        for track in tracks:
            track = Track.fromWavelinkTrack(track)
            new_tracks.append(track)
            duration += track.duration

        return cls(tracks=new_tracks, duration=duration)

    def updateFromTracks(self, tracks: list[WavelinkTrack] | list[Track], ignore_duplicates=True):
        for track in tracks:
            track = Track.fromWavelinkTrack(track)
            if ignore_duplicates and track in self.tracks:
                continue
            else:
                self.tracks.append(track)
                self.duration += track.duration

    def updateFromPlaylist(self, playlist: Playlist, ignore_duplicates=True):
        self.updateFromTracks(playlist.tracks, ignore_duplicates)

    def removeTracks(self, tracks: list[WavelinkTrack] | list[Track]):
        for track in tracks:
            track = Track.fromWavelinkTrack(track)
            while track in self.tracks:
                self.tracks.remove(track)
                self.duration -= track.duration

    def removeTracksFromPlaylist(self, playlist: Playlist):
        self.removeTracks(playlist.tracks)





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

    @classmethod
    def fromDict(cls, data: dict):
        # TODO implement this for python dict data
        pass


@dataclass
class GlobalData:
    playlists: dict[str, Playlist] = default_factory(dict)
    tags: dict[str, Tag] = default_factory(dict)
    sentinels: dict[str, Sentinel] = default_factory(dict)

    @classmethod
    def fromDict(cls, data: dict):
        # TODO implement this for python dict data
        pass


@dataclass
class BotData:
    servers: dict[str, ServerData] = default_factory(dict)
    globals: GlobalData = GlobalData

    @classmethod
    def fromDict(cls, data: dict):
        # TODO implement this for python dict data
        # No reason to do this in the main bot file, do it all here
        pass



# server_data_context_var: ContextVar[ServerData] = ContextVar('server_data', default=ServerData)


"""
data structure
bot.data



"""
server_data = CVar[ServerData]('server_data', default=ServerData())
