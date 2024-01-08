from enum import Enum, auto
from typing import Union, List, Literal, Any
import wavelink
from discord import TextChannel
from wavelink import YouTubeTrack, YouTubePlaylist, Playable, InvalidLavalinkResponse
from wavelink.ext import spotify
from wavelink.player import logger as wavelink_logger

from bot.ext.responses import PersistentMessage
from bot.utils.context_vars import CVar
from bot.utils.wavelink_utils import WavelinkTrack
from bot.utils.bot_data import Track


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
        self.halted_queue_count = 0
        self.priority_queue = wavelink.Queue()
        self.playlist_queue = wavelink.Queue()
        self.sound_queue = wavelink.Queue()

        """
        queue order
        Sound > Priority > Playlist > Queue
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


    def halt(self):
        self.halted_queue_count = self.queue.count
        self.halted = True
    async def stop(self, *, halt: bool=False, force: bool = True) -> None:
        if halt: self.halt()
        await super().stop(force=force)



    def popSelectedTrack(self) -> WavelinkTrack:
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


    async def popNextTrack(self) -> tuple[WavelinkTrack, bool]:
        """Soundboard > Priority > Playlist > Queue"""
        track: WavelinkTrack
        history = True
        if self.sound_queue.count: # Sound Queue
            track = await self.sound_queue.get_wait()
            history = False
        elif self.priority_queue.count: # Priority Queue
            track = await self.priority_queue.get_wait()
        elif self.playlist_queue.count: # Playlist Queue
            track = await self.playlist_queue.get_wait()
        elif self.queue.count: # Music Queue
            track = await self.queue.get_wait()
        else:
            track = None
        return track, history

    def popPreviousTrack(self):
        track = self.queue.history.pop()
        return track

    async def cycleQueue(self, count: int = 1):
        for i in range(abs(count)):
            if count > 0:
                # Skip forward
                if self.queue.count or self.queue.loop or self.queue.loop_all:
                    # track = await self.queue.get_wait()
                    track, history = await self.popNextTrack()
                    if history: self.queue.history.put(track)
                    # track = self.queue.get()
                    # self.queue.history.put(track)
                else:
                    total_skipped = i
                    # self.halt()
                    break
            else:
                # Skip Backward
                if self.queue.history.count:
                    track = self.popPreviousTrack()
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

    async def waitAddToQueue(self, tracks: list[WavelinkTrack] | WavelinkTrack):
        if isinstance(tracks, list):
            for track in tracks: await self.queue.put_wait(track)
        else:
            await self.queue.put_wait(tracks)
        # for track in tracks:
        #     self.queue.extend(track)

    async def addToQueue(self, tracks: [WavelinkTrack]):
        self.queue.extend(tracks)


    async def queueTracks(self, queue: Literal["music", "priority", "playlist", "soundboard"], tracks: list[WavelinkTrack] | WavelinkTrack):
        if queue == "music":
            queue = self.queue
        elif queue == "priority":
            queue = self.priority_queue
        elif queue == "playlist":
            queue = self.playlist_queue
        elif queue == "soundboard":
            queue = self.sound_queue

        if isinstance(tracks, list):
            for track in tracks: await queue.put_wait(tracks)
        else:
            await self.queue.put_wait(tracks)

    async def buildAndQueue(self, tracks: list[Track] | Track):
        if isinstance(tracks, list):
            new_tracks = [await track.buildWavelinkTrack() for track in tracks]
        else:
            new_tracks = await tracks.buildWavelinkTrack()
        await self.waitAddToQueue(new_tracks)

    async def haltPlayback(self):
        self.halted = True
        await self.stop()



    async def play(self,
                   track: Playable | spotify.SpotifyTrack,
                   replace: bool = True,
                   start: int | None = None,
                   end: int | None = None,
                   volume: int | None = None,
                   *,
                   populate: bool = False,
                   queue_source: wavelink.Queue = None
                   ) -> Playable:
        """|coro|

        Play a WaveLink Track.

        Parameters
        ----------
        track: :class:`tracks.Playable`
            The :class:`tracks.Playable` or :class:`~wavelink.ext.spotify.SpotifyTrack` track to start playing.
        replace: bool
            Whether this track should replace the current track. Defaults to ``True``.
        start: Optional[int]
            The position to start the track at in milliseconds.
            Defaults to ``None`` which will start the track at the beginning.
        end: Optional[int]
            The position to end the track at in milliseconds.
            Defaults to ``None`` which means it will play until the end.
        volume: Optional[int]
            Sets the volume of the player. Must be between ``0`` and ``1000``.
            Defaults to ``None`` which will not change the volume.
        populate: bool
            Whether to populate the AutoPlay queue. Defaults to ``False``.
        queue_source: wavelink.Queue
            The queue that the track was sourced from, None if there wasn't a source
            .. versionadded:: 2.0

        Returns
        -------
        :class:`~tracks.Playable`
            The track that is now playing.


        .. note::

            If you pass a :class:`~wavelink.YouTubeTrack` **or** :class:`~wavelink.ext.spotify.SpotifyTrack` and set
            ``populate=True``, **while** :attr:`~wavelink.Player.autoplay` is set to ``True``, this method will populate
            the ``auto_queue`` with recommended songs. When the ``auto_queue`` is low on tracks this method will
            automatically populate the ``auto_queue`` with more tracks, and continue this cycle until either the
            player has been disconnected or :attr:`~wavelink.Player.autoplay` is set to ``False``.


        Example
        -------

        .. code:: python3

            tracks: list[wavelink.YouTubeTrack] = await wavelink.YouTubeTrack.search(...)
            if not tracks:
                # Do something as no tracks were found...
                return

            await player.queue.put_wait(tracks[0])

            if not player.is_playing():
                await player.play(player.queue.get(), populate=True)


        .. versionchanged:: 2.6.0

            This method now accepts :class:`~wavelink.YouTubeTrack` or :class:`~wavelink.ext.spotify.SpotifyTrack`
            when populating the ``auto_queue``.
        """
        assert self._guild is not None

        if isinstance(track, YouTubeTrack) and self.autoplay and populate:
            query: str = f'https://www.youtube.com/watch?v={track.identifier}&list=RD{track.identifier}'

            try:
                recos: YouTubePlaylist = await self.current_node.get_playlist(query=query, cls=YouTubePlaylist)
                recos: list[YouTubeTrack] = getattr(recos, 'tracks', [])

                queues = set(self.queue) | set(self.auto_queue) | set(self.auto_queue.history) | {track}

                for track_ in recos:
                    if track_ in queues:
                        continue

                    await self.auto_queue.put_wait(track_)

                self.auto_queue.shuffle()
            except ValueError:
                pass

        elif isinstance(track, spotify.SpotifyTrack):
            original = track
            track = await track.fulfill(player=self, cls=YouTubeTrack, populate=populate)

            if populate:
                self.auto_queue.shuffle()

            for attr, value in original.__dict__.items():
                if hasattr(track, attr):
                    wavelink_logger.warning(f'Player {self.guild.id} was unable to set attribute "{attr}" '
                                   f'when converting a SpotifyTrack as it conflicts with the new track type.')
                    continue

                setattr(track, attr, value)

        data = {
            'encodedTrack': track.encoded,
            'position': start or 0,
            'volume': volume or self._volume
        }

        if end:
            data['endTime'] = end

        self._current = track
        self._original = track

        try:
            resp: dict[str, Any] = await self.current_node._send(
                method='PATCH',
                path=f'sessions/{self.current_node._session_id}/players',
                guild_id=self._guild.id,
                data=data,
                query=f'noReplace={not replace}'
            )

        except InvalidLavalinkResponse as e:
            self._current = None
            self._original = None
            wavelink_logger.debug(f'Player {self._guild.id} attempted to load track: {track}, but failed: {e}')
            raise e

        self._player_state['track'] = resp['track']['encoded']


        # Custom code Start
        if queue_source is None: queue_source = self.queue
        if not (queue_source.loop and queue_source._loaded):
            # self.queue.history.put(track)
            queue_source.history.put(track)

        queue_source._loaded = track
        # custom code end
        self.queue._loaded = track

        wavelink_logger.debug(f'Player {self._guild.id} loaded and started playing track: {track}.')
        return track


    async def beginPlayback(self):
        self.halted = False
        if track:=self.popSelectedTrack():
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
        await self.play(self.popSelectedTrack(),
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

    def allTracks(self):
        tracks = list(self.queue.history) + list(self.queue)
        return tracks


    # put implements


player_instance = CVar[Player]('player_instance', default=None)
