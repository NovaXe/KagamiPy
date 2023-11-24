from enum import Enum, auto
import wavelink

from bot.ext.responses import PersistentMessage
from bot.utils.wavelink_utils import WavelinkTrack


class Player(wavelink.Player):
    class LoopType(Enum):
        NO_LOOP = auto()
        LOOP_ALL = auto()
        LOOP_TRACK = auto()

        __order__ = "NO_LOOP LOOP_ALL LOOP_TRACK"

        def next(self):
            next_value = self.value + 1
            if next_value > self.LOOP_TRACK.value:
                next_value = self.NO_LOOP.value
            return Player.LoopType(next_value)

        def prev(self):
            prev_value = self.value - 1
            if prev_value < self.NO_LOOP.value:
                prev_value = self.LOOP_TRACK.value
            return Player.LoopType(prev_value)

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.start_pos: int = 0
        self.loop_mode = Player.LoopType.NO_LOOP
        self.interrupted = False
        self.now_playing_message: PersistentMessage = None
        self.halted = True
        self.priority_queue = wavelink.Queue
        self.playlist_queue = wavelink.Queue
        self.soundboard_queue = wavelink.Queue

        """
        queue order
        Soundboard > Priority > Playlist > Queue
        
        """

        # halting conditions
        # playing nothing
        # skipped past first or last track in entire queue
        #
        # self.queue_displays: list[PageScroller] = []

    def changeLoopMode(self, mode: LoopType=None):
        if not mode:
            self.loop_mode = iter(self.loop_mode)
        else:
            self.loop_mode = mode

        if mode is mode.NO_LOOP:
            self.queue.loop = False
            self.queue.loop_all = False
        elif mode is mode.LOOP_ALL:
            self.queue.loop = False
            self.queue.loop_all = True
        elif mode is mode.LOOP_TRACK:
            self.queue.loop = True
            self.queue.loop_all = False

    async def stop(self, *, halt: bool=False, force: bool = True) -> None:
        if halt: self.halted=True
        await super().stop(force=force)

    def selectedTrack(self) -> WavelinkTrack:
        """Represents the first track in the history queue"""
        if self.queue.history.count:
            return self.queue.history.pop()
        else:
            return None

    def currentlyPlaying(self) -> tuple[WavelinkTrack, int]:
        """What the bot is actually playing\n
        :returns (current track, position in milliseconds)
        """
        return self.current, self.position

    async def cycleQueue(self, count: int = 1):
        for i in range(abs(count)):
            if count > 0:
                # Skip forward
                if self.queue.count or self.queue.loop or self.queue.loop_all:
                    track = await self.queue.get_wait()
                    # track = self.queue.get()
                    self.queue.history.put(track)
                else:
                    total_skipped = i
                    # self.halt()
                    break
            else:
                # Skip Backward
                if self.queue.history.count:
                    track = self.queue.history.pop()
                    self.queue.put_at_front(track)
                else:
                    total_skipped = i
                    # self.halt()
                    break
        else:
            total_skipped = abs(count)
        return total_skipped



        # for i in range(abs(count)):
        #     if count>0:
        #         self.queue.history.put(await self.queue.get_wait())
        #     else:
        #         self.queue.put_at_front(self.queue.history.pop())
        #         # del self.queue.history[0]

    async def waitAddToQueue(self, tracks:[WavelinkTrack]):
        for track in tracks:
            await self.queue.put_wait(track)
        # for track in tracks:
        #     self.queue.extend(track)

    async def addToQueue(self, tracks:[WavelinkTrack]):
        self.queue.extend(tracks)

    async def haltPlayback(self):
        self.halted = True
        await self.stop()

    async def beginPlayback(self):
        self.halted = False
        if track:=self.selectedTrack():
            await self.play(track,
                            replace=True)
        else:
            self.halted=True

    async def cyclePlayNext(self):
        if await self.cycleQueue() !=0:
            await self.beginPlayback()
        else:
            await self.stop(halt=True)

    async def cyclePlayPrevious(self):
        if await self.cycleQueue(-1) !=0:
            await self.beginPlayback()
        else:
            await self.stop(halt=True)

    # on begin playback
    # unhalt potentially give a different name
    #



    async def resumeInteruptedTrack(self):
        """Contninues playback of the currently selected track after an interuption"""
        await self.play(self.selectedTrack(),
                        replace=True,
                        start=self.start_pos)
        self.start_pos = 0

    async def interuptPlayback(self, track: WavelinkTrack, start:int=None, end:int=None):
        """
        :param track: The desired track to play
        :param start: Time to start playback in miliseconds
        :param end: Time to end playback in miliseconds
        """
        self.savePos()
        await self.play(track,
                        replace=True,
                        start=start,
                        end=end)

    def savePos(self):
        self.start_pos = self.position









    async def playNext(self):
        pass

    async def playPrevious(self):
        pass

    # put implements
