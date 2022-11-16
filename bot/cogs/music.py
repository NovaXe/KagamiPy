import asyncio
import re
from typing import List

import discord
import discord.utils
import wavelink
from discord.ext import commands
from discord import app_commands, VoiceChannel, StageChannel
from wavelink import YouTubeTrack

from bot.utils import modals
from wavelink.ext import spotify
from enum import Enum

URL_REG = re.compile(r'https?://(?:www\.)?.+')
YT_URL_REG = re.compile(r"(?:https://)(?:www\.)?(?:youtube|youtu\.be)(?:\.com)?\/(?:watch\?v=)?(.{11})")


class LoopMode(Enum):
    NO_LOOP = 0
    LOOP_SONG = 1
    LOOP_QUEUE = 2


class Player(wavelink.Player):
    def __init__(self, dj_user: discord.Member, dj_channel: discord.TextChannel):
        super().__init__()
        self.queue = wavelink.Queue()
        self.current_track: wavelink.Track = None
        self.loop_mode: LoopMode = LoopMode.NO_LOOP
        self.dj_user: discord.Member = dj_user
        self.dj_channel: discord.TextChannel = dj_channel

    def add_to_queue(self, single: bool, track: wavelink.Track) -> None:
        if single:
            self.queue.put(track)
        else:
            self.queue.extend(track)

    def get_next_song(self) -> wavelink.Track:
        return self.queue.get()

    async def play_next_track(self):
        if self.queue.is_empty:
            self.current_track = None
            return
        self.current_track = self.queue.get()
        await self.play(source=self.current_track, replace=True)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.player = None
        bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(bot=self.bot,
                                            host='127.0.0.1',
                                            port=3333,
                                            password='KagamiLavalink1337')

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f"Node: <{node.identifier}> is ready")

    async def attempt_to_join_channel(self, interaction: discord.Interaction) -> discord.VoiceClient:
        user_voice = interaction.user.voice
        if user_voice is None:
            await interaction.response.send_message("Please join a voice channel", ephemeral=True)
            return None
        channel = user_voice.channel
        voice_client = interaction.guild.voice_client
        if self.player is None:
            self.player = Player(dj_user=interaction.user, dj_channel=interaction.channel)
            if voice_client is None:
                voice_client: Player = await channel.connect(cls=self.player)
            return voice_client
        return voice_client

    @app_commands.command(name="join", description="joins your current voice channel")
    async def join_channel(self, interaction: discord.Interaction) -> None:
        voice_client = await self.attempt_to_join_channel(interaction)
        if voice_client is None:
            return
        await interaction.response.send_message(f"I have joined {interaction.user.voice.channel.name}")

    @app_commands.command(name="leave", description="leaves the channel")
    async def leave_channel(self, interaction: discord.Interaction):
        if self.player is None:
            await interaction.response.send_message("I am not in a voice channel")
        await self.player.disconnect()
        self.player = None
        await interaction.response.send_message("I have left the voice channel")

    @app_commands.command(name="play", description="plays/adds the given song")
    async def play_song(self, interaction: discord.Interaction, search: str) -> None:
        voice_client: Player = await self.attempt_to_join_channel(interaction)

        is_yt_url = bool(YT_URL_REG.search(search))
        if is_yt_url:
            track = await voice_client.node.get_tracks(query=search, cls=wavelink.YouTubeTrack)
            self.player.add_to_queue(single=False, track=track)
        else:
            track = await wavelink.YouTubeTrack.search(query=search, return_first=True)
            self.player.add_to_queue(single=True, track=track)

        if self.player.current_track is None:
            await self.player.play_next_track()

        await interaction.response.send_message("Added song to queue", ephemeral=True)

    @app_commands.command(name="queue", description="shows the track queue")
    async def show_queue(self, interaction: discord.Interaction):
        if self.player is None:
            await interaction.response.send_message("There is currently no voice session")
        currently_playing = self.player.current_track
        queue_as_list = list(reversed([track for track in self.player.queue.copy()]))
        queue_message = "\n".join([f"{len(queue_as_list) - index})   {track.title}"
                                   f"   {int(track.length/60)}:{int(track.length%60)}"
                                   for index, track in enumerate(queue_as_list)])

        if currently_playing is not None:
            queue_message += f"\nNow Playing\n{currently_playing.title}   {int(self.player.position/60)}:{int(self.player.position % 60)}" \
                             f" / {int(currently_playing.length/60)}:{int(currently_playing.length%60)}"
        else:
            queue_message += ">> Nothing is currently Playing"
        await interaction.response.send_message(content=queue_message)

    @app_commands.command(name="skip", description="skips the currently playing song")
    async def skip_song(self, interaction: discord.Interaction):
        await self.player.stop()
        await self.player.play_next_track()
        await interaction.response.send_message("skipped song")

    @app_commands.command(name="clear", description="clears the entire queue")
    async def clear_queue(self, interaction: discord.Interaction):
        queue_size = self.player.queue.count
        await self.player.queue.clear()
        await interaction.response.send_message(f"Cleared {queue_size} tracks from the queue")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: Player, track: wavelink.Track, reason):
        await self.player.play_next_track()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, player: Player, track: wavelink.Track, error):
        await self.player.play_next_track()

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, player: Player, track: wavelink.Track, threshold):
        await self.player.play_next_track()


async def setup(bot):
    await bot.add_cog(Music(bot))
