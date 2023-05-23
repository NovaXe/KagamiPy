import asyncio
import datetime
import re
from typing import (
    Literal,
    Dict,
    Union,
    Optional,
    List,
)
import discord
import discord.utils
import wavelink
from discord.ext import commands
from discord import app_commands, VoiceChannel, StageChannel
from discord.ext import tasks
from wavelink import YouTubeTrack
from collections import deque
import atexit
from bot.utils.ui import MessageScroller
from bot.utils.ui import QueueController
from bot.utils.utils import seconds_to_time
from bot.utils.bot_data import Server
from bot.utils.music_helpers import *
from bot.utils.utils import find_closely_matching_dict_keys


class Soundboard(commands.GroupCog, group_name="soundboard"):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config



    async def join_voice_channel(self, interaction: discord.Interaction, guild: discord.Guild=None, voice_channel: discord.VoiceChannel=None, keep_existing_player=False):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        voice_client: Player = interaction.guild.voice_client
        if guild:
            voice_client: Player = guild.voice_client

        channel_to_join: discord.VoiceChannel = interaction.user.voice.channel
        if voice_channel:
            channel_to_join = voice_channel

        player = None
        if voice_client is not None:
            if keep_existing_player:
                player = voice_client
            else:
                player = Player(dj_user=interaction.user, dj_channel=interaction.channel)
        else:
            player = Player(dj_user=interaction.user, dj_channel=interaction.channel)

        voice_client = await channel_to_join.connect(cls=player)
        server.has_player = True
        # server.player = voice_client
        return voice_client

    async def attempt_to_join_vc(self, interaction: discord.Interaction, voice_channel=None, should_switch_channel=False):
        voice_client = interaction.guild.voice_client

        if voice_client:
            if should_switch_channel:
                voice_client = await self.join_voice_channel(interaction, voice_channel=voice_channel, keep_existing_player=False)
        else:
            voice_client = await self.join_voice_channel(interaction, voice_channel=voice_channel, keep_existing_player=False)

        return voice_client

    async def soundboard_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        server: Server = self.bot.fetch_server(interaction.guild_id)
        return [
            app_commands.Choice(name=sound_name, value=sound_name)
            for sound_name, sound_id in server.soundboard.items() if current.lower() in sound_name.lower()
        ][:25]

    @app_commands.autocomplete(sound_name=soundboard_autocomplete)
    @app_commands.command(name="play", description="plays the given sound")
    async def play(self, interaction: discord.Interaction, sound_name: str):
        await interaction.response.defer(thinking=True)
        current_player: Player = interaction.guild.voice_client
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if sound_name not in server.soundboard.keys():
            close_match = list(find_closely_matching_dict_keys(search=sound_name, tags=server.soundboard, n=1).keys())[0]
            if not close_match:
                await interaction.edit_original_response(content=f"The sound `{sound_name}` does not exist")
                return
            else:
                sound_name = close_match




        current_player: Player = await self.attempt_to_join_vc(interaction=interaction, should_switch_channel=False)
        await interaction.edit_original_response(content=f"{interaction.user.name} played {sound_name}")

        track = await wavelink.NodePool.get_node().build_track(identifier=server.soundboard[sound_name], cls=wavelink.Track)
        track.title = sound_name
        await current_player.interrupt_current_track(track)


    @app_commands.command(name="stop", description="stops the current sound")
    async def stop(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        current_player: Player = interaction.guild.voice_client
        if not current_player:
            await interaction.edit_original_response(content="I'm not in a channel")
            return

        if not current_player.interrupted_by_sound:
            await interaction.edit_original_response(content="I'm not playing a sound")

        await current_player.resume_interrupted_track()


    @app_commands.command(name="add", description="adds a sound to the soundboard")
    async def add_sound(self, interaction: discord.Interaction, sound_name: str, sound_search: str):
        await interaction.response.defer(thinking=True)
        track: wavelink.Track = await search_song(sound_search, single_track=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)

        if sound_name in server.soundboard.keys():
            await interaction.edit_original_response(content="A sound with that name already exists")
            return

        server.soundboard[sound_name] = track.id
        await interaction.edit_original_response(content=f"Added {sound_name} to the soundboard")

    @app_commands.autocomplete(sound_name=soundboard_autocomplete)
    @app_commands.command(name="remove", description="removes a sound from the soundboard")
    async def remove_sound(self, interaction: discord.Interaction, sound_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        server.soundboard.pop(sound_name)
        await interaction.edit_original_response(content=f"Removed {sound_name} from the soundboard")


    @app_commands.command(name="list", description="lists all sounds")
    async def list_sounds(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)

        sound_names = list(server.soundboard.keys())
        soundboard_length = len(sound_names)
        page_data = [(int(i / 10), sound_names[i:i + 10]) for i in range(0, soundboard_length, 10)]
        pages = []
        for page_index, page_list in page_data:
            content = "```swift\n"
            content += f"{interaction.guild.name} Soundboard has {soundboard_length} sound{'s' if soundboard_length>1 else ''}\n"
            content += "──────────────────────────\n"
            for sound_index, sound_name in enumerate(page_list):
                number = str(sound_index+1 + page_index * 10) + ")"
                content += f"{number.ljust(5)} {sound_name}\n"

            content += f"Page #: {page_index+1} / {math.ceil(soundboard_length/10)}\n```"
            pages.insert(page_index, content)

        if len(pages) == 0:
            await interaction.edit_original_response(content="```swift\nThe soundboard is empty```")
            return

        message = await interaction.edit_original_response(content=pages[0])

        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(view=view)


async def setup(bot):
    soundboard_cog = Soundboard(bot)
    await bot.add_cog(soundboard_cog)
