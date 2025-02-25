from dataclasses import dataclass
from enum import IntEnum
from inspect import getcallargs
from typing import (
    Literal, List, Callable, Any, cast, get_args, override
)
import datetime
import math
import time
import re
from math import ceil, floor, copysign
import PIL as pillow
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from urllib.parse import urlparse, parse_qs
import aiosqlite
import discord
from discord.ext import commands, tasks
from discord import (
    Status,
    TextChannel,
    ui,
    VoiceClient, 
    VoiceState, 
    app_commands, 
#    Interaction, 
    Member, 
    VoiceChannel,
    voice_client,
)
from discord.ext.commands import GroupCog, Cog, MessageNotFound
from discord.app_commands import Transform, Transformer, Group, Choice, Range
from discord import ButtonStyle
import wavelink
from wavelink import Playable, Search, TrackEndEventPayload, TrackStartEventPayload, WebsocketClosedEventPayload

from bot import Kagami
from common import errors
from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, PersistentSettings
from common.paginator import Scroller, ScrollerState
from common.types import MessageableGuildChannel
from .voice import PlayerSession, StatusBar, NotInChannel, NotInSession, NoSession, get_tracklist_callback
from .db import TrackList, TrackListDetails, TrackListFlags
from utils.depr_db_interface import Database
from common.utils import acstr, ms_timestamp, secondsToTime, milliseconds_divmod

from cogs.voice import voice

logger = setup_logging(__name__)

type VocalGuildChannel = VoiceChannel | discord.StageChannel
type Interaction = discord.Interaction[Kagami]

async def joinChannel(voice_channel: VocalGuildChannel) -> PlayerSession:
    voice_client = voice_channel.guild.voice_client
    if voice_client is None:
        voice_client = await voice_channel.connect(cls=PlayerSession)
    elif not isinstance(voice_client, PlayerSession):
        # await voice_client.disconnect(force=True)
        voice_client = await voice_channel.connect(cls=PlayerSession)
    else:
        assert isinstance(voice_client, PlayerSession)
        if voice_channel != voice_client.channel:
            await voice_client.move_to(voice_channel)
        else: # if same channel silently do nothing
            pass
    return voice_client

# async def ensure_session(interaction: Interaction) -> None:
def is_existing_session():
    async def predicate(interaction: Interaction):
        assert interaction.guild is not None
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            raise NoSession
        return True
    return app_commands.check(predicate)

def is_not_outsider():
    async def predicate(interaction: Interaction):
        assert interaction.guild is not None
        assert isinstance(interaction.user, Member)
        voice_state = interaction.user.voice
        voice_client = interaction.guild.voice_client
        if voice_client is not None:
            if voice_state is None or voice_state.channel != voice_client.channel:
                raise NotInSession
        return True
    return app_commands.check(predicate)

def is_in_voice():
    async def predicate(interaction: Interaction):
        assert isinstance(interaction.user, Member)
        if interaction.user.voice is None:
            raise NotInChannel
        return True
    return app_commands.check(predicate)

class SeekTransformer(Transformer):
    @override
    async def autocomplete(self, interaction: discord.Interaction, value: str, /) -> list[Choice[str]]: # pyright: ignore [reportIncompatibleMethodOverride]
        assert interaction.guild is not None
        voice_client = interaction.guild.voice_client
        logger.debug(f"seek_autocomplete - {value = }")
        if voice_client is None:
            return []
        elif len(value) != 0 and value.isdigit():
            stamp = ms_timestamp(max(0, int(value) * 1000))
            return [Choice(name=stamp, value=value)]
        elif len(value) != 0:
            # logger.debug(f"seek_autocomplete - {len(value) = }")
            return []
        session = cast(PlayerSession, voice_client)
        now = session.position
        # return [Choice(name="test", value="test")]

        # : list[Choice[int]] 
        choices = []
        for i in reversed(range(-10, 10+1, 5)):
            stamp = ms_timestamp(max(0, now+i*1000))
            logger.debug(f"seek_autocomplete - {stamp = }")
            choice = Choice(name=f"{stamp} ({i:+})", value=str(now // 1000 + i))
            choices += [choice]
        logger.debug(f"seek_autocomplete - {choices = }")
        return choices

    @override
    async def transform(self, interaction: Interaction, value: int | str) -> int: # pyright: ignore [reportIncompatibleMethodOverride]
        assert interaction.guild is not None
        voice_client = interaction.guild.voice_client
        logger.debug(f"seek_transform - {value = }")
        if not voice_client: 
            raise NoSession

        if isinstance(value, int) or value.isdigit():
            seek_seconds = int(value)
            if seek_seconds < 0:
                raise errors.CustomCheck(f"Invalid Timestamp: {value}") 
        else:
            pattern = r"(?:(\d+):)?([0-5]?\d):([0-5]?\d)"
            capture = re.match(pattern, value)
            logger.debug(f"seek_transform - {capture = }")
            if not capture:
                raise errors.CustomCheck(f"Invalid Timestamp: {value}")
            groups = capture.groups()
            hours = int(groups[0]) if groups[0] else 0
            minutes = int(groups[1])
            seconds = int(groups[2])
            seek_seconds = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds).seconds
        return seek_seconds

class MusicCog(GroupCog, group_name="m"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman

    @override
    async def cog_load(self):
        await self.bot.dbman.setup(table_group=__package__,
                                   drop_tables=self.bot.config.drop_tables,
                                   drop_triggers=self.bot.config.drop_triggers,
                                   ignore_schema_updates=self.bot.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.bot.config.ignore_trigger_updates)
        
        node = wavelink.Node(**self.bot.config.lavalink, client=self.bot) # pyright:ignore
        await wavelink.Pool.connect(nodes=[node])

    @override
    async def cog_unload(self):
        for guild in self.bot.guilds:
            if vc:=guild.voice_client:
                await vc.disconnect(force=False)

    def conn(self) -> ConnectionContext:
        return self.bot.dbman.conn()

    async def send_session_confirmation(self, interaction: Interaction, epoch_seconds: int, count: int) -> bool:
        """
        time: epoch seconds converted to discord timestamp
        """
        content = f"A previous session of {count} tracks ended early on <t:{epoch_seconds}:D>, would you like to resume the session?"
        return await Confirmation.send(interaction, content)

    # async def session_queue_tracks(self, session: PlayerSession, tracks: list[Playable]) -> None:
    #     async with self.conn() as db:
    #         pass

    # async def session_pop_track(self, session: PlayerSession, index: int) -> Playable | None:
    #     assert session.queue.history # because the history could be None since history is a queue but doesn't have a history of it's own
    #     assert session.guild
    #     history_count = len(session.queue.history)
    #     queue_count = len(session.queue)
    #     current_index = history_count - 1
    #     pop_index = current_index + index

    #     async with self.conn() as db:
    #         details = await TrackListDetails.selectPriorSession(db, session.guild.id)
    #         if not details:
    #             return
    #         details.start_index += int(max(0, copysign(1, pop_index)))
    #         await TrackList.deleteWhere(db, details.guild_id, details.name, pop_index)
    #         await details.insert(db)
    #         await db.commit()
    
    # async def session_new_tracklist(self, session: PlayerSession) -> None:
    #     logger.debug("session_new_tracklist - pre assert")
    #     logger.debug(f"session_new_tracklist - {session}")
    #     assert session.queue.history # because the history could be None since history is a queue but doesn't have a history of it's own
    #     assert session.guild
    #     logger.debug("session_new_tracklist - post assert")

    #     tracks = list(session.queue.history) + list(session.queue)
    #     logger.debug(f"session_new_tracklist - session track count: {len(tracks)}")
    #     current_index = l-1 if (l:=len(session.queue.history)) > 0 else 0
    #     logger.debug(f"session_new_tracklist - current index: {current_index}")
    #     name = str(int(time.time()))
    #     list_details = TrackListDetails(session.guild.id, name, start_index=current_index, flags=TrackListFlags.session)
    #     logger.debug(f"session_new_tracklist - track list details: {list_details}")

    #     async with self.conn() as db:
    #         logger.debug(f"session_new_tracklist - begin insert")
    #         await list_details.insert(db)
    #         await TrackList.insert_wavelink_tracks(db, tracks, guild_id=session.guild.id, name=name)
    #         await db.commit()
    #         logger.debug(f"session_new_tracklist - committed changes")

    # async def session_change_index(self, session: PlayerSession, delta: int=1) -> None:
    #     pass

    async def attempt_session_requeue(self, interaction: Interaction, session: PlayerSession) -> int:
        """
        If the name wasn't clear, this attempts to find a previous session and requeue it's tracks if it exists
        This method will not start playing if the player is paused
        """
        return 0 # temporarilly disable to get the update out with various fixes
        assert session.guild 
        assert session.queue.history is not None
        async with self.conn() as db:
            details = await TrackListDetails.selectPriorSession(db, session.guild.id)
            # logger.debug(f"attempt_session_resume - details:{details}") # debug-dev
            if not details: 
                return 0
            track_count = await TrackList.selectTrackCountWhere(db, session.guild.id, name=details.name)
            if track_count > 0 and await self.send_session_confirmation(interaction, int(details.name), track_count): 
                # logger.debug(f"attempt_session_resume - confirmation yes") # debug-dev
                playable_tracks = await TrackList.selectAllWavelink(db, wavelink.Pool.get_node(), guild_id=session.guild.id, name=details.name)
                # logger.debug(f"attempt_session_resume - playable tracks : {len(playable_tracks)}") # debug-dev
                session.queue.history._items = playable_tracks[:details.start_index] if len(playable_tracks) > 0 else []
                session.queue._items = playable_tracks[details.start_index:] if (len(playable_tracks) - 1) > details.start_index else []
                return track_count
                # logger.debug(f"attempt_session_resume - first track: {track}") # debug-dev
            else:
                return 0

    @app_commands.command(name="join", description="Starts a music session in the voice channel")
    @is_not_outsider()
    # @app_commands.guild_only()
    async def join(self, interaction: Interaction, channel: VoiceChannel | None=None) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        user = cast(Member, interaction.user)
        session = guild.voice_client
        voice_state = user.voice
        is_new_sesssion = not guild.voice_client

        if channel is not None:
            session = await joinChannel(channel)
        elif voice_state is not None:
            assert voice_state.channel is not None
            session = await joinChannel(voice_state.channel)
        else:
            raise errors.CustomCheck("Join or specify a channel to start a session")
        assert session.queue.history is not None
        
        if is_new_sesssion:
            logger.debug("m join : new session")
            track_count = await self.attempt_session_requeue(interaction, session)
            if track_count > 0:
                await respond(interaction, f"Resumed the old session", delete_after=5, send_followup=True, ephemeral=True)
        await respond(interaction, f"let the playa be playin in {session.channel}", delete_after=5)

    @app_commands.command(name="leave", description="Ends the current session")
    @is_existing_session()
    @is_not_outsider()
    async def leave(self, interaction: Interaction) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        await session.disconnect()
        await respond(interaction, "the playa done playin", delete_after=5)

    @app_commands.command(name="play", description="Queue a track to be played in the voice channel")
    @app_commands.describe(query="search query / song link / playlist link")
    @is_not_outsider()
    @is_in_voice()
    async def play(self, interaction: Interaction, query: str | None=None) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        user = cast(Member, interaction.user)
        assert user.voice and user.voice.channel
        session = guild.voice_client

        resumed = False
        if not session:
            session = await joinChannel(user.voice.channel)
            assert session.queue.history is not None
            track_count = await self.attempt_session_requeue(interaction, session)
            if track_count > 0:
                await respond(interaction, f"Requeued {track_count} tracks from the old session", ephemeral=True, send_followup=True, delete_after=5)
                await session.play_next()
        # logger.debug(f"play - post resumption") # debug-dev

        session = cast(PlayerSession, session)
        if query is None:
            await session.pause(False)
            await respond(interaction, "let the playa be playin", delete_after=5)
            return

        assert query is not None
        results = await session.search_and_queue(query)
        # logger.debug(f"play - {len(results)=}") # debug-dev
        if len(results) == 1: # only a single track was returned
            if session.current is not None:
                await respond(interaction, f"Added {results[0]} to the queue", 
                              delete_after=5)
            else:
                await session.play_next()
                await respond(interaction, f"Now playing {session.current}", 
                              delete_after=5)
        elif len(results) > 1: # many tracks returned
            message = await respond(interaction, content="...", send_followup=True, ephemeral=True)
            guild = cast(discord.Guild, interaction.guild)
            session = cast(PlayerSession, guild.voice_client)
            user = cast(Member, interaction.user)
            scroller = Scroller(message, user, get_tracklist_callback(results, title=f"Queued {len(results)} tracks"), timeout=30)
            await scroller.update(interaction)
            if session.current is None:
                await session.play_next()
        else: # no tracks returned
            await respond(interaction, "I couldn't find any tracks that matched",
                          delete_after=5)
        await session.update_status_bar()

    @app_commands.command(name="pause", description="Pauses the player")
    @is_existing_session()
    @is_not_outsider()
    async def pause(self, interaction: Interaction) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        await session.pause(not session.paused)
        if session.paused:
            await respond(interaction, f"temporary stopage of the playa's playin", delete_after=5)
        else:
            await respond(interaction, f"let the playa be playin", delete_after=5)
        await session.update_status_bar()


    @app_commands.command(name="skip", description="Skip to the next track in the queue")
    @is_existing_session()
    @is_not_outsider()
    async def skip(self, interaction: Interaction, count: int=1) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        current_title = session.current.title if session.current else "Nothing"
        new_index = await session.skipto(count)
        new_title = session.current.title if session.current else "Nothing"

        assert session.queue.history is not None
        previous_state = session.paused
        await session.pause(True)
        if new_index == 1:
            await respond(interaction, f"Skipped `{current_title}`", delete_after=5)
        elif new_index == 0 and not session.queue.history.is_empty:
            await respond(interaction, f"Restarting `{current_title}`", delete_after=5)
        else:
            await respond(interaction, f"Skipped {new_index} tracks to `{new_title}`", delete_after=5)
        await session.pause(previous_state)


    @app_commands.command(name="back", description="Skip to the previous track in the queue")
    @is_existing_session()
    @is_not_outsider()
    async def back(self, interaction: Interaction, count: int=1) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        current_title = session.current.title if session.current else "Nothing"
        new_index = await session.skipto(count*-1)
        new_title = session.current.title if session.current else "Nothing"

        previous_state = session.paused
        await session.pause(True)
        if new_index == -1:
            await respond(interaction, f"Skipped back to `{new_title}`", delete_after=5)
        elif new_index == 0: # new_index == -1:
            await respond(interaction, f"Restarting `{current_title}`", delete_after=5)
        else:
            await respond(interaction, f"Skipped back {-1 * new_index} tracks to `{new_title}`", delete_after=5)
        await session.pause(previous_state)

    @app_commands.command(name="pop", description="Removes a track from the queue or history")
    @app_commands.describe(extent="Removes all tracks inclusively between both points")
    @is_existing_session()
    @is_not_outsider()
    async def pop(self, interaction: Interaction, index: int, extent: int | None=None) -> None:
        await respond(interaction, ephemeral=True)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        assert session.queue.history is not None, "impossible"

        def clamp_index(value: int) -> int:
            assert session.queue.history is not None
            if value > 0:
                new = min(value, len(session.queue))
            else:
                new = max(value, -len(session.queue.history) + 1)
            # shifted left because index=1 corresponds to the real index of 0 in the queue
            # alongside this, the last element of the history (right side) is at position -1
            return new - 1 


        index = clamp_index(index)
        extent = clamp_index(extent) if extent else index
        
        left, right = min(index, extent), max(index, extent)

        # +1 gets added to right to include the element at that position 
        if left >= 0: # implies right > 0, b/c right > left
            del session.queue[left:right+1]
            if right == left:
                content = f"Removed track `{left+1}` from the queue"
            else:
                # {'s' if right-left > 0 else ''}
                content = f"Removed {right-left+1} tracks from the queue"
        elif left < 0 and right >= 0:
            hc = len(session.queue.history[left:])
            del session.queue.history[left:]
            qc = len(session.queue[:right+1])
            del session.queue[:right+1]
            content = f"Removed {hc} track{'s' if hc > 1 else ''} from the history\nand {qc} track{'s' if qc > 1 else ''} from the queue"
        elif right <= 0: # implies left < 0, b/c left < right
            if right + 1 >= 0: # because slice(-x, 0) is []
                del session.queue.history[left:]
            else:
                del session.queue.history[left:right+1]
            if right == left:
                content = f"Removed track `{left+1}` from the history"
            else:
                content = f"Removed {right-left+1} tracks from the history"
        else:
            content = "something impossible happned"
        await respond(interaction, content)

    @app_commands.command(name="seek", description="seeks to the time in the track")
    @app_commands.describe(time="A number of seconds or a timestamp in HH:MM:SS")
    @is_existing_session()
    @is_not_outsider()
    async def seek(self, interaction: Interaction, time: Transform[int, SeekTransformer]) -> None:
        await respond(interaction, ephemeral=True)
        assert interaction.guild is not None
        voice_client = interaction.guild.voice_client
        session = cast(PlayerSession, voice_client)
        await session.seek(time * 1000)
        await respond(interaction, f"Seeked to {ms_timestamp(time*1000)}")

    @app_commands.command(name="loop", description="Sets the loop mode of the queue")
    @is_existing_session()
    @is_not_outsider()
    async def loop(self, interaction: Interaction, mode: wavelink.QueueMode | None=None) -> None:
        await respond(interaction, ephemeral=True)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        if mode is None:
            session.cycle_queue_mode()
        else:
            session.queue.mode = mode
        await respond(interaction, f"Queue Mode: {session.queue.mode}", delete_after=5)
        await session.update_status_bar()

    async def view_callback(self, interaction: Interaction, state: ScrollerState) -> tuple[str, int, int]:
        # TODO Consider restructuring to use an embed to display information
        # Also consider a custom button to offset the titles if they're too long to see the full title 
        ITEM_COUNT = 10
        offset = state.initial_offset + state.relative_offset
        guild = cast(discord.Guild, interaction.guild)
        voice_client = guild.voice_client
        if voice_client is None:
            return """```swift\nThe voice session has ended.\n```""", 0, 0
        session = cast(PlayerSession, guild.voice_client)
        assert session.queue.history is not None
        queue_tracks = session.queue._items # pyright:ignore
        if (not session.queue.history.is_empty) and (session.current == session.queue.history[-1]): # ensures that you only will see history
            history_tracks = session.queue.history._items[:-1]
            magic_history_offset = 0
        else:
            history_tracks = session.queue.history._items # pyright:ignore
            magic_history_offset = 1
        queue_length = len(queue_tracks)
        history_length = len(history_tracks)

        first_page_index = -1 * ((history_length + 4) // ITEM_COUNT)
        last_page_index = (queue_length + 4) // ITEM_COUNT
        
        offset = max(min(offset, last_page_index), first_page_index)
        
        # column widths
        W_INDEX, W_TITLE, W_DURATION = 7, 40, 8


        def track_repr(track: Playable):
            return f"{acstr(track.title, W_TITLE)} - {acstr(ms_timestamp(track.length), W_DURATION, just="r")}"

        def track_repr_index(track: Playable, index: int):
            return f"{acstr(index, W_INDEX, edges=("( ", ")"))} {acstr(track.title, W_TITLE)} - {acstr(ms_timestamp(track.length), W_DURATION, just="r")}"

        currently_playing = session.current
        if currently_playing is not None:
            status = "Playing" if session.playing and not session.paused else ("Paused" if session.paused else "Stopped")
            # ➤
            currently_playing_rep = f"{acstr(status, W_INDEX)} {track_repr(currently_playing)}"
        else:
            currently_playing_rep = f"Nothing is currently playing"

        reps: list[str] = []
        if offset == 0:
            # Show 5 history tracks, 5 queue tracks and now playing in the middle
            # Because this page contains the first 5 tracks of both the history and the queue
            # the history and queue pages must be shift by 5 to account for it
            history_slice = history_tracks[-5:]
            for i, track in enumerate(history_slice):
                index = len(history_slice) * -1 + i + magic_history_offset
                temp = track_repr_index(track, index)
                reps.append(temp)
            reps.append("-------")
            reps.append(currently_playing_rep)
            reps.append("-------")
            queue_slice = queue_tracks[:5]
            for i, track in enumerate(queue_slice):
                index = i + 1
                temp = track_repr_index(track, index)
                reps.append(temp)
        elif offset < 0:
            # 10 history tracks, now playing at the bottom
            # Offset will be <= -1
            first, last = (offset * ITEM_COUNT - 5), (offset * ITEM_COUNT + 5)
            history_slice = history_tracks[first:last]
            for i, track in enumerate(history_slice):
                index = len(history_slice) * -1 + i + last + magic_history_offset
                temp = track_repr_index(track, index)
                reps.append(temp)
            reps.append("-------")
            reps.append(currently_playing_rep)
        else:
            # 10 queue tracks, now playing at the top
            reps.append(currently_playing_rep)
            reps.append("-------")
            # Offset will be >=1 
            first, last = (offset * ITEM_COUNT - 5), (offset * ITEM_COUNT + 5)
            queue_slice = queue_tracks[first:last]
            for i, track in enumerate(queue_slice):
                index = i + 1 + first
                temp = track_repr_index(track, index)
                reps.append(temp)

        body = '\n'.join(reps)
        header = f"{acstr('Index', W_INDEX)} {acstr('Title', W_TITLE)} - {acstr('Length', W_DURATION, just="r")}"
        content = f"```swift\n{header}\n-------\n{body}\n-------\nPage # ({first_page_index} : {offset} : {last_page_index})\n```"
        # is_last = (tag_count - offset * ITEM_COUNT) < ITEM_COUNT
        return content, first_page_index, last_page_index

    @app_commands.command(name="queue", description="View all the tracks in the queue")
    @is_existing_session()
    @is_not_outsider()
    async def view_queue(self, interaction: Interaction) -> None:
        message = await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        user = cast(Member, interaction.user)

        scroller = Scroller(message, user, self.view_callback)
        await scroller.update(interaction)

    @app_commands.command(name="nowplaying", description="An editable now playing message that dynamically changes")
    @is_existing_session()
    @is_not_outsider()
    async def nowplaying(self, interaction: Interaction, style: Literal["minimal", "remote", "mini-queue"]):
        await respond(interaction, ephemeral=True)
        assert interaction.channel is not None
        channel = cast(MessageableGuildChannel, interaction.channel)
        assert interaction.guild is not None
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            raise NoSession
        session = cast(PlayerSession, voice_client)
        if session.status_bar is None:
            status_bar = StatusBar(channel=channel, style=style)
            await status_bar.resend()
            session.status_bar = status_bar
            await respond(interaction, "`Sent the status bar`", delete_after=3)
        else:
            if style != session.status_bar.style:
                await session.status_bar.kill()
                session.status_bar = StatusBar(channel=channel, style=style)
                await session.status_bar.resend()
                await respond(interaction, "`Updated the status bar style`", delete_after=3)
            else:
                await session.status_bar.kill()
                session.status_bar = None
                await respond(interaction, "`Disabled the status bar`", delete_after=3)

    async def volume_autocomplete(self, interaction: Interaction, current: str) -> list[Choice[int]]:
        assert interaction.guild is not None
        voice_client = interaction.guild.voice_client
        if voice_client:
            session = cast(PlayerSession, voice_client)
            return [
                Choice(name=f"{session.volume+10}%", value=session.volume),
                Choice(name=f"{session.volume}% ⬅️ Current", value=session.volume),
                Choice(name=f"{session.volume-10}%", value=session.volume)
            ]
        else:
            return []

    @app_commands.command(name="volume", description="Adjusts the volume of the player for everyone in the call")
    @app_commands.autocomplete(volume=volume_autocomplete)
    @is_existing_session()
    @is_not_outsider()
    async def volume(self, interaction: Interaction, volume: int | None=None) -> None:
        await respond(interaction, ephemeral=True)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        if volume is None:
            await respond(interaction, f"Session Volume: {session.volume}")
        else:
            old_volume = session.volume
            session.set_volume(volume)
            await respond(interaction, f"Session Volume: {old_volume} -> {session.volume}")

    @GroupCog.listener()
    async def on_wavelink_websocket_closed(self, payload: WebsocketClosedEventPayload) -> None:
        logger.debug(f"wavelink_websocket_closed - enter")
        session = cast(PlayerSession, payload.player)
        logger.debug(f"wavelink_websocket_closed - cast session")
        logger.debug(f"wavelink_websocket_closed - {session}")
        # await self.session_new_tracklist(session)
        await session.save_queue()


    @GroupCog.listener()
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload) -> None:
        session = cast(PlayerSession, payload.player)
        if session.status_bar:
            await session.status_bar.refresh()


    @GroupCog.listener()
    async def on_wavelink_track_end(self, payload: TrackEndEventPayload) -> None:
        pass
        # session = cast(PlayerSession, payload.player)
        # if session.status_bar:
        #     await session.status_bar.refresh()

    async def handle_bot_voice_state_update(self, before: VoiceState, after: VoiceState) -> None:
        if before.channel and not after.channel:
            logger.debug("voice_state_update - Bot left a channel")
            guild_id = before.channel.guild.id
            session = cast(PlayerSession, before.channel.guild.voice_client)
            if not session:
                logger.debug("voice_state_update - No session, ignoring")
                return

            assert session.queue.history
            tracks = list(session.queue.history) + list(session.queue)
            logger.debug(f"voice_state_update - session track count: {len(tracks)}")
            current_index = l-1 if (l:=len(session.queue.history)) > 0 else 0
            logger.debug(f"voice_state_update - current index: {current_index}")
            epoch_seconds = int(time.time())
            name = f"{epoch_seconds}"
            list_details = TrackListDetails(guild_id, name, start_index=current_index, flags=TrackListFlags.session)
            logger.debug(f"voice_state_update - track list details: {list_details}")

            async with self.conn() as db:
                logger.debug(f"voice_state_update - begin insert")
                await list_details.insert(db)
                await TrackList.insert_wavelink_tracks(db, tracks, guild_id=guild_id, name=name)
                await db.commit()
                logger.debug(f"voice_state_update - committed changes")

    @GroupCog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: VoiceState, after: VoiceState) -> None:
        # leave channel if len(members) == 1 and memeber == bot
        # make bot leave when someone else leaves and now the bot is alone, that's it
        if member == self.bot.user:
            # await self.handle_bot_voice_state_update(before, after)
            return # ignoring self
        assert self.bot.user
        bot_id = self.bot.user.id
        bot_member = member.guild.get_member(bot_id)

        if member.guild.voice_client:
            session = cast(PlayerSession, member.guild.voice_client)
            if before.channel and before.channel != after.channel and session.channel == before.channel:
                if len(before.channel.members) == 1:
                    await session.disconnect()
        else:
            # I'm doing this with member stuff instead of voice clients in case the bot is left in the channel while lavalink has an issue
            if before.channel and before.channel != after.channel:
                if len(before.channel.members) == 2 and bot_member in before.channel.members:
                    await bot_member.move_to(None)

    # @GroupCog.listener()
    async def on_message(self, message: discord.Message) -> None:
        return # For right now this isn't needed, persistant messages like this are kinda shitty and bad
        if message.guild is None: # event ignored if in dm
            return

        if message.guild.voice_client:
            session: PlayerSession = cast(PlayerSession, message.guild.voice_client)
            if session.status_bar is not None and session.status_bar.message != message:
                print("================")
                print(session.status_bar.message)
                print(message)
                await session.status_bar.resend()

class Confirmation(ui.View):
    def __init__(self, timeout: float=60, message: discord.Message | None=None):
        """
        message: the discord message the view is attached to, when passed will be deleted on timeout
        """
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = message
        self.value: bool = False

    @classmethod
    async def send(cls, interaction: Interaction, content: str) -> bool:
        assert interaction.guild_id is not None
        confirmation_view = Confirmation()
        message = await respond(interaction, view=confirmation_view, 
                                content=content, send_followup=True, ephemeral=True)
        confirmation_view.message = message
        await confirmation_view.wait()
        return confirmation_view.value

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.delete()
            except MessageNotFound as e:
                logger.debug(f"Confirmation View on_timeout - {e}")
    
    async def done(self) -> None:
        await self.on_timeout()
        self.stop()
    
    @ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, interaction: Interaction, button: ui.Button["Confirmation"]) -> None:
        await respond(interaction)
        self.value = True
        await self.done()

    @ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction: Interaction, button: ui.Button["Confirmation"]) -> None:
        await respond(interaction)
        self.value = False
        await self.done()


