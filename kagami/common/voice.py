from readline import add_history
from typing import Any, Literal

from discord import VoiceClient, VoiceChannel
from wavelink import Player, AutoPlayMode
from bot import Kagami

class PlayerSession(Player):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.autoplay = AutoPlayMode.partial
    
    def shift_queue(self, shift: int) -> int:
        assert self.queue.history is not None
        count: int = 0
        if shift > 0:
            tracks = self.queue[:shift]
            count = len(tracks)
            del self.queue[:shift]
            self.queue.history.put(tracks)
        elif shift < 0:
            shift = max(shift, -len(self.queue.history))
            tracks = self.queue.history[shift:]
            count = -len(tracks)
            del self.queue.history[shift:]
            self.queue._items = tracks + self.queue._items
        return count

    async def skipto(self, index: int) -> int:
        assert self.queue.history is not None
        new_index = self.shift_queue(index)
        if len(self.queue.history) > 0:
            await self.play(self.queue.history[-1], add_history=False)
        else:
            self.autoplay = AutoPlayMode.disabled
            await self.pause(True)
            # self._current = None
            await self.skip()
            self.autoplay = AutoPlayMode.partial
            # await self.pause(True)
        return new_index
    

