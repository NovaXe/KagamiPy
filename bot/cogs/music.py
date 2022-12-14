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
import math
from bot.utils.ui import MessageScroller
from bot.utils.ui import QueueController
from bot.utils.musichelpers import *

from bot.utils import ui
from wavelink.ext import spotify

URL_REG = re.compile(r'https?://(?:www\.)?.+')
YT_URL_REG = re.compile(r"(?:https://)(?:www\.)?(?:youtube|youtu\.be)(?:\.com)?\/(?:watch\?v=)?(.{11})")
YT_PLAYLIST_REG = re.compile(r"[\?|&](list=)(.*)\&")
DISCORD_ATTACHMENT_REG = re.compile(r"(https://|http://)?(cdn\.|media\.)discord(app)?\.(com|net)/attachments/[0-9]{17,19}/[0-9]{17,19}/(?P<filename>.{1,256})\.(?P<mime>[0-9a-zA-Z]{2,4})(\?size=[0-9]{1,4})?")
SOUNDCLOUD_REG = re.compile("^https?:\/\/(www\.|m\.)?soundcloud\.com\/[a-z0-9](?!.*?(-|_){2})[\w-]{1,23}[a-z0-9](?:\/.+)?$")


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.player = None
        self.servers: dict[str, Server] = {}
        self.players = {}




    playlist_group = app_commands.Group(name="playlist", description="commands relating to music playlists")
    music_group = app_commands.Group(name="music", description="commands relating to music playback")
    
    def fetch_server(self, server_id: int):
        if str(server_id) not in self.servers:
            self.servers[str(server_id)] = Server(server_id)
        return self.servers[str(server_id)]
    
    @playlist_group.command(name="create", description="creates a new playlist")
    @app_commands.describe(source="how to source the playlist")
    async def playlist_create(self, interaction: discord.Interaction, source: Literal["new", "queue"], name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)

        if name in server.playlists.keys():
            await interaction.edit_original_response(content=f"A playlist named '{name}' already exists")
            return

        if source == "new":
            server.create_playlist(name)
            await interaction.edit_original_response(content="Created a new Playlist")
        elif source == "queue":
            if current_player is None:
                await interaction.edit_original_response(content="There is currently no voice session")
                return
            history_list = list(current_player.history)
            queue_list = list(current_player.queue)
            current_track = [current_player.current_track]


            playlist_list = list(dict.fromkeys((history_list + current_track + queue_list)).keys())

            server.create_playlist(name).update_list(playlist_list)
            await interaction.edit_original_response(content="Created a playlist from the queue")

    async def playlist_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        server: Server = self.fetch_server(interaction.guild_id)
        return [
            app_commands.Choice(name=playlist_name, value=playlist_name)
            for playlist_name, playlist in server.playlists.items() if current.lower() in playlist_name.lower()
        ][:25]

    @playlist_group.command(name="delete", description="deletes the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_delete(self, interaction: discord.Interaction, playlist: str):
        server: Server = self.fetch_server(interaction.guild_id)
        await interaction.response.defer()
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        server.playlists.pop(playlist)
        # del server.playlists[playlist]
        await interaction.edit_original_response(content=f"Playlist: '{playlist}' was deleted")

    @playlist_group.command(name="rename", description="renames the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_rename(self, interaction: discord.Interaction, playlist: str, new_name: str):
        server: Server = self.fetch_server(interaction.guild_id)
        await interaction.response.defer()
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return

        if new_name in server.playlists.keys():
            await interaction.response.send_message(f"A playlist named '{new_name}' already exists")
            return

        server.playlists[new_name] = server.playlists.pop(playlist)
        await interaction.edit_original_response(content=f"Playlist: '{playlist}' renamed to '{new_name}'")


    @playlist_group.command(name="update", description="merges the current queue into the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_update(self, interaction: discord.Interaction, playlist: str):
        server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return

        if current_player is None:
            await interaction.response.send_message(content="There is currently no voice session")
            return

        history_list = list(current_player.history)
        queue_list = list(current_player.queue)
        current_track = [current_player.current_track]

        playlist_list = list(dict.fromkeys((history_list + current_track + queue_list)).keys())

        server.playlists[playlist].update_list(playlist_list)
        await interaction.response.send_message(f"Updated playlist: '{playlist}' with the queue")

    @playlist_group.command(name="add_tracks", description="Searches and adds the track(s) to the queue")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_add_tracks(self, interaction: discord.Interaction, playlist: str, song: str):
        server: Server = self.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        tracks = await self.search_song(interaction, song)
        server.playlists[playlist].update_list(tracks)
        length = len(tracks)
        if length == 1:
            await interaction.response.send_message(f"Added {tracks[0].title} to playlist: '{playlist}'")
        else:
            await interaction.response.send_message(f"Added {length} tracks to playlist: '{playlist}")

    @playlist_group.command(name="remove_track", description="Removes the track at the given position")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_remove_track(self, interaction: discord.Interaction, playlist: str, track_position: int):
        server: Server = self.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        interaction.response.defer()
        track_id = server.playlists[playlist].tracks.pop(track_position-1)
        full_track = await wavelink.NodePool.get_node().build_track(cls=wavelink.Track, identifier=track_id)
        await interaction.edit_original_response(
            content=f"Removed track {track_position}: '{full_track.title}' from playlist: '{playlist}'")

    @playlist_group.command(name="play", description="clears the queue and plays the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_play(self, interaction: discord.Interaction, playlist: str):
        server: Server = self.fetch_server(interaction.guild_id)
        await interaction.response.defer(thinking=True)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist", ephemeral=True)
            return
        current_player: Player = await self.attempt_to_join_vc(interaction)
        current_player.queue.clear()
        current_player.current_track = None
        current_player.history.clear()
        tracks = [await wavelink.NodePool.get_node().build_track(cls=wavelink.Track, identifier=track_id)
                  for track_id in server.playlists[playlist].tracks
                  ]
        await current_player.add_to_queue(single=False, track=tracks)
        # await player.cycle_track()
        await current_player.play_next_track()
        await interaction.edit_original_response(content=f"Now playing playlist: '{playlist}'")

    @playlist_group.command(name="queue", description="adds the playlist to the end of the queue")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_queue(self, interaction: discord.Interaction, playlist: str):
        await interaction.response.defer()
        server: Server = self.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist")
            return
        current_player: Player = await self.attempt_to_join_vc(interaction)
        tracks = []

        tracks = [await wavelink.NodePool.get_node().build_track(cls=wavelink.Track, identifier=track_id)
                  for track_id in server.playlists[playlist].tracks
                  ]
        await current_player.add_to_queue(single=False, track=tracks)
        await interaction.edit_original_response(content=f"Added playlist: '{playlist}' to the queue")

    @playlist_group.command(name="list_all", description="lists all the server's playlists")
    async def playlist_list(self, interaction: discord.Interaction):
        server: Server = self.fetch_server(interaction.guild_id)
        await interaction.response.defer()

        def shorten_name(name: str) -> str:
            length = len(name)
            if length > 36:
                if length <= 40:
                    new_name = name.ljust(40)
                else:
                    new_name = (name[:36] + " ...").ljust(40)
            else:
                new_name = name.ljust(40)
            return new_name

        message = f"```swift\n{interaction.guild.name} Playlists:\n"
        message += "\n".join([
            f"\t{shorten_name(playlist_name)}   :   tracks: {len(playlist.tracks)}" for playlist_name, playlist in server.playlists.items()
        ])
        message += "```"
        await interaction.edit_original_response(content=message)

    @playlist_group.command(name="show_tracks", description="shows what songs are in a playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_show_tracks(self, interaction: discord.Interaction, playlist: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist")
            return


        track_names_info = ""
        runtime: int = 0
        track_ids = server.playlists[playlist].tracks
        playlist_length = len(track_ids)
        total_page_count = math.ceil(playlist_length / 10)



        page_data = [(int(i / 10), track_ids[i:i + 10]) for i in range(0, playlist_length, 10)]

        pages: List[str] = []
        track_index = 0
        for page_index, page_list in page_data:

            content = ""
            content += "??????????????????????????????????????????????????????????????????????????????\n"
            for index, track_id in enumerate(page_list):
                full_track: wavelink.Track = await wavelink.NodePool.get_node().build_track(cls=wavelink.Track,
                                                                                            identifier=track_id)
                track_string = track_to_string(full_track)
                position = (str(track_index+1) + ")").ljust(5)
                content += f"{position} {track_string}"
                runtime += full_track.duration
                track_index += 1

            # pages[current_page] = content
            content += f"Page #: {page_index + 1} / {total_page_count}\n"
            content += "```"
            pages.insert(page_index, content)

        playlist_hours = int(runtime // 3600)
        playlist_minutes = int((runtime % 60) // 60)
        playlist_seconds = int(runtime % 60)
        playlist_info_text = f"```swift\n{playlist} has {playlist_length} tracks and a runtime of " \
                             f"{playlist_hours:02}:{playlist_minutes:02}:{playlist_seconds:02}\n"

        pages = [playlist_info_text + page for page in pages]


        message = await interaction.edit_original_response(content=pages[0])

        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(view=view)

    def save_server_data(self):
        data: dict[int, dict[str, dict[str, str]]] = {}
        for server_id, server in self.servers.items():
            data[server_id] = {"playlists": {}}
            for playlist_name, playlist in server.playlists.items():
                data[server_id]["playlists"].update({playlist_name: playlist.tracks})


        self.bot.server_data = data

    def load_server_data(self):
        for server_id, server in self.bot.server_data.items():
            self.servers[server_id] = Server(server_id)
            for playlist_name, playlist_tracks in self.bot.server_data[server_id]["playlists"].items():
                self.servers[server_id].playlists[playlist_name] = Playlist(playlist_name, playlist_tracks)

    async def cog_unload(self) -> None:
        self.save_server_data()

    async def cog_load(self):
        self.bot.loop.create_task(self.connect_nodes())

    @tasks.loop(seconds=10)
    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(bot=self.bot,
                                            host='127.0.0.1',
                                            port=4762,
                                            password='KagamiLavalink1337',
                                            spotify_client=spotify.SpotifyClient(client_id=self.config["spotify"]["client_id"],
                                                                                 client_secret=self.config["spotify"]["client_secret"])
                                            )

    @staticmethod
    async def close_nodes() -> None:
        for node in wavelink.NodePool.nodes:
            await node.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f"Node: <{node.identifier}> is ready")


    # async def attempt_to_join_channel_old(self, interaction: discord.Interaction) -> discord.VoiceClient:
    #     user_voice = interaction.user.voice
    #     if user_voice is None:
    #         await interaction.response.send_message("Please join a voice channel", ephemeral=False)
    #         return None
    #     channel = user_voice.channel
    #     voice_client = interaction.guild.voice_client
    #     server: Server = self.fetch_server(interaction.guild_id)
    #
    #     if server.player is None:
    #         server.player = Player(dj_user=interaction.user, dj_channel=interaction.channel)
    #         if voice_client is None:
    #             voice_client: Player = await channel.connect(cls=server.player)
    #         return voice_client
    #     return voice_client


    async def join_voice_channel(self, interaction: discord.Interaction, guild: discord.Guild=None, voice_channel: discord.VoiceChannel=None, keep_existing_player=False):
        server: Server = self.fetch_server(interaction.guild_id)
        voice_client: Player = self.fetch_player_instance(interaction.guild)
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


    def fetch_player_instance(self, guild: discord.Guild):
        server: Server = self.fetch_server(guild.id)
        # node = wavelink.NodePool.get_node()
        # player: Player = node.get_player(guild)
        player: Player = guild.voice_client

        # server.player = player
        return player



    async def attempt_to_join_vc(self, interaction: discord.Interaction, voice_channel=None, should_switch_channel=False):
        voice_client = self.fetch_player_instance(interaction.guild)

        if voice_client:
            if should_switch_channel:
                voice_client = await self.join_voice_channel(interaction, voice_channel=voice_channel, keep_existing_player=False)
        else:
            voice_client = await self.join_voice_channel(interaction, voice_channel=voice_channel, keep_existing_player=False)

        return voice_client



    @app_commands.command(name="join", description="joins your current voice channel")
    async def join_channel(self, interaction: discord.Interaction, voice_channel: discord.VoiceChannel=None) -> None:
        voice_client = await self.attempt_to_join_vc(interaction=interaction, voice_channel=voice_channel, should_switch_channel=False)
        if voice_client is None:
            await interaction.response.send_message(f"An issue occurred when attempting to join the channel")
            return

        await interaction.response.send_message(f"I have joined {interaction.user.voice.channel.name}")

    @app_commands.command(name="leave", description="leaves the channel")
    async def leave_channel(self, interaction: discord.Interaction):
        voice_client: Player = self.fetch_player_instance(interaction.guild)
        if voice_client is None:
            await interaction.response.send_message("I am not in a voice channel")
            return

        await voice_client.disconnect()
        await interaction.response.send_message("I have left the voice channel")

    @staticmethod
    async def search_song(interaction: discord.Interaction, search: str) -> list[wavelink.Track]:
        is_yt_url = bool(YT_URL_REG.search(search))
        is_url = bool(URL_REG.search(search))
        decoded_spotify_url = spotify.decode_url(search)
        is_spotify_url = bool(decoded_spotify_url is not None)
        is_soundcloud_url = bool(SOUNDCLOUD_REG.search(search))
        attachment_regex_result = DISCORD_ATTACHMENT_REG.search(search)
        is_discord_attachment = bool(attachment_regex_result)
        tracks = []

        node = wavelink.NodePool.get_node()

        if is_yt_url:
            if "list=" in search:

                playlist = await node.get_playlist(identifier=search, cls=wavelink.YouTubePlaylist)
                if "playlist" in search:
                    tracks = playlist.tracks
                else:
                    tracks = [playlist.tracks[playlist.selected_track]]
            else:
                tracks = await node.get_tracks(query=search, cls=wavelink.YouTubeTrack)
        elif is_spotify_url:
            if decoded_spotify_url["type"] is spotify.SpotifySearchType.track:
                tracks = [await spotify.SpotifyTrack.search(query=decoded_spotify_url["id"],
                                                            type=decoded_spotify_url["type"],
                                                            return_first=True)]
            elif decoded_spotify_url["type"] in (spotify.SpotifySearchType.playlist, spotify.SpotifySearchType.album):
                tracks = await spotify.SpotifyTrack.search(query=decoded_spotify_url["id"],
                                                           type=decoded_spotify_url["type"])
        elif is_soundcloud_url:
            tracks = await node.get_tracks(query=search, cls=wavelink.SoundCloudTrack)

        elif is_discord_attachment:
            modified_track = (await node.get_tracks(query=search, cls=wavelink.LocalTrack))[0]
            modified_track.title = attachment_regex_result.group("filename")+"."+attachment_regex_result.group("mime")
            tracks = [modified_track]
        else:
            tracks = [await wavelink.YouTubeTrack.search(query=search, return_first=True)]


        return tracks


    @app_commands.command(name="play", description="plays/adds the given song")
    async def play_song(self, interaction: discord.Interaction, search: str = None) -> None:
        current_player: Player = self.fetch_player_instance(interaction.guild)

        if current_player:
            if search is None:
                await current_player.resume()
                await interaction.response.send_message(content="Resumed the player")
                return

        current_player = await self.attempt_to_join_vc(interaction=interaction, should_switch_channel=False)
        if search is None:
            await interaction.response.send_message("I have joined the channel", ephemeral=False)
            return


        await interaction.response.defer()
        tracks = await self.search_song(interaction, search)
        track_count = len(tracks)
        total_page_count = math.ceil(track_count / 10)


        if track_count > 1:

            page_data = [(int(i / 10), tracks[i:i + 10]) for i in range(0, len(tracks), 10)]

            pages: List[str] = []
            track_index = 0
            runtime = 0
            for page_index, page_list in page_data:

                content = ""
                content += "??????????????????????????????????????????????????????????????????????????????\n"
                for index, track in enumerate(page_list):

                    track_string = track_to_string(track)
                    position = (str(track_index + 1) + ")").ljust(5)
                    content += f"{position} {track_string}"
                    runtime += track.duration
                    track_index += 1

                # pages[current_page] = content
                content += f"Page #: {page_index + 1} / {total_page_count}\n"
                content += "```"
                pages.insert(page_index, content)

            playlist_hours = int(runtime // 3600)
            playlist_minutes = int((runtime % 60) // 60)
            playlist_seconds = int(runtime % 60)
            playlist_info_text = f"```swift\n{track_count} tracks were added to the queue, adding " \
                                 f"{playlist_hours:02}:{playlist_minutes:02}:{playlist_seconds:02} to the runtime\n"

            pages = [playlist_info_text + page for page in pages]
            message = await interaction.edit_original_response(content=pages[0])
            view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
            await interaction.edit_original_response(content=pages[0], view=view)
        else:
            track_hours = int(tracks[0].duration // 3600)
            track_minutes = int((tracks[0].duration % 60) // 60)
            track_seconds = int(tracks[0].duration % 60)
            await interaction.edit_original_response(content=f"`{tracks[0].title}  -  {f'{track_hours}:02' + ':' if track_hours > 0 else ''}{track_minutes:02}:{track_seconds:02} was added to the queue`")


        await current_player.add_to_queue(single=False, track=tracks)
        if current_player.current_track is None:
            await current_player.play_next_track()


    @app_commands.command(name="queue", description="shows the track queue")
    async def show_queue(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)
        if current_player is None:
            await interaction.edit_original_response(content="There is currently no voice session")
            return
        pages, home_page = await create_queue_pages(current_player)
        message = await interaction.edit_original_response(content=pages[home_page])

        # scrolling_view = MessageScroller(message=message, pages=pages, home_page=home_page)
        controller_view = QueueController(player=current_player, message=message, pages=pages, home_page=home_page)
        await interaction.edit_original_response(view=controller_view)




    @app_commands.command(name="nowplaying", description="shows the currently playing track")
    async def now_playing(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)
        if current_player is None:
            await interaction.edit_original_response(content="There is currently no voice session")
            return

        now_playing = current_player.current_track
        if current_player.current_track:
            now_playing_text = f"**`NOW PLAYING ??? {now_playing.title}" \
                               f"  -  {int(current_player.position / 60)}" \
                               f":{int(current_player.position % 60):02}" \
                               f" / {int(now_playing.length / 60)}:{int(now_playing.length % 60):02}`**"
        else:
            now_playing_text = f"**`NOW PLAYING ??? Nothing`**\n"

        current_player.now_playing_message = await interaction.edit_original_response(content=now_playing_text)


    async def toggle_pause(self, interaction: discord.Interaction = None):
        message: str = None
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)
        if current_player.is_paused():
            await current_player.resume()
            message = "Resumed the player"
        else:
            await current_player.pause()
            message = "Paused the player"
        if interaction is None:
            return
        await interaction.response.send_message(content=message, ephemeral=True)

    @app_commands.command(name="pause", description="pauses the player")
    async def pause_song(self, interaction: discord.Interaction):
        await self.toggle_pause(interaction)

    @app_commands.command(name="resume", description="resumes the player")
    async def resume_song(self, interaction: discord.Interaction):
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)

        await current_player.resume()
        await interaction.response.send_message(content="Resumed the player", ephemeral=True)

    async def skip_unskip_track(self, interaction: discord.Interaction, skip_back: bool, skip_count: int):
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)
        if current_player is None:
            return None

        if current_player.current_track is None:
            for i in range(skip_count):
                await current_player.cycle_track(reverse=skip_back)
                print("skipped track\n")
            await current_player.start_current_track()
            return


        current_player.skip_to_prev = skip_back
        current_player.skip_count = skip_count



        # for i in range(skip_count):
        #     if skip_back:
        #         await current_player.cycle_track(reverse=True)
        #     else:
        #         await current_player.cycle_track()
        #     # print("skipped track\n")

        await current_player.stop()
        # await current_player.start_current_track()

    @app_commands.command(name="replay", description="replays the currently playing song")
    async def restart_song(self, interaction: discord.Interaction):
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)

        await current_player.start_current_track()
        await interaction.response.send_message(content="Replaying the current song")

    @app_commands.command(name="skip", description="skips to the next song")
    async def skip_forward(self, interaction: discord.Interaction, count: int = 1):
        if await self.skip_unskip_track(interaction, False, count) is None:
            await interaction.response.send_message("There is currently no voice session")
            return
        await interaction.response.send_message("Skipped to next song")

    @app_commands.command(name="unskip", description="skips back to the previous song")
    async def skip_back(self, interaction: discord.Interaction, count: int = 1):
        if await self.skip_unskip_track(interaction, True, count) is None:
            await interaction.response.send_message("There is currently no voice session")
            return
        await interaction.response.send_message("Skipped to previous song")

    @app_commands.command(name="loop", description="cycles through loop modes")
    async def loop(self, interaction: discord.Interaction):
        current_player: Player = self.fetch_player_instance(interaction.guild)
        if current_player is None:
            await interaction.response.send_message("There is currently no voice session")
            return
        current_player.loop_mode.next()

        message = ""
        match current_player.loop_mode:
            case LoopMode.NO_LOOP:
                message = "Loop Off"
            case LoopMode.LOOP_QUEUE:
                message = "Loop Queue"
            case LoopMode.LOOP_SONG:
                message = "Loop Song"


        await interaction.response.send_message(content=f"Loop Mode: {message}")




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
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: Player = self.fetch_player_instance(interaction.guild)

        queue_size = current_player.queue.count

        current_player.queue.clear()
        # self.players[interaction.guild_id].history.clear()
        await interaction.response.send_message(f"Cleared {queue_size} tracks from the queue")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: Player, track: wavelink.Track, **payload: dict):
        # print("loop mode ", player.loop_mode)
        if player.loop_mode is LoopMode.NO_LOOP:
            pass
        elif player.loop_mode is LoopMode.LOOP_QUEUE:
            if player.queue.is_empty:
                # print("empty queue")
                if not player.history.is_empty:
                    # print("not empty history")
                    await player.cycle_track()
                    player.queue = player.history.copy()
                    player.history.clear()
                else:
                    # print("empty history")
                    await player.restart_current_track()
                    return
            else:
                pass
        elif player.loop_mode is LoopMode.LOOP_SONG:
            await player.restart_current_track()
            return

        for i in range(player.skip_count):
            await player.cycle_track(reverse=player.skip_to_prev)
        player.skip_to_prev = False
        player.skip_count = 1

        # print("track ended")




        await player.start_current_track()

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
        # track_title: str = str(player.source)
        #
        # if not player.source:
        #     track_title = track.title
        # await player.dj_channel.send(content=f"Now Playing **{track_title}**")


        track = player.current_track
        track_hours = int(track.duration // 3600)
        track_minutes = int((track.duration % 60) // 60)
        track_seconds = int(track.duration % 60)
        message = f"**`NOW PLAYING {track.title}  -  {f'{track_hours}:02' + ':' if track_hours > 0 else ''}{track_minutes:02}:{track_seconds:02} `**"

        if player.now_playing_message is None:
            player.now_playing_message = await player.dj_channel.send(content=message)
        elif player.dj_channel.last_message_id == player.now_playing_message.id:
            await player.now_playing_message.edit(content=message)
        else:
            new_message = await player.dj_channel.send(content=message)
            await player.now_playing_message.delete()
            player.now_playing_message = new_message

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        server: Server = self.fetch_server(member.guild.id)
        current_player: Player = member.guild.voice_client

        if current_player is None:
            server.player = None
            # print("no voice client")
            return
        # print("state change")
        if before.channel is None:
            # print("not in channel")
            return
        if before.channel != after.channel:
            # print("user left channel")
            if len(before.channel.members)-1 == 0:
                # print("leaving")
                await current_player.dj_channel.send(f"Everyone left '{before.channel.name}' so I left too")
                await current_player.disconnect()
                server.player = None
            # else:
            #     print("members remain")
        # else:
        #     print("user didn't leave")






async def setup(bot):
    music_cog = Music(bot)
    music_cog.load_server_data()
    # atexit.register(music_cog.save_server_data)
    await bot.add_cog(music_cog)
