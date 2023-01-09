import asyncio
import math

import wavelink
from wavelink.ext import spotify
from wavelink import YouTubeTrack
import discord
from enum import Enum
from typing import List


class Server:
    def __init__(self, guild_id: int, player=None):
        self.id = str(guild_id)
        self.playlists: dict[str, Playlist] = {}     # name : Playlist
        self.player: Player = player
        self.has_player: bool = False
        self.views = {}


    def create_playlist(self, name: str):
        self.playlists[name] = Playlist(name)
        return self.playlists[name]


class Playlist:
    def __init__(self, name: str, track_list: list[str] = None):
        self.tracks: list[str] = [] if track_list is None else track_list
        self.name = name

    def add_track(self, track: wavelink.Track) -> None:
        self.tracks.append(track.id)

    def remove_track(self, track: wavelink.Track) -> None:
        self.tracks.remove(track.id)

    def remove_track_at(self, position: int) -> None:
        self.tracks.pop(position)

    def update_list(self, new_tracks: list[wavelink.Track]):
        track_list = []
        for track in new_tracks:
            track_list.append(track.id)
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


class Player(wavelink.Player):
    def __init__(self, dj_user: discord.Member, dj_channel: discord.TextChannel):
        super().__init__()
        self.history = wavelink.Queue()
        self.queue = wavelink.Queue()
        self.current_track: wavelink.Track = None
        self.loop_mode: LoopMode = LoopMode.NO_LOOP
        self.dj_user: discord.Member = dj_user
        self.dj_channel: discord.TextChannel = dj_channel
        self.skip_count = 1
        self.skip_to_prev = False
        self.skip_mode: SkipMode = SkipMode.NEXT
        self.queue_views = []
        self.is_stopped = False
        self.now_playing_message: discord.Message = None


    async def add_to_queue(self, single: bool, track: wavelink.Track) -> None:
        if single:
            self.queue.put(track)
        else:
            self.queue.extend(track)

    def get_next_song(self) -> wavelink.Track:
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
        await self.play(source=self.current_track, replace=True)
        # await asyncio.sleep(3)
        # pass

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


def track_to_string(track: wavelink.Track):
    title = ""
    title_length = len(track.title)
    if title_length > 36:
        if title_length <= 40:
            title = track.title.ljust(40)
        else:
            title = (track.title[:36] + " ...").ljust(40)
    else:
        title = track.title.ljust(40)
    message = f"{title}  -  {int(track.length // 60)}:{int(track.length % 60):02}\n"
    return message


async def create_queue_pages(player: Player):
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

        now_playing_text = f"NOW PLAYING ➤ {now_playing.title}" \
                           f"  -  {int(player.position / 60)}" \
                           f":{int(player.position % 60):02}" \
                           f" / {int(now_playing.length / 60)}:{int(now_playing.length % 60):02}\n"
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

