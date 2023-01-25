from typing import (
    Literal,
    Dict,
    Union,
    Optional,
    List,
)

from bot.utils.music_helpers import Player
from bot.utils.music_helpers import Playlist


class Server:
    def __init__(self, guild_id: int, player=None, json_data=None):
        self.id = str(guild_id)
        self.playlists: dict[str, Playlist] = {}     # name : Playlist
        self.player: Player = player
        self.has_player: bool = False
        self.views = {}
        self.soundboard: dict[str, str] = {}

        if json_data:
            self.playlists = json_data.get("playlists")




    def create_playlist(self, name: str):
        self.playlists[name] = Playlist(name)
        return self.playlists[name]

