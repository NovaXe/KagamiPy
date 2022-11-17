import asyncio
import re
from typing import List
from typing import Optional
import discord
import discord.utils
import wavelink
from discord.ext import commands
from discord import app_commands, VoiceChannel, StageChannel
from wavelink import YouTubeTrack
from collections import deque

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
        self.history = wavelink.Queue()
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
        await self.cycle_track()
        await self.start_current_track()
        # if self.queue.is_empty:
        #     self.current_track = None
        #     return
        # if self.current_track is not None:
        #     self.history.put(self.current_track)
        # self.current_track = self.queue.get()
        # await self.play(source=self.current_track, replace=True)

    async def start_current_track(self):
        if self.current_track is None:
            return
        await self.play(source=self.current_track, replace=True)

    async def cycle_track(self, reverse:bool = False):
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


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.player = None
        self.players = {}
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
            await interaction.response.send_message("Please join a voice channel", ephemeral=False)
            return None
        channel = user_voice.channel
        voice_client = interaction.guild.voice_client

        if self.players[interaction.guild_id] is None:
            self.players[interaction.guild_id] = Player(dj_user=interaction.user, dj_channel=interaction.channel)
            if voice_client is None:
                voice_client: Player = await channel.connect(cls=self.players[interaction.guild_id])
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
        if self.players[interaction.guild_id] is None:
            await interaction.response.send_message("I am not in a voice channel")
        await self.players[interaction.guild_id].disconnect()
        self.players.pop(interaction.guild_id)
        await interaction.response.send_message("I have left the voice channel")

    @app_commands.command(name="play", description="plays/adds the given song")
    async def play_song(self, interaction: discord.Interaction, search: str = None) -> None:
        message = ""
        if interaction.guild.voice_client:
            if search is None:
                await self.players[interaction.guild_id].resume()
                await interaction.response.send_message(content="Resumed the player")
                return
        voice_client: Player = await self.attempt_to_join_channel(interaction)
        if search is None:
            await interaction.response.send_message("I have joined the channel", ephemeral=False)
            return

        is_yt_url = bool(YT_URL_REG.search(search))
        if is_yt_url:
            track = await voice_client.node.get_tracks(query=search, cls=wavelink.YouTubeTrack)
            self.players[interaction.guild_id].add_to_queue(single=False, track=track)
        else:
            track = await wavelink.YouTubeTrack.search(query=search, return_first=True)
            self.players[interaction.guild_id].add_to_queue(single=True, track=track)

        await interaction.response.send_message(f"**{track.title}** was added to the queue", ephemeral=False)

        if self.players[interaction.guild_id].current_track is None:
            await self.players[interaction.guild_id].play_next_track()
            # await self.players[interaction.guild_id].cycle_track()
            # await self.players[interaction.guild_id].start_current_track()

    @app_commands.command(name="queue", description="shows the track queue")
    async def show_queue(self, interaction: discord.Interaction):
        if self.players[interaction.guild_id] is None:
            await interaction.response.send_message("There is currently no voice session")
        currently_playing = self.players[interaction.guild_id].current_track
        queue_as_list = list(reversed([track for track in self.players[interaction.guild_id].queue.copy()]))
        queue_message = "\n".join([f"**{len(queue_as_list) - index})**   *{track.title}*"
                                   f"   {int((track.length/60))}:{int(track.length%60):02}"
                                   for index, track in enumerate(queue_as_list)])

        if currently_playing is not None:
            queue_message += f"\nNow Playing\n{currently_playing.title}" \
                             f"   {int(self.players[interaction.guild_id].position / 60)}:{int(self.players[interaction.guild_id].position % 60):02}" \
                             f" / {int(currently_playing.length/60)}:{int(currently_playing.length%60):02}"
        else:
            queue_message += ">> Nothing is currently Playing"
        await interaction.response.send_message(content=queue_message)

    async def toggle_pause(self, interaction: discord.Interaction = None):
        message: str = None
        if self.players[interaction.guild_id].is_paused():
            await self.players[interaction.guild_id].resume()
            message = "Resumed the player"
        else:
            await self.players[interaction.guild_id].pause()
            message = "Paused the player"
        if interaction is None:
            return
        await interaction.response.send_message(content=message, ephemeral=True)

    @app_commands.command(name="pause", description="pauses the player")
    async def pause_song(self, interaction: discord.Interaction):
        await self.toggle_pause(interaction)

    @app_commands.command(name="resume", description="resumes the player")
    async def resume_song(self, interaction: discord.Interaction):
        await self.players[interaction.guild_id].resume()
        await interaction.response.send_message(content="Resumed the player", ephemeral=True)

    @app_commands.command(name="skip", description="skips the currently playing song")
    async def skip_song(self, interaction: discord.Interaction, skip_count: int=1):
        for i in range(skip_count):
            await self.players[interaction.guild_id].cycle_track()
        await self.players[interaction.guild_id].stop()
        await self.players[interaction.guild_id].start_current_track()
        await interaction.response.send_message("skipped song")

    @app_commands.command(name="jumpto", description="jumps to the given spot in the queue")
    async def jump_to(self, interaction: discord.Interaction, index: int):
        for i in range(index+1):
            await self.players[interaction.guild_id].cycle_track()
        await self.players[interaction.guild_id].stop()
        await self.players[interaction.guild_id].start_current_track()
        await interaction.response.send_message(f"Jumped to position {index} in the queue")

    @app_commands.command(name="clear", description="clears the entire queue")
    async def clear_queue(self, interaction: discord.Interaction):
        queue_size = self.players[interaction.guild_id].queue.count
        await self.players[interaction.guild_id].queue.clear()
        await self.players[interaction.guild_id].history.clear()
        await interaction.response.send_message(f"Cleared {queue_size} tracks from the queue")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: Player, track: wavelink.Track, reason):

        await player.play_next_track()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, player: Player, track: wavelink.Track, error):
        await player.play_next_track()

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, player: Player, track: wavelink.Track, threshold):
        await player.play_next_track()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: Player, track: wavelink.Track):
        await player.dj_channel.send(content=f"Now Playing **{track.title}**")



async def setup(bot):
    await bot.add_cog(Music(bot))
