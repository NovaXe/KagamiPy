import collections
import math
from collections import namedtuple
import itertools
from dataclasses import dataclass
import re
from math import(ceil, floor)

import discord
from discord import(Message, Interaction)
from discord.ext import commands
from bot.kagami import Kagami
from discord.ui import(Button, Select, TextInput, View)
import wavelink
from wavelink.ext import spotify
from enum import (Enum, auto)
from bot.utils.utils import (secondsToTime, secondsDivMod, createSinglePage)
from bot.utils.utils import (PageBehavior, PageIndices, InfoSeperators, InfoTextElem, ITL)
from bot.ext.types import *

WavelinkTrack = wavelink.GenericTrack


class Player(wavelink.Player):
    class LoopType(Enum):
        NO_LOOP = auto()
        LOOP_ALL = auto()
        LOOP_TRACK = auto()

        __order__ = "NO_LOOP LOOP_ALL LOOP_TRACK"

        def next(self):
            next_value = self.value + 1
            if next_value > self.LOOP_TRACK:
                next_value = self.NO_LOOP
            return Player.LoopType(next_value)

        def prev(self):
            prev_value = self.value - 1
            if prev_value < self.NO_LOOP:
                prev_value = self.LOOP_TRACK
            return Player.LoopType(prev_value)


    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.start_pos: int = 0
        self.loop_mode = Player.LoopType.NO_LOOP
        self.interrupted = False
        self.np_message_id: int = None
        self.np_channel_id: int = None


    def setNowPlayingInfo(self, channel_id:int=None, message_id:int=None):
        self.np_channel_id = channel_id
        self.np_message_id = message_id



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




    def selectedTrack(self) -> WavelinkTrack:
        """Represents the first track in the history queue"""
        return self.queue.history.pop()

    def currentlyPlaying(self) -> (WavelinkTrack, int):
        """What the bot is actually playing"""
        return self.current, self.position

    async def cycleQueue(self, count: int = 1):
        if count == 0:
            return

        for i in range(abs(count)):
            if count>0:
                self.queue.history.put(await self.queue.get_wait())
            else:
                self.queue.put_at_front(self.queue.history.pop())
                # del self.queue.history[0]

    async def waitAddToQueue(self, tracks:[WavelinkTrack]):
        for track in tracks:
            await self.queue.put_wait(track)


    async def beginPlayback(self):
        await self.play(self.selectedTrack(),
                        replace=True)

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



class TrackType(Enum):
    YOUTUBE = auto()
    SPOTIFY = auto()
    SOUNDCLOUD = auto()


YT_URL_REG = re.compile(r"(?:https://)(?:www\.)?(?:youtube|youtu\.be)(?:\.com)?\/(?:watch\?v=)?(.{11})")
DISCORD_ATTACHMENT_REG = re.compile(r"(https://|http://)?(cdn\.|media\.)discord(app)?\.(com|net)/attachments/[0-9]{17,19}/[0-9]{17,19}/(?P<filename>.{1,256})\.(?P<mime>[0-9a-zA-Z]{2,4})(\?size=[0-9]{1,4})?")
SOUNDCLOUD_REG = re.compile("^https?:\/\/(www\.|m\.)?soundcloud\.com\/[a-z0-9](?!.*?(-|_){2})[\w-]{1,23}[a-z0-9](?:\/.+)?$")

async def searchForTracks(search: str, count: int=1) -> ([WavelinkTrack], str):
    is_yt_url = bool(YT_URL_REG.search(search))
    is_spotify_url = bool(spotify.decode_url(search))
    is_soundcloud_url = bool(SOUNDCLOUD_REG.search(search))
    attachment_regex_result = DISCORD_ATTACHMENT_REG.search(search)
    is_discord_attachment = bool(attachment_regex_result)
    node = wavelink.NodePool.get_node()

    source = ""
    # Maybe restrict length of tracks to the count for spotify and soundcloud if they behave weirdly
    if is_yt_url:
        source = "youtube"
        if "list=" in search:
            playlist: wavelink.YouTubePlaylist = await node.get_playlist(query=search, cls=wavelink.YouTubePlaylist)
            if "playlist" in search:
                source="youtube playlist"
                tracks = playlist.tracks
            else:
                tracks = [playlist.tracks[playlist.selected_track]]
        else:
            tracks = (await node.get_tracks(query=search, cls=wavelink.YouTubeTrack))[0:count]
    elif is_spotify_url:
        source = "spotify"
        # Not sure cause i think having it be the whole list will make it work for playlists
        # tracks = await spotify.SpotifyTrack.search(query=search)[0:count]
        tracks = (await spotify.SpotifyTrack.search(query=search))
    elif is_soundcloud_url:
        source = "soundcloud"
        tracks = (await node.get_tracks(query=search, cls=wavelink.SoundCloudTrack))
    elif is_discord_attachment:
        source = "attachment"
        modified_track = (await node.get_tracks(query=search, cls=wavelink.GenericTrack))[0:count]
        modified_track.title = attachment_regex_result.group("filename") + "." + attachment_regex_result.group("mime")
        tracks = [modified_track]
    else:
        source = "youtube"
        tracks = (await wavelink.YouTubeTrack.search(search))[0:count]

    return tracks, source


async def buildTracks(tracks):
    _data = {}
    _duration = 0
    for _track_id in tracks:
        _full_track = await wavelink.NodePool.get_node().build_track(cls=wavelink.GenericTrack, encoded=_track_id)
        track_duration = int(_full_track.duration // 1000)
        _duration += track_duration
        _data.update({_full_track.title: {"duration": secondsToTime(track_duration)}})
    return _data, _duration


def track_to_string(track: WavelinkTrack) -> str:
    title = ""
    title_length = len(track.title)
    if title_length > 36:
        if title_length <= 40:
            title = track.title.ljust(40)
        else:
            title = (track.title[:36] + " ...").ljust(40)
    else:
        title = track.title.ljust(40)
    message = f"{title}  -  {secondsToTime(track.length//1000)}\n"
    return message

def createNowPlayingMessage(track: WavelinkTrack, position: int=None, formatting=True) -> str:
    if track is None:
        message = f"NOW PLAYING ➤ Nothing"
    else:
        if position:
            message = f"NOW PLAYING ➤ {track.title}  -  {secondsToTime(position//1000)} / {secondsToTime(track.duration//1000)}"
        else:
            message = f"NOW PLAYING ➤ {track.title}  -  {secondsToTime(track.duration//1000)}"

    if formatting:
        message = f"**`{message}`**"
    return message


def trackListData(tracks: [WavelinkTrack]) ->(dict, int):
    data: collections.OrderedDict = {}
    total_duration = 0
    for track in tracks:
        data[track.title] = {"duration": secondsToTime(track.length//1000)}
        # data.update({track.title: {"duration": secondsToTime(track.length//1000)}})
        total_duration += track.length
    return data, total_duration


def queueSlice(queue: wavelink.Queue, start, end):
    deque_slice: list[WavelinkTrack] = list(collections.deque(itertools.islice(queue, start, end)))
    return deque_slice



def getEdgeIndices(queue: wavelink.Queue):
    history_page_count = 0
    upnext_page_count = 0
    if (h_len := len(queue.history) - 6) > 0:
        history_page_count = ceil(h_len / 10)
    if (u_len := len(queue) - 5) > 0:
        upnext_page_count = ceil(u_len / 10)

    return EdgeIndices(-1*history_page_count, upnext_page_count)



def getPageTracks(queue: wavelink.Queue, page_index: int) -> list[wavelink] | None:
    tracks: list[WavelinkTrack] = []
    history: list[WavelinkTrack] = list(queue.history)[::-1]
    upnext: list[WavelinkTrack] = list(queue)

    first_index = ceil(len(history))

    if page_index==0:
        # tracks = [*queue.history[1:6], queue.history[0], *queue[0:5]]
        history_tracks = history[1:6][::-1]
        upnext_tracks = upnext[0:5]
        selected_track = history[0:1]
        # tracks = history_tracks + selected_track + upnext_tracks
        tracks = history_tracks + upnext_tracks
    elif page_index<0:
        end = abs(page_index)*10 + 6
        start = end - 10
        tracks = history[start:end][::-1]
    else:
        start = (abs(page_index)-1)*10 + 5
        end = start+10
        tracks = upnext[start:end]

    if len(tracks):
        return tracks
    else:
        return None






def createQueuePage(queue: wavelink.Queue, page_index: int) -> str:
    """
    :param queue:
    :param page_index: history < 0 < upnext
    :return:
    """



    """
    page indices
    pg -1 : queue.history[6:16]
    offset = 6
    queue.history[offset:offset+10]
    
    
    central: 
    history: queue.history[1:6]
    selected: queue.history[0]
    upnext: queue[0:5]
    
    pg 1
    """




    tracks = getPageTracks(queue, page_index)

    track_count = len(tracks)
    h_len = len(queue.history) - 1
    mid_index = min(5, h_len)
    data = {}
    for track in tracks:
        data.update({
            track.title: {
                "duration": secondsToTime(track.duration//1000)

            }
        })

    """
          🡅Previous🡅
──────────────────────────
    """
    i_spacing = 6

    """
    first_index
    10 tracks per page
    5 tracks on page 0
    
    
    """
    iloc: ITL
    first_index: int
    if page_index < 0:
        iloc = ITL.BOTTOM
        # end = abs(page_index)*10 + 6
        # first_index = (page_index * 10) - 5 + (10 - track_count) + 1
        first_index = (page_index*10) - 6 + (10 - track_count)
    elif page_index == 0:
        iloc = ITL.MIDDLE

        first_index = -mid_index
    else:
        iloc = ITL.TOP
        first_index = ((page_index-1) * 10) + 6

    left, right = getEdgeIndices(queue)


    top_text = f"{'🡅Previous🡅'.rjust(i_spacing)}\n" \
               f"──────────────────────────"

    bottom_text = f"──────────────────────────\n" \
                  f"{'🡇Up Next🡇'.rjust(i_spacing)}"

    ignored_indices = None
    if page_index ==0:
        ignored_indices=[mid_index]
        if h_len == 0:
            top_text = None
        if len(queue) == 0:
            bottom_text = None


    now_playing = createNowPlayingMessage(queue.history[-1], formatting=False)


    info_text = InfoTextElem(text=now_playing,
                             seperators=InfoSeperators(
                                 top=top_text,
                                 bottom=bottom_text),
                             loc=iloc,
                             mid_index=mid_index)

    page_behavior = PageBehavior(elem_count=track_count,
                                 max_key_length=55,
                                 ignored_indices=ignored_indices,
                                 index_spacing=i_spacing)

    page = createSinglePage(data,
                            behavior=page_behavior,
                            infotext=info_text,
                            custom_reprs={"duration": CustomRepr("", "")},
                            first_item_index=first_index,
                            page_position=PageIndices(left, page_index, right))

    return page
    #
    # if tracks is None:
    #     page = "Nothing Here"
    # else:
    #     page = '\n'.join([track.title for track in tracks])
    # return f"{page}\n page {page_index}"




"""
queue controller
attributes:
message id
channel id

generate page on button click
cache generated pages
mark page for regen if something has changed
list[page, need_regen]
list[str, bool]

upgrade old message scroller and player controls to utilize new dynamic shit

"""




















