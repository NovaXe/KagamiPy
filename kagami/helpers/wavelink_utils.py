import collections
import itertools
import re
from math import ceil

import wavelink
from wavelink.ext import spotify

from common.utils import secondsToTime

WavelinkTrack = wavelink.GenericTrack


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



def createNowPlayingMessage(track: WavelinkTrack, position: int=None,
                            formatting=True, show_arrow=True, descriptor_text: str="NOW PLAYING") -> str:
    if track is None:
        message = f"{descriptor_text} ➤ Nothing"
    else:
        if position:
            message = f"{descriptor_text} {'➤ ' if show_arrow else ''}{track.title}  -  {secondsToTime(position//1000)} / {secondsToTime(track.duration//1000)}"
        else:
            message = f"{descriptor_text} {'➤ ' if show_arrow else ''}{track.title}  -  {secondsToTime(track.duration//1000)}"

    if formatting:
        message = f"**`{message}`**"
    return message


def trackListData(tracks: [WavelinkTrack]) ->tuple[dict, int]:
    data: collections.OrderedDict = {}
    total_duration = 0
    for track in tracks:
        data[track.title] = {"duration": secondsToTime(track.duration//1000)}
        # data.update({track.title: {"duration": secondsToTime(track.length//1000)}})
        total_duration += track.duration
    return data, total_duration


def queueSlice(queue: wavelink.Queue, start, end):
    deque_slice: list[WavelinkTrack] = list(collections.deque(itertools.islice(queue, start, end)))
    return deque_slice


def getPageTracks(queue: wavelink.Queue, page_index: int) -> list[wavelink] | None:
    tracks: list[WavelinkTrack] = []
    history: list[WavelinkTrack] = list(queue.history)[::-1]
    upnext: list[WavelinkTrack] = list(queue)

    first_index = ceil(len(history))

    if page_index==0:
        # tracks = [*queue.history[1:6], queue.history[0], *queue[0:5]]
        history_tracks = history[1:6][::-1]
        upnext_tracks = upnext[0:5]
        # selected_track = history[-1:-2] Probably wrong idf cause I think the correct one is at -1
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
        return []


YT_URL_REG = re.compile(r"(?:https://)(?:www\.)?(?:youtube|youtu\.be)(?:\.com)?\/(?:watch\?v=)?(.{11})")
DISCORD_ATTACHMENT_REG = re.compile(r"(https://|http://)?(cdn\.|media\.)discord(app)?\.(com|net)/attachments/[0-9]{17,19}/[0-9]{17,19}/(?P<filename>.{1,256})\.(?P<mime>[0-9a-zA-Z]{2,4})(\?size=[0-9]{1,4})?")
SOUNDCLOUD_REG = re.compile("^https?:\/\/(www\.|m\.)?soundcloud\.com\/[a-z0-9](?!.*?(-|_){2})[\w-]{1,23}[a-z0-9](?:\/.+)?$")


async def searchForTracks(search: str, count: int=1) -> tuple[list[WavelinkTrack], str]:
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
        modified_track = (await node.get_tracks(query=search, cls=wavelink.GenericTrack))[0]
        modified_track.title = attachment_regex_result.group("filename") + "." + attachment_regex_result.group("mime")
        tracks = [modified_track]
    else:
        source = "youtube"
        tracks = (await wavelink.YouTubeTrack.search(search))[0:count]

    return tracks, source



async def buildTrack(track_encoded: str)->WavelinkTrack:
    return await wavelink.NodePool.get_node().build_track(cls=WavelinkTrack, encoded=track_encoded)
