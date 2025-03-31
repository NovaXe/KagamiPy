from __future__ import annotations
from code import interact
from typing import Any, Literal, cast, override, Callable, Awaitable
import asyncio
import time
from math import ceil

from urllib.parse import urlparse, parse_qs

import discord
from discord import NotFound, VoiceClient, VoiceChannel, ui, ButtonStyle, TextStyle
from wavelink import Player, AutoPlayMode, QueueMode, Playable, Search
import wavelink
from bot import Kagami
from common.interactions import respond
from common.logging import setup_logging
from common.errors import CustomCheck
from common.utils import acstr, ms_timestamp
from common.types import MessageableGuildChannel
from common.paginator import ScrollerState, Scroller

from .db import TrackListDetails, TrackList, TrackListFlags

logger = setup_logging(__name__)

type Interaction = discord.Interaction[Kagami]

class NotInChannel(CustomCheck):
    MESSAGE: str = "You must be in a voice channel to use this command"

class NotInSession(CustomCheck):
    MESSAGE: str = "You must part of the voice session to use this"

class NoSession(CustomCheck):
    MESSAGE: str = "A voice session must be active to use this command"


class PlayerSession(Player):
    # _disconect_callback: Awaitable[[PlayerSession], None, None] | None = None
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.autoplay = AutoPlayMode.partial
        self.status_bar: StatusBar | None = None

    # @override
    # def cleanup(self) -> None:
    #     return super().cleanup()

    async def save_queue(self) -> None:
        return # temporarilly disabled to get the update out
        logger.debug("save_queue - pre assert")
        logger.debug(f"save_queue - {self}")
        # assert self.queue.history # because the history could be None since history is a queue but doesn't have a history of it's own
        assert self.guild
        logger.debug("save_queue - post assert")

        history_tracks, history_length = (list(self.queue.history), len(self.queue.history)) if self.queue.history else ([], 0)

        tracks = history_tracks + list(self.queue)
        logger.debug(f"save_queue - self track count: {len(tracks)}")
        current_index = history_length-1 if history_length > 0 else 0
        logger.debug(f"save_queue - current index: {current_index}")
        name = str(int(time.time()))
        list_details = TrackListDetails(self.guild.id, name, start_index=current_index, flags=TrackListFlags.session)
        logger.debug(f"save_queue - track list details: {list_details}")

        if len(tracks) == 0:
            return

        assert isinstance(self.client, Kagami)
        async with self.client.dbman.conn() as db:
            logger.debug(f"save_queue - begin insert")
            await list_details.insert(db)
            await TrackList.insert_wavelink_tracks(db, tracks, guild_id=self.guild.id, name=name)
            await db.commit()
            logger.debug(f"save_queue - committed changes")

    @override
    async def disconnect(self, **kwargs: dict[str, Any]) -> None:
        if self.status_bar:
            await self.status_bar.kill()
        await self.save_queue()
        return await super().disconnect(**kwargs)

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
        if new_index == 0 and index > 1:
            # await self.pause(True) 
            pass # does not skip over the last track if multiple tracks are skipped, lets the last track play
        elif new_index == 0 and index == 1:
            await self.skip()
        elif len(self.queue.history) > 0:
            await self.play(self.queue.history[-1], add_history=False)
        else:
            self.autoplay = AutoPlayMode.disabled
            await self.pause(True)
            # self._current = None
            await self.skip()
            self.autoplay = AutoPlayMode.partial
            # await self.pause(True)
        return new_index

    async def search_and_queue(self, query: str, position: int | None=None) -> list[Playable] | wavelink.Playlist:
        # logger.debug(f"search_and_queue - {position=}")
        if position: position = min(max(1, position), len(self.queue)) - 1 # (-1) turns this into an index
        # logger.debug(f"search_and_queue - {position=}")
        # position 1 corresponds to the next track in the queue
        # position 0 means play this shit right now, to be handled by the command that ran this method
        results: Search = await Playable.search(query)
        if len(results) == 0:
            return []
        if isinstance(results, wavelink.Playlist):
            parsed_query = cast(str, urlparse(results.url).query)
            params = parse_qs(parsed_query)
            if position is None:
                if "v" in params.items(): # isolates the specific video from the link
                    self.queue.put(results[results.selected])
                else:
                    self.queue.put(results)
            else:
                if "v" in params.items(): # isolates the specific video from the link
                    self.queue.put_at(position, results[results.selected])
                else:
                    self.queue._items = self.queue._items[:position] + list(results) + self.queue._items[position:]
        else:
            # logger.debug(f"search_and_queue - {bool(position)=}")
            self.queue.put_at(position, results[0]) if position is not None else self.queue.put(results[0])
            results = [results[0]]
        return results

    async def play_next(self) -> Playable | None:
        "Simple wrapper to get and play the next track in the queue"
        if not self.queue.is_empty:
            track = self.queue.get()
            # track = await self.queue.get_wait() 
            # waiting is uneeded because i'm already checking if the queue is or isn't empty
            await self.play(track)
        else:
            track = None
        return track

    async def update_status_bar(self) -> None:
        # logger.debug("enter update status bar")
        if self.status_bar is not None:
            # logger.debug("statusbar exists")
            await self.status_bar.update()

    # async def pause(self, value: bool, /) -> None:
    #     result = await super().pause(value)
    #     await self.update_status_bar()
    #     return result

    # async def play(self, track: Playable, *, replace: bool = True, start: int = 0, end: int | None = None, volume: int | None = None, paused: bool | None = None, add_history: bool = True, filters: wavelink.Filters | None = None, populate: bool = False, max_populate: int = 5) -> Playable:
    #     result = await super().play(track, replace=replace, start=start, end=end, volume=volume, paused=paused, add_history=add_history, filters=filters, populate=populate, max_populate=max_populate)
    #     await self.update_status_bar()
    #     return result

    def cycle_queue_mode(self) -> QueueMode:
        """
        Cycles the queue looping mode
        normal -> loop -> loop_all
        """
        # TODO: maybe don't make this async since it doesn't need to be for its primary function
        # look into just doing this update elsewhere, there has to be a better way, maybe in the command that will be calling this 
        match self.queue.mode:
            case QueueMode.normal:
                self.queue.mode = QueueMode.loop
            case QueueMode.loop:
                self.queue.mode = QueueMode.loop_all
            case QueueMode.loop_all:
                self.queue.mode = QueueMode.normal
        return self.queue.mode


class SearchQueryModal(ui.Modal, title="Search Query"):
    query: ui.TextInput["SearchQueryModal"] = ui.TextInput(label="Search Query", required=True, style=TextStyle.short)

    async def on_submit(self, interaction: Interaction, /) -> None:
        await respond(interaction)

def get_tracklist_callback(tracks: list[wavelink.Playable] | wavelink.Playlist, title: str | None=None) -> Callable[[Interaction, ScrollerState], Awaitable[tuple[str, int, int]]]:
    async def callback(irxn: Interaction, state: ScrollerState) -> tuple[str, int, int]:
        ITEM_COUNT = 10
        first_page_index = 0
        # last_page_index = len(tracks) // ITEM_COUNT
        last_page_index = ceil(len(tracks) / ITEM_COUNT) - 1
        offset = max(min(state.offset, last_page_index), first_page_index)
        W_INDEX = 7
        W_TITLE = 60
        W_DURATION = 9
        def repr(track: Playable, index: int) -> str:
            return f"{acstr(index, W_INDEX, edges=("", ")"))} {acstr(track.title, W_TITLE)} - {acstr(ms_timestamp(track.length), W_DURATION, just="r")}"

        reps: list[str] = []
        for slice_index, track in enumerate(tracks[offset*ITEM_COUNT:offset*ITEM_COUNT + ITEM_COUNT]):
            index = (slice_index + offset * 10) + 1
            rep = repr(track, index)
            reps.append(rep)
        body = '\n'.join(reps)
        formatted_title = f"{title}\n" if title else ''
        header = f"{formatted_title}{acstr('Index', W_INDEX)} {acstr('Title', W_TITLE)} - {acstr('Length', W_DURATION, just="r")}"
        content = f"```swift\n{header}\n-------\n{body}\n-------\nPage # ({first_page_index} : {offset} : {last_page_index})\n```"
        # is_last = (tag_count - offset * ITEM_COUNT) < ITEM_COUNT
        return content, first_page_index, last_page_index
    return callback


class StatusBar(ui.View):
    type Button = ui.Button["StatusBar"]
    def __init__(self, channel: MessageableGuildChannel, style: str, timeout: float | None=None):
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None
        self.channel: MessageableGuildChannel = channel
        self.style: str = style
        self.seek_milliseconds: int = 5000
        self.volume_interval: int = 10
        if style == "minimal":
            self.clear_items()

    @override
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)
        voice_state = interaction.user.voice
        voice_client = interaction.guild.voice_client
        if voice_client is not None:
            if voice_state is None or voice_state.channel != voice_client.channel:
                await respond(interaction, "You must be in the voice session to use this", ephemeral=True, delete_after=3)
                # raise CustomCheck("You must be part of the voice session to use this")
                return False
        return True

    @override
    async def on_timeout(self) -> None:
        await self.kill()
        await super().on_timeout()

    def get_content(self) -> str:
        assert (guild:=self.channel.guild) is not None, "Can't exist outside of a guild"
        assert (voice_client:=guild.voice_client) is not None, "Voice session must exist"
        session = cast(PlayerSession, voice_client)
        current_track = session.current
        rep = "```swift\nNothing is currently playing\n```"
        if self.style == "minimal" or self.style == "remote":
            if current_track is not None:
                status = "Playing" if session.playing and not session.paused else ("Paused" if session.paused else "Stopped")
                rep = f"```swift" + \
                f"\n{acstr(status, 7)} {acstr(current_track.title, 100)}" + \
                f"\n- Artist: {current_track.author}" + \
                f"\n- Duration: {ms_timestamp(current_track.length)}" + \
                "\n```"
        elif self.style == "mini-queue":
            assert session.queue.history is not None, "There is no good reason the history shouldn't exist"
            history_len = len(session.queue.history)
            queue_len = len(session.queue)
            # handles the case where a track is playing and it is the same as the last history track
            # the only case where this isn't true is when playback has been interupted in some way
            # No reason to have the previous track listed as the currently playing track, that's retarded
            rep = "```swift\n"
            if history_len > 0 and (track:=session.queue.history[-1]) != current_track:
                rep += f"\n{acstr("Prev", 7)} {acstr(track.title, 100)}" + \
                       f"\n- Artist: {track.author}" + \
                       f"\n- Duration: {ms_timestamp(track.length)}"
                rep += "\n-------"
            elif history_len > 1:
                track = session.queue.history[-2]
                rep += f"\n{acstr("Prev", 7)} {acstr(track.title, 100)}" + \
                       f"\n- Artist: {track.author}" + \
                       f"\n- Duration: {ms_timestamp(track.length)}"
                rep += "\n-------"
            if current_track is not None:
                status = "Playing" if session.playing and not session.paused else ("Paused" if session.paused else "Stopped")
                rep += f"\n{acstr(status, 7)} {acstr(current_track.title, 100)}" + \
                       f"\n- Artist: {current_track.author}" + \
                       f"\n- Duration: {ms_timestamp(current_track.length)}"
            else:
                rep += "\nNothing is currently playing"

            if queue_len > 0:
                track = session.queue[0]
                rep += "\n-------"
                rep += f"\n{acstr("Next", 7)} {acstr(track.title, 100)}" + \
                       f"\n- Artist: {track.author}" + \
                       f"\n- Duration: {ms_timestamp(track.length)}"
            rep += "\n```"
        return rep

    async def resend(self) -> None:
        """
        Used to resend the status by by deleting the old and sending a new message
        """
        if self.message is not None:
            # print(f"{self.message.id=}")
            old_message = self.message
            await old_message.delete()
            self.message = await self.channel.send(content=self.get_content(), view=self)
            await self.update()
            # _, self.message = await asyncio.gather(old_message.delete(), self.channel.send(content=self.get_content()))
        else:
            self.message = await self.channel.send(content=self.get_content(), view=self)
            await self.update()

    async def refresh(self) -> None:
        voice_client = self.channel.guild.voice_client
        if voice_client is None:
            await self.kill()
        else:
            if self.message != self.channel.last_message:
                await self.resend()
            else:
                await self.update()

    async def update(self) -> None:
        """
        Updates the statusbar message if anything has changed, otherwise do nothing
        """
        if self.message is None:
            return
        assert (guild:=self.channel.guild) is not None, "Can't exist outside of a guild"
        assert (voice_client:=guild.voice_client) is not None, "Voice session must exist"
        session = cast(PlayerSession, voice_client)
        is_anything_changed = False 
        # used to to know if the message needs to be edited in case anything changed
        # may seem redundant but without this I edit the message when I don't need to
        # Ideally I would only edit the message when I need to but the instance is owned by the
        # session and if a pause command is run I'd like it to update the view
        # I wanted to just check if message.view != self but you can't actually do that
        # only other thing would be making a copy of the current view and comparing it but that is a waste of memory

        before = self.play_pause.emoji
        # logger.debug(f"{before=}")
        self.play_pause.emoji = "▶️" if session.paused else "⏸️"
        after = self.play_pause.emoji
        # logger.debug(f"{after=}")
        # logger.debug(f"{before=}")
        is_anything_changed = is_anything_changed or before != after
        # logger.debug(f"{is_anything_changed}")

        before = self.loop_mode.emoji
        before2 = self.loop_mode.style
        match session.queue.mode:
            case QueueMode.loop:
                self.loop_mode.emoji = "🔂"
                self.loop_mode.style = ButtonStyle.blurple
            case QueueMode.loop_all:
                self.loop_mode.emoji = "🔁"
                self.loop_mode.style = ButtonStyle.blurple
            case QueueMode.normal:
                self.loop_mode.emoji = "🔁"
                self.loop_mode.style = ButtonStyle.grey
        after = self.loop_mode.emoji.id
        after2 = self.loop_mode.style
        is_anything_changed = is_anything_changed or before != after or before2 != after2
        # logger.debug(f"{is_anything_changed}")

        before = self.volume_up.label
        self.volume_up.label = f"{session.volume}"
        self.volume_down.label = f"{session.volume}"
        after = self.volume_up.label
        is_anything_changed = is_anything_changed or before != after
        # logger.debug(f"{is_anything_changed}")
        
        # old vs new content is done differently since I need the new content to edit the message
        old_content = self.message.content
        new_content = self.get_content()
        if is_anything_changed or old_content != new_content:
            # logger.debug("editting status message")
            try:
                await self.message.edit(content=new_content, view=self)
            except discord.NotFound:
                self.message = None

    async def kill(self) -> None:
        try:
            await self.message.delete() if self.message else ...
        except discord.NotFound:
            self.message = None
        self.stop()

    # First row begins here
    @ui.button(emoji="⏪", style=ButtonStyle.green, row=0)
    async def rewind(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        if session.current:
            await session.seek(max(session.position - self.seek_milliseconds, 0))
        await self.update()

    @ui.button(emoji="⏯", style=ButtonStyle.green, row=0)
    async def play_pause(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
            # raise SessionInactive 
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.pause(not session.paused)
        # button.emoji = "▶️" if session.paused else "⏸️"
        await self.update()

    @ui.button(emoji="⏩", style=ButtonStyle.green, row=0)
    async def fastforward(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        if session.current:
            await session.seek(min(session.position + self.seek_milliseconds, session.current.length))
        await self.update()

    @ui.button(emoji="🔁", style=ButtonStyle.grey, row=0)
    async def loop_mode(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        session.cycle_queue_mode()
        await self.update()

    @ui.button(emoji="🔊", style=ButtonStyle.secondary, row=0)
    async def volume_up(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.set_volume(min(200, session.volume + self.volume_interval))
        await self.update()

    # Second row begins here
    @ui.button(emoji="⏮️", style=ButtonStyle.green, row=1)
    async def skip_back(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.skipto(-1)
        await self.update()

    @ui.button(emoji="⏹️", style=ButtonStyle.green, row=1)
    async def stop_playback(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.pause(True)
        await session.seek(0)
        # self.play_pause.emoji = "▶️"
        await self.update()

    @ui.button(emoji="⏭", style=ButtonStyle.green, row=1)
    async def skip_forward(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.skipto(1)
        await self.update()

    @ui.button(emoji="🔎", style=ButtonStyle.primary, row=1)
    async def search(self, interaction: Interaction, button: Button):
        # await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        modal = SearchQueryModal()
        await interaction.response.send_modal(modal)
        if not (await modal.wait()):
            results = await session.search_and_queue(modal.query.value)
            if len(results) == 1:
                if session.current is None:
                    await session.play_next()
                    # track = await session.queue.get_wait()
                    # await session.play(track)
                    # get wait no longer used because playnext handles the logic
                    await respond(interaction, f"Now playing {track.title}", 
                                  send_followup=True, delete_after=5)
                else:
                    await respond(interaction, f"Added {results[0]} to the queue", 
                                  send_followup=True, delete_after=5)
            elif len(results) > 1:
                message = await respond(interaction, send_followup=True)
                guild = cast(discord.Guild, interaction.guild)
                session = cast(PlayerSession, guild.voice_client)
                user = cast(discord.Member, interaction.user)

                scroller = Scroller(message, user, get_tracklist_callback(results))
                if session.current is None:
                    await session.play_next()
                    # track = await session.queue.get_wait() # idfk why this was even here when it did nothing
                await scroller.update(interaction)
            else:
                await respond(interaction, "I couldn't find any tracks that matched",
                              send_followup=True, delete_after=5)
        await self.update()

    @ui.button(emoji="🔉", style=ButtonStyle.secondary, row=1)
    async def volume_down(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.set_volume(max(0, session.volume - self.volume_interval))
        await self.update()

