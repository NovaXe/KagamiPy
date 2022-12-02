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
YT_PLAYLIST_REG = re.compile(r"[\?|&](list=)(.*)\&")


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
        # print("next track played\n")
        # if self.queue.is_empty:
        #     self.current_track = None
        #     return
        # if self.current_track is not None:
        #     self.history.put(self.current_track)
        # self.current_track = self.queue.get()
        # await self.play(source=self.current_track, replace=True)

    async def play_previous_track(self):
        await self.cycle_track(reverse=True)
        await self.start_current_track()

    async def start_current_track(self):
        if self.current_track is None:
            return
        await self.play(source=self.current_track, replace=True)

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
                                            port=4762,
                                            password='KagamiLavalink1337',
                                            spotify_client=spotify.SpotifyClient(client_id=self.config["spotify"]["client_id"],
                                                                                 client_secret=self.config["spotify"]["client_secret"])
                                            )


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

        if interaction.guild_id not in self.players:
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
        if interaction.guild_id not in self.players:
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
        is_url = bool(URL_REG.search(search))
        decoded_spotify_url = spotify.decode_url(search)
        is_spotify_url = bool(decoded_spotify_url is not None)
        titles = ""

        await interaction.response.defer()

        if is_yt_url:
            if "list=" in search:
                playlist = await voice_client.node.get_playlist(identifier=search, cls=wavelink.YouTubePlaylist)
                if "playlist" in search:
                    tracks = playlist.tracks
                else:
                    tracks = [playlist.tracks[playlist.selected_track]]
            else:
                tracks = await voice_client.node.get_tracks(query=search, cls=wavelink.YouTubeTrack)
            self.players[interaction.guild_id].add_to_queue(single=False, track=tracks)
            # titles = ""
            for i, track in enumerate(tracks):
                title = track.title
                if len(titles + title) < 1800:
                    titles += title + "\n"
                else:
                    titles += f"and {i} more songs\n"
                    break
            # titles = '\n'.join([t.title for t in tracks])
        elif is_spotify_url:
            tracks = []
            # print("spotify link\n")
            if decoded_spotify_url["type"] is spotify.SpotifySearchType.track:
                tracks = [await spotify.SpotifyTrack.search(query=decoded_spotify_url["id"],
                                                            type=decoded_spotify_url["type"],
                                                            return_first=True)]
            elif decoded_spotify_url["type"] in (spotify.SpotifySearchType.playlist, spotify.SpotifySearchType.album):
                # interaction.response.defer(ephemeral=)
                tracks = await spotify.SpotifyTrack.search(query=decoded_spotify_url["id"],
                                                           type=decoded_spotify_url["type"])

            # is spotify.SpotifySearchType.playlist or decoded_spotify_url["type"] is spotify.SpotifySearchType.album
            if tracks:
                self.players[interaction.guild_id].add_to_queue(single=False, track=tracks)
                # titles = ""
                for i, track in enumerate(tracks):
                    title = track.title
                    if len(titles + title) < 1800:
                        titles += title + "\n"
                    else:
                        titles += f"and {i} more songs\n"
                        break
        else:
            track = await wavelink.YouTubeTrack.search(query=search, return_first=True)
            self.players[interaction.guild_id].add_to_queue(single=True, track=track)
            titles = track.title


        # print(titles)
        await interaction.edit_original_response(content=f"**{titles}**was added to the queue")

        if self.players[interaction.guild_id].current_track is None:
            await self.players[interaction.guild_id].play_next_track()
            # await self.players[interaction.guild_id].cycle_track()
            # await self.players[interaction.guild_id].start_current_track()

    @app_commands.command(name="queue", description="shows the track queue")
    async def show_queue(self, interaction: discord.Interaction):
        if interaction.guild_id not in self.players:
            await interaction.response.send_message("There is currently no voice session")
            return

        now_playing = self.players[interaction.guild_id].current_track
        history_list = list(reversed(list(self.players[interaction.guild_id].history)[:10]))
        queue_list = list(self.players[interaction.guild_id].queue)[:10]
        message = "```swift\n"

        for index, track in enumerate(history_list):
            title = ""
            title_length = len(track.title)
            if title_length > 36:
                if title_length <= 40:
                    title = track.title.ljust(40)
                else:
                    title = (track.title[:36] + " ...").ljust(40)
            else:
                title = track.title.ljust(40)

            position = (str(len(history_list) - index) + ")").ljust(5)
            message += f"{position} {title}" \
                       f"  -  {int((track.length / 60))}:{int(track.length % 60):02}\n"
        if len(history_list):
            message += f"      🡅Previous🡅\n"
            message += "──────────────────────────\n"
        if now_playing:

            message += f"NOW PLAYING ➤ {now_playing.title}" \
                       f"  -  {int(self.players[interaction.guild_id].position / 60)}" \
                       f":{int(self.players[interaction.guild_id].position % 60):02}" \
                       f" / {int(now_playing.length / 60)}:{int(now_playing.length % 60):02}\n"
        else:
            if not history_list and not queue_list:
                message += "The queue is empty"
            else:
                message += f"__**NOW PLAYING**__ ➤ Nothing"
        if len(queue_list):
            message += "──────────────────────────\n"
            message += "      🡇Up Next🡇\n"

        for index, track in enumerate(queue_list):
            title = ""
            title_length = len(track.title)
            if title_length > 36:
                if title_length <= 40:
                    title = track.title.ljust(40)
                else:
                    title = (track.title[:36] + " ...").ljust(40)
            else:
                title = track.title.ljust(40)
            position = (str(index + 1) + ")").ljust(5)
            message += f"{position} {title}  -  {int((track.length / 60))}:{int(track.length % 60):02}\n"
        message += "\n```"
        await interaction.response.send_message(content=message)

    # @app_commands.command(name="queue", description="shows the track queue")
    # async def show_queue(self, interaction: discord.Interaction):
    #     if interaction.guild_id not in self.players:
    #         await interaction.response.send_message("There is currently no voice session")
    #         return
    #
    #     now_playing = self.players[interaction.guild_id].current_track
    #     history_list = list(reversed(list(self.players[interaction.guild_id].history)[:10]))
    #     queue_list = list(self.players[interaction.guild_id].queue)[:10]
    #     message = ""
    #
    #     for index, track in enumerate(history_list):
    #         title = ""
    #         title_length = len(track.title)
    #         if title_length > 38:
    #             if title_length <= 40:
    #                 title = track.title
    #             else:
    #                 title = (track.title[:38] + "...").ljust(40, ' ')
    #         else:
    #             title = track.title.ljust(40)
    #
    #         title_remove = track.title[38:]
    #         position = (str(len(history_list) - index) + ")").ljust(5)
    #         message += f"**{position}** {int((track.length/60))}:{int(track.length%60):02}" \
    #                    f"  -  {title}\n"
    #     if len(history_list):
    #         message += f"**__🡅Previous🡅__**\n"
    #         message += "──────────────────────────\n"
    #     if now_playing:
    #
    #         message += f"__**NOW PLAYING**__ ➤ {now_playing.title}" \
    #                    f"  -  {int(self.players[interaction.guild_id].position / 60)}" \
    #                    f":{int(self.players[interaction.guild_id].position % 60):02}" \
    #                    f" / {int(now_playing.length/60)}:{int(now_playing.length%60):02}\n"
    #     else:
    #         if not history_list and not queue_list:
    #             message += "**__The queue is empty__**"
    #         else:
    #             message += f"__**NOW PLAYING**__ ➤ Nothing"
    #     if len(queue_list):
    #         message += "──────────────────────────\n"
    #         message += "**__🡇Up Next🡇__**\n"
    #
    #     for index, track in enumerate(queue_list):
    #         title = ""
    #         title_length = len(track.title)
    #         if title_length > 38:
    #             if title_length <= 40:
    #                 title = track.title
    #             else:
    #                 title = (track.title[:38] + "...").ljust(40)
    #         else:
    #             title = track.title.ljust(40)
    #         position = (str(index + 1) + ")").ljust(5)
    #         message += f"**{position}** {int((track.length / 60))}:{int(track.length % 60):02}  -  {title}\n"
    #     await interaction.response.send_message(content=message)

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

    async def skip_unskip_track(self, interaction: discord.Interaction, skip_back: bool, skip_count: int):
        for i in range(skip_count):
            if skip_back:
                await self.players[interaction.guild_id].cycle_track(reverse=True)
            else:
                await self.players[interaction.guild_id].cycle_track()
            # print("skipped track\n")
        await self.players[interaction.guild_id].stop()
        await self.players[interaction.guild_id].start_current_track()

    @app_commands.command(name="replay", description="replays the currently playing song")
    async def restart_song(self, interaction: discord.Interaction):
        self.player.start_current_track()
        await interaction.response.send_message(content="Replaying the current song")

    @app_commands.command(name="skip", description="skips to the next song")
    async def skip_forward(self, interaction: discord.Interaction, count: int = 1):
        await self.skip_unskip_track(interaction, False, count)
        await interaction.response.send_message("Skipped to next song")

    @app_commands.command(name="unskip", description="skips back to the previous song")
    async def skip_back(self, interaction: discord.Interaction, count: int = 1):
        await self.skip_unskip_track(interaction, True, count)
        await interaction.response.send_message("Skipped to previous song")

    # @app_commands.command(name="jumpto", description="jumps to the given spot in the queue")
    # async def jump_to(self, interaction: discord.Interaction, index: int):
    #     await self.skip_unskip_track(interaction, False, index-1)
    #     await interaction.response.send_message(f"Jumped to position {index} in the queue")
    #
    # @app_commands.command(name="jumpback", description="jumps to the given spot in the history")
    # async def jump_back(self, interaction: discord.Interaction, index: int):
    #     await self.skip_unskip_track(interaction, True, index-1)
    #     await interaction.response.send_message(f"Jumped to position {index} in the history")

    @app_commands.command(name="clear", description="clears the entire queue")
    async def clear_queue(self, interaction: discord.Interaction):
        queue_size = self.players[interaction.guild_id].queue.count
        self.players[interaction.guild_id].queue.clear()
        # self.players[interaction.guild_id].history.clear()
        await interaction.response.send_message(f"Cleared {queue_size} tracks from the queue")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: Player, track: wavelink.Track, **payload: dict):
        if payload["reason"] == "FINISHED":
            await player.play_next_track()
        # print("track end\n")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, player: Player, track: wavelink.Track, error):
        await player.play_next_track()
        # print("track exception\n")

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, player: Player, track: wavelink.Track, threshold):
        await player.play_next_track()
        # print("track stuck\n")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: Player, track: wavelink.Track):
        await player.dj_channel.send(content=f"Now Playing **{track.title}**")



async def setup(bot):
    await bot.add_cog(Music(bot))
