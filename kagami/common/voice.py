from typing import Any, Literal

from discord import VoiceClient, VoiceChannel
from wavelink import Player
from bot import Kagami

class PlayerSession(Player):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        