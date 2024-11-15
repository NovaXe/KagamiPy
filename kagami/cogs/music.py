from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Literal, List, Callable, Any, cast
)
import PIL as pillow
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiosqlite
import discord
from discord.ext import commands, tasks
from discord import (
    VoiceClient, 
    VoiceState, 
    app_commands, 
    Interaction, 
    Member, 
    VoiceChannel,
)
from discord.ext.commands import GroupCog
from discord.app_commands import Transform, Transformer, Group, Choice, Range
import wavelink
from wavelink import Playable, Search

from bot import Kagami
from common import errors
from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, PersistentSettings
from common.paginator import Scroller, ScrollerState
from common.voice import PlayerSession
from utils.depr_db_interface import Database
from common.utils import acstr


class NotInChannel(errors.CustomCheck):
    MESSAGE: str = "You must be in a voice channel to use this command"

class NotInSession(errors.CustomCheck):
    MESSAGE: str = "You must part of the voice session to use this"

class NoSession(errors.CustomCheck):
    MESSAGE: str = "A voice session must be active to use this command"

type VocalGuildChannel = VoiceChannel | discord.StageChannel

async def joinChannel(voice_channel: VocalGuildChannel) -> PlayerSession:
    voice_client = voice_channel.guild.voice_client
    if voice_client is None:
        voice_client = await voice_channel.connect(cls=PlayerSession)
    else:
        assert isinstance(voice_client, PlayerSession)
        await voice_client.move_to(voice_channel)
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
        
        node = wavelink.Node(**self.bot.config.lavalink, client=self.bot)
        await wavelink.Pool.connect(nodes=[node])

    @app_commands.command(name="join", description="Starts a music session in the voice channel")
    # @app_commands.guild_only()
    async def join(self, interaction: Interaction[Kagami], channel: VoiceChannel | None=None) -> None:
        _ = await respond(interaction)
        assert isinstance(interaction.user, Member) and interaction.guild is not None
        voice_state: VoiceState | None = interaction.user.voice
        existing_session: PlayerSession | None = interaction.guild.voice_client
        if channel is None:
            if existing_session is not None: 
                raise errors.CustomCheck(f"Sorry, there is already an active voice session")
            elif voice_state is None or voice_state.channel is None:
                raise errors.CustomCheck("Join or specify a channel to start a session")
            else:
                new_channel = voice_state.channel
        else:
            new_channel = channel
        
        if existing_session:
            await existing_session.move_to(new_channel)
        else:
            await new_channel.connect(cls=PlayerSession, self_deaf=True)
        await respond(interaction, f"let the playa be playin in {new_channel.name}", delete_after=5)
        
    @app_commands.command(name="leave", description="Ends the current session")
    @is_existing_session()
    @is_not_outsider()
    async def leave(self, interaction: Interaction) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = guild.voice_client
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
        if query is None:
            session = cast(PlayerSession, session)
            await session.pause(False)
            await respond(interaction, "let the playa beforth playin", delete_after=5)

        results: Search = await Playable.search(query)
        if not results:
            await respond(interaction, "I couldn't find any tracks that matched",
                          send_followup=True, delete_after=5)
        else:
            await session.play(results[0])
            await respond(interaction, f"Added {results[0]} to the queue", 
                          send_followup=True, delete_after=5)
        


    @app_commands.command(name="skip", description="Skip to the next track in the queue")
    @is_existing_session()
    @is_not_outsider()
    async def skip(self, interaction: Interaction, count: int=1) -> None:
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        tracks: list[Playable] = []
        await session.pause(True)
        for i in range(count):
            track = await session.skip()
            if track is None:
                break
            tracks.append(track)
        skipped_count = len(tracks)
        if skipped_count == 1:
            await respond(interaction, f"Skipped {tracks[0]}")
        elif skipped_count > 1:
            await respond(interaction, f"Skiped {skipped_count}")
        else:
            await respond(interaction, f"There are no tracks to skip")
        await session.pause(False)

    @app_commands.command(name="back", description="Skip to the previous track in the queue")
    async def back(self, interaction: Interaction, count: int=1) -> None:
        raise NotImplemented
        await respond(interaction)
        guild = cast(discord.Guild, interaction.guild)
        session = cast(PlayerSession, guild.voice_client)
        tracks: list[Playable] = []
        if len(session.queue.history) > 0:
            pass

        for i in range(count):

            track = await session.queue.history[-1]
            track = await session.skip()
            if track is None:
                break
            tracks.append(track)
        skipped_count = len(tracks)
        if skipped_count == 1:
            await respond(interaction, f"Skipped {tracks[0]}")
        elif skipped_count > 1:
            await respond(interaction, f"Skiped {skipped_count}")
        else:
            await respond(interaction, f"There are no tracks to skip")

    @app_commands.command(name="view-queue", description="View all the tracks in the queue")
    async def view_queue(self, interaction: Interaction) -> None:
        raise NotImplementedError

    @app_commands.command(name="view-history", description="View all track in the history")
    async def view_history(self, interaction: Interaction) -> None:
        raise NotImplementedError




async def setup(bot: Kagami):
    await bot.add_cog(MusicCog(bot))

