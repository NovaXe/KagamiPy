import math
import re

import wavelink
from wavelink.ext import spotify
import discord
from enum import Enum
from bot.utils.utils import (
    secondsDivMod
)


class OldPlaylist:
    def __init__(self, name: str, track_list: list[str] = None):
        self.tracks: list[str] = [] if track_list is None else track_list
        self.name = name

    def add_track(self, track: wavelink.GenericTrack) -> None:
        self.tracks.append(track.encoded)

    def remove_track(self, track: wavelink.GenericTrack) -> None:
        self.tracks.remove(track.encoded)

    def remove_track_at(self, position: int) -> None:
        self.tracks.pop(position)

    def update_list(self, new_tracks: list[wavelink.GenericTrack]):
        track_list = []
        for track in new_tracks:
            track_list.append(track.encoded)
        self.tracks = list(dict.fromkeys(self.tracks + track_list).keys())
        # self.tracks = list(set(self.tracks + new_tracks))


class LoopMode(Enum):
    NO_LOOP = 0
    LOOP_QUEUE = 1
    LOOP_SONG = 2

    __order__ = "NO_LOOP LOOP_QUEUE LOOP_SONG"

    def next(self):
        next_value = self.value + 1
        if next_value > 2:
            next_value = 0
        return LoopMode(next_value)

    def prev(self):
        prev_value = self.value - 1
        if prev_value < 0:
            prev_value = 2
        return LoopMode(prev_value)


class SkipMode(Enum):
    NEXT = 0
    PREV = 1


class OldPlayer(wavelink.Player):
    def __init__(self, dj_user: discord.Member, dj_channel: discord.TextChannel):
        super().__init__()
        self.history = wavelink.Queue()
        self.queue = wavelink.Queue()
        self.current_track: wavelink.GenericTrack = None
        self.loop_mode: LoopMode = LoopMode.NO_LOOP
        self.dj_user: discord.Member = dj_user
        self.dj_channel: discord.TextChannel = dj_channel
        self.skip_count = 1
        self.skip_to_prev = False
        self.skip_mode: SkipMode = SkipMode.NEXT
        self.queue_views = []
        self.is_stopped = False
        self.now_playing_message: discord.Message = None


        self.interrupt_position = 0
        self.interrupted_by_sound = False


    async def add_to_queue(self, single: bool, track: wavelink.GenericTrack) -> None:
        if single:
            self.queue.put(track)
        else:
            self.queue.extend(track)

    def get_next_song(self) -> wavelink.GenericTrack:
        return self.queue.get()

    async def play_next_track(self):
        await self.cycle_track()
        await self.start_current_track()

    async def play_previous_track(self):
        await self.cycle_track(reverse=True)
        await self.start_current_track()

    async def start_current_track(self):
        if self.current_track is None:
            return
        await self.play(track=self.current_track, replace=True)
        # await asyncio.sleep(3)
        # pass

    async def interrupt_current_track(self, track):
        if self.current_track:
            self.interrupt_position = self.position
            self.interrupted_by_sound = True

        await self.play(track=track, replace=True)

    async def resume_interrupted_track(self):
        if self.current_track:
            await self.play(track=self.current_track, replace=True)
            await self.seek(int(self.interrupt_position*1000))
            self.interrupt_position = 0
            self.interrupted_by_sound = False


    async def restart_current_track(self):
        # await self.pause()
        await self.start_current_track()
        # await self.resume()

    async def cycle_track(self, reverse: bool = False):
        if reverse:
            if self.current_track is not None:
                self.queue.put_at_front(self.current_track)
            if not self.history.is_empty:
                self.current_track = self.history.pop()
            else:
                self.current_track = None
        else:
            if self.current_track is not None:
                self.history.put(self.current_track)
            if not self.queue.is_empty:
                self.current_track = self.queue.get()
            else:
                self.current_track = None
        # print("cycled track\n")

    def change_loop_mode(self, mode: LoopMode = None):
        if mode:
            self.loop_mode = mode
            return

        self.loop_mode = iter(self.loop_mode)


    # async def restart_track(self):
    #     await self.play(source=self.current_track, replace=True)
    #
    # async def seek_track(self, seconds: int):
    #     await self.seek(seconds)
     

# async def update_now_playing_message(player: Player, channel: discord.TextChannel=None):
#     if channel is None:
#         channel = player.dj_channel
#     track = player.current_track
#     track_hours = int(track.duration // 3600)
#     track_minutes = int((track.duration % 60) // 60)
#     track_seconds = int(track.duration % 60)
#     message = f"**`NOW PLAYING {track.title}  -  {f'{track_hours}:02' + ':' if track_hours > 0 else ''}{track_minutes:02}:{track_seconds:02} `**"
#     await player.now_playing_message.delete()
#     player.now_playing_message = await channel.send(content=message)

def track_to_string(track: wavelink.GenericTrack):
    title = ""
    title_length = len(track.title)
    if title_length > 36:
        if title_length <= 40:
            title = track.title.ljust(40)
        else:
            title = (track.title[:36] + " ...").ljust(40)
    else:
        title = track.title.ljust(40)

    d_hours, d_minutes, d_seconds = secondsDivMod(int(track.length // 1000))
    message = f"{title}  -  {f'{d_hours}:02' + ':' if d_hours > 0 else ''}{d_minutes:02}:{d_seconds:02}\n"
    return message


async def create_queue_pages(player: OldPlayer):
    now_playing = player.current_track
    history_list = list(player.history)
    history_length = len(history_list)
    queue_list = list(player.queue)
    queue_length = len(queue_list)

    history_peek = history_list[-5:]
    queue_peek = queue_list[:5]

    hidden_history = history_list[:-5]
    hidden_queue = queue_list[5:]

    total_page_count = math.ceil(len(hidden_history) / 10) + 1 + math.ceil(len(hidden_queue) / 10)

    home_page = 0

    pages = []
    current_page = 0




    now_playing_text = ""
    if now_playing:
        d_hours, d_minutes, d_seconds = secondsDivMod(int(now_playing.length // 1000))
        p_hours, p_minutes, p_seconds = secondsDivMod(int(player.position // 1000))

        now_playing_text = f"NOW PLAYING ➤ {now_playing.title}" \
                           f"  -  {f'{p_hours}:02' + ':' if p_hours > 0 else ''}{p_minutes:02}:{p_seconds:02}" \
                           f" / {f'{d_hours}:02' + ':' if d_hours > 0 else ''}{d_minutes:02}:{d_seconds:02}\n"
    else:
        if not history_peek and not queue_peek:
            now_playing_text = "The queue is empty\n"
        else:
            now_playing_text = f"__**NOW PLAYING**__ ➤ Nothing\n"


    track_index = 0
    hidden_history.reverse()
    for page_number, page_list in [(int(i/10), hidden_history[i:i+10]) for i in range(0, len(hidden_history), 10)]:
        current_page = page_number
        content = "```swift\n"
        content_list = []
        for index, track in enumerate(page_list):
            track_index += 1
            track_string = track_to_string(track)
            position = (str(track_index+5) + ")").ljust(5)
            content_list.append(f"{position} {track_string}")

        content_list.reverse()
        content += ''.join(content_list)

        content += "      🡅Previous🡅\n" \
                   "──────────────────────────\n"
        content += now_playing_text
        content += f"Page #: {math.ceil(len(hidden_history) / 10) - current_page} / {total_page_count}\n"
        content += "```"
        pages.insert(current_page, content)
        # pages[current_page] = content

    pages.reverse()
    if len(hidden_history):
        current_page += 1
    # current_page += 1
    content = "```swift\n"
    for index, track in enumerate(history_peek):
        track_string = track_to_string(track)
        position = (str(5 - index) + ")").ljust(5)
        content += f"{position} {track_string}"
    if len(history_peek):
        content += f"      🡅Previous🡅\n" \
                   f"──────────────────────────\n"

    content += now_playing_text
    home_page = current_page
    if len(queue_peek):
        content += "──────────────────────────\n" \
                   "      🡇Up Next🡇\n"

    for index, track in enumerate(queue_peek):
        track_string = track_to_string(track)
        position = (str(index + 1) + ")").ljust(5)
        content += f"{position} {track_string}"

    content += f"Page #: {current_page+1} / {total_page_count}\n"
    content += "```"
    # pages[current_page] = content

    pages.insert(current_page, content)
    current_page += 1


    track_index = 0
    for page_number, page_list in [(int(i/10), hidden_queue[i:i+10]) for i in range(0, len(hidden_queue), 10)]:

        content = "```swift\n"
        content += now_playing_text
        content += "──────────────────────────\n" \
                   "      🡇Up Next🡇\n"
        for index, track in enumerate(page_list):
            track_index += 1
            track_string = track_to_string(track)
            position = (str(track_index+5) + ")").ljust(5)
            content += f"{position} {track_string}"

        # pages[current_page] = content
        content += f"Page #: {current_page + page_number+1} / {total_page_count}\n"
        content += "```"
        pages.insert(current_page + page_number, content)


    return pages, home_page


URL_REG = re.compile(r'https?://(?:www\.)?.+')
YT_URL_REG = re.compile(r"(?:https://)(?:www\.)?(?:youtube|youtu\.be)(?:\.com)?\/(?:watch\?v=)?(.{11})")
YT_PLAYLIST_REG = re.compile(r"[\?|&](list=)(.*)\&")
DISCORD_ATTACHMENT_REG = re.compile(r"(https://|http://)?(cdn\.|media\.)discord(app)?\.(com|net)/attachments/[0-9]{17,19}/[0-9]{17,19}/(?P<filename>.{1,256})\.(?P<mime>[0-9a-zA-Z]{2,4})(\?size=[0-9]{1,4})?")
SOUNDCLOUD_REG = re.compile("^https?:\/\/(www\.|m\.)?soundcloud\.com\/[a-z0-9](?!.*?(-|_){2})[\w-]{1,23}[a-z0-9](?:\/.+)?$")


async def search_song(search: str, single_track=False) -> list[wavelink.GenericTrack]:
    is_yt_url = bool(YT_URL_REG.search(search))
    is_url = bool(URL_REG.search(search))
    decoded_spotify_url = spotify.decode_url(search)
    is_spotify_url = bool(decoded_spotify_url is not None)
    is_soundcloud_url = bool(SOUNDCLOUD_REG.search(search))
    attachment_regex_result = DISCORD_ATTACHMENT_REG.search(search)
    is_discord_attachment = bool(attachment_regex_result)
    tracks = []

    node = wavelink.NodePool.get_node()

    if is_yt_url:
        if "list=" in search:

            playlist = await node.get_playlist(query=search, cls=wavelink.YouTubePlaylist)
            if "playlist" in search:
                tracks = playlist.tracks
            else:
                tracks = [playlist.tracks[playlist.selected_track]]
        else:
            tracks = await node.get_tracks(query=search, cls=wavelink.YouTubeTrack)
    elif is_spotify_url:
        tracks = await spotify.SpotifyTrack.search(query=decoded_spotify_url.id)

    elif is_soundcloud_url:
        tracks = await node.get_tracks(query=search, cls=wavelink.SoundCloudTrack)

    elif is_discord_attachment:
        modified_track = (await node.get_tracks(query=search, cls=wavelink.GenericTrack))[0]
        modified_track.title = attachment_regex_result.group("filename")+"."+attachment_regex_result.group("mime")
        tracks = [modified_track]
    else:
        tracks = [(await wavelink.YouTubeTrack.search(search))[0]]
    return tracks[0] if single_track else tracks

