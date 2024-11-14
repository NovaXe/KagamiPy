from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Literal, List, Callable, Any
)
import PIL as pillow
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiosqlite
import discord
from discord.ext import commands, tasks
from discord import VoiceClient, VoiceState, app_commands, Interaction, Member, VoiceChannel
from discord.ext.commands import GroupCog
from discord.app_commands import Transform, Transformer, Group, Choice, Range
import wavelink
from wavelink.player import VocalGuildChannel

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

type VocalGuildChannel = VoiceChannel | discord.StageChannel

async def joinChannel(voice_channel: VocalGuildChannel) -> PlayerSession:
    voice_client = voice_channel.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect(cls=PlayerSession)
    else:
        assert isinstance(voice_client, PlayerSession)
        await voice_client.move_to(voice_channel)
    return voice_client


def requireVoiceclient(begin_session=False, defer_response=True, ephemeral=False):
    async def predicate(interaction: Interaction):
        if defer_response: await respond(interaction, ephemeral=ephemeral)
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            if begin_session:
                await attemptToJoin(interaction, send_response=False, ephemeral=ephemeral)
                return True
            else:
                raise errors.NoVoiceClient
        else:
            return True

    return app_commands.check(predicate)

def requireVoiceSession(start_session: bool=False, defer_response: bool=True, ephemeral_response: bool=False)
    async def predicate(interaction: Interaction):
        if defer_response:
            await respond(interaction, ephemeral=ephemeral_response)
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            if start_session:
                await 

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
        else
            await new_channel.connect(cls=PlayerSession, self_deaf=True)
        await respond(interaction, f"Started a new session in {new_channel.name}", delete_after=5)
        
    @app_commands.command(name="leave", description="Ends the current session")
    async def leave(self, interaction: Interaction) -> None:
        await respond(interaction)


    @app_commands.command(name="play", description="Queue a track to be played in the voice channel")
    @app_commands.describe(track="search query / song link / playlist link")
    async def play(self, interaction: Interaction, track: str) -> None:



    @app_commands.command(name="skip", description="Skip to the next track in the queue")
    async def skip(self, interaction: Interaction, count: int=1) -> None:
        raise NotImplementedError

    @app_commands.command(name="back", description="Skip to the previous track in the queue")
    async def back(self, interaction: Interaction, count: int=1) -> None:
        raise NotImplementedError

    @app_commands.command(name="view-queue", description="View all the tracks in the queue")
    async def view_queue(self, interaction: Interaction) -> None:
        raise NotImplementedError

    @app_commands.command(name="view-history", description="View all track in the history")
    async def view_history(self, interaction: Interaction) -> None:
        raise NotImplementedError




async def setup(bot: Kagami):
    bot.add_cog(MusicCog(bot))

