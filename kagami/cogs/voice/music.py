from dataclasses import dataclass
from enum import IntEnum
from inspect import getcallargs
from typing import (
    Literal, List, Callable, Any, cast, get_args
)
import datetime
import math
from math import ceil, floor
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
from discord.ext.commands import GroupCog, Cog
from discord.app_commands import Transform, Transformer, Group, Choice, Range
import wavelink
from wavelink import Playable, Search, TrackEndEventPayload, TrackStartEventPayload

from bot import Kagami
from common import errors
from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, PersistentSettings
from common.paginator import Scroller, ScrollerState
from common.types import MessageableGuildChannel
from .voice import PlayerSession, StatusBar, NotInChannel, NotInSession, NoSession, get_tracklist_callback
from utils.depr_db_interface import Database
from common.utils import acstr, ms_timestamp


type VocalGuildChannel = VoiceChannel | discord.StageChannel
type Interaction = discord.Interaction[Kagami]

async def joinChannel(voice_channel: VocalGuildChannel) -> PlayerSession:
    voice_client = voice_channel.guild.voice_client
    if voice_client is None:
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

class MusicCog(GroupCog, group_name="m"): 
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman

    async def cog_load(self):
        await self.bot.dbman.setup(table_group=__name__,
                                   drop_tables=self.bot.config.drop_tables,
                                   drop_triggers=self.bot.config.drop_triggers,
                                   ignore_schema_updates=self.bot.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.bot.config.ignore_trigger_updates)
        
        node = wavelink.Node(**self.bot.config.lavalink, client=self.bot) # pyright:ignore
        await wavelink.Pool.connect(nodes=[node])

    @app_commands.command(name="join", description="Starts a music session in the voice channel")
    @is_not_outsider()
    # @app_commands.guild_only()
    async def join(self, interaction: Interaction, channel: VoiceChannel | None=None) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        user = cast(Member, interaction.user)
        session = guild.voice_client
        voice_state = user.voice

        if channel is not None:
            session = await joinChannel(channel)
        elif voice_state is not None:
            assert voice_state.channel is not None
            session = await joinChannel(voice_state.channel)
        else:
            raise errors.CustomCheck("Join or specify a channel to start a session")

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
        if not session:
            session = await joinChannel(user.voice.channel)
            await respond(interaction, "let the playa be playin", delete_after=5)
            if query is None:
                return
        session = cast(PlayerSession, session)
        if query is None:
            await session.pause(False)
            await respond(interaction, "let the playa beforth playin", delete_after=5)
            return
        assert query is not None
        results = await session.search_and_queue(query)
        if len(results) == 1:
            if session.current is None:
                track = await session.queue.get_wait()
                await session.play(track)
                await respond(interaction, f"Now playing {track.title}", 
                              send_followup=True, delete_after=5)
            else:
                await respond(interaction, f"Added {results[0]} to the queue", 
                              send_followup=True, delete_after=5)
        elif len(results) > 1:
            message = await respond(interaction, send_followup=True)
            guild = cast(discord.Guild, interaction.guild)
            session = cast(PlayerSession, guild.voice_client)
            user = cast(Member, interaction.user)

            scroller = Scroller(message, user, get_tracklist_callback(results))
            if session.current is None:
                track = await session.queue.get_wait()
            await scroller.update(interaction)
        else:
            await respond(interaction, "I couldn't find any tracks that matched",
                          send_followup=True, delete_after=5)
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

        previous_state = session.paused
        await session.pause(True)
        if new_index == 1:
            await respond(interaction, f"Skipped `{current_title}`", delete_after=5)
        elif new_index == 0: # or new_index == -1
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
        history_tracks = session.queue.history._items # pyright:ignore
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
                index = len(history_slice) * -1 + i + 1
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
                index = len(history_slice) * -1 + i + last + 1
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
            return [Choice(name=str(session.volume), value=session.volume)]
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

    @GroupCog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: VoiceState, after: VoiceState) -> None:
        # leave channel if len(members) == 1 and memeber == bot
        # make bot leave when someone else leaves and now the bot is alone, that's it
        if member == self.bot.user:
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

