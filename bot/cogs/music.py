import asyncio
import re
from typing import List
from typing import Literal
from typing import Optional
import discord
import discord.utils
import wavelink
from discord.ext import commands
from discord import app_commands, VoiceChannel, StageChannel
from wavelink import YouTubeTrack
from collections import deque
import atexit

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



class Server:
    def __init__(self, guild_id: int):
        self.id = str(guild_id)
        self.playlists: dict[str, Playlist] = {}     # name : Playlist
        self.player = None

    def create_playlist(self, name: str):
        self.playlists[name] = Playlist(name)
        return self.playlists[name]


class Playlist:
    def __init__(self, name: str, track_list: list[str] = None):
        self.tracks: list[str] = [] if track_list is None else track_list
        self.name = name

    def add_track(self, track: wavelink.Track) -> None:
        self.tracks.append(track.id)

    def remove_track(self, track: wavelink.Track) -> None:
        self.tracks.remove(track.id)

    def remove_track_at(self, position: int) -> None:
        self.tracks.pop(position)

    def update_list(self, new_tracks: list[wavelink.Track]):
        track_list = []
        for track in new_tracks:
            track_list.append(track.id)
        else:
            self.tracks = list(set(self.tracks + track_list))
        # self.tracks = list(set(self.tracks + new_tracks))



class Player(wavelink.Player):
    def __init__(self, dj_user: discord.Member, dj_channel: discord.TextChannel):
        super().__init__()
        self.history = wavelink.Queue()
        self.queue = wavelink.Queue()
        self.current_track: wavelink.Track = None
        self.loop_mode: LoopMode = LoopMode.NO_LOOP
        self.dj_user: discord.Member = dj_user
        self.dj_channel: discord.TextChannel = dj_channel

    async def add_to_queue(self, single: bool, track: wavelink.Track) -> None:
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


    async def restart_track(self):
        await self.play(source=self.current_track, replace=True)

    async def seek_track(self, seconds: int):
        await self.seek(seconds)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.player = None
        self.servers: dict[str, Server] = {}
        self.players = {}
        bot.loop.create_task(self.connect_nodes())


    playlist_group = app_commands.Group(name="playlist", description="commands relating to music playlists")
    
    def fetch_server(self, server_id: int):
        if str(server_id) not in self.servers:
            self.servers[str(server_id)] = Server(server_id)
        return self.servers[str(server_id)]
    
    @playlist_group.command(name="create", description="creates a new playlist")
    @app_commands.describe(source="how to source the playlist")
    async def playlist_create(self, interaction: discord.Interaction, source: Literal["new", "queue"], name: str):
        server: Server = self.fetch_server(interaction.guild_id)
        if name in server.playlists.keys():
            await interaction.response.send_message(f"A playlist named '{name}' already exists")
            return

        if source == "new":
            server.create_playlist(name)
            await interaction.response.send_message("Created a new Playlist")
        elif source == "queue":
            queue_list = list(set(server.player.history + server.player.current_track + server.player.queue))
            server.create_playlist(name).update_list(queue_list)
            await interaction.response.send_message("Created a playlist from the queue")




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
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        queue_list = list(set(server.player.history + server.player.current_track + server.player.queue))
        server.playlists[playlist].update_list(queue_list)
        await interaction.response.send_message(f"Updated playlist: '{playlist}' with the queue")

    @playlist_group.command(name="add_tracks", description="searches and adds the track(s) to the queue")
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


    @playlist_group.command(name="play", description="clears the queue and plays the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_play(self, interaction: discord.Interaction, playlist: str):
        server: Server = self.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        player: Player = await self.attempt_to_join_channel(interaction)
        player.queue.clear()
        player.current_track = None
        player.history.clear()
        tracks = [await wavelink.NodePool.get_node().build_track(cls=wavelink.Track, identifier=track_id)
                  for track_id in server.playlists[playlist].tracks
                  ]
        await player.add_to_queue(single=False, track=tracks)
        await player.cycle_track()
        await player.play_next_track()
        await interaction.response.send_message(f"Now playing playlist: '{playlist}'")


    @playlist_group.command(name="queue", description="adds the playlist to the end of the queue")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_queue(self, interaction: discord.Interaction, playlist: str):
        await interaction.response.defer()
        server: Server = self.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist")
            return
        player: Player = await self.attempt_to_join_channel(interaction)
        tracks = []

        tracks = [await wavelink.NodePool.get_node().build_track(cls=wavelink.Track, identifier=track_id)
                  for track_id in server.playlists[playlist].tracks
                  ]
        await player.add_to_queue(single=False, track=tracks)
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
        await interaction.response.defer()
        server: Server = self.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist")
            return

        message = "```swift\n"
        track_names_info = ""
        runtime: int = 0
        playlist_length = len(server.playlists[playlist].tracks)
        songs_in_message: int = 0
        for track_pos, track_id in enumerate(server.playlists[playlist].tracks):
            full_track: wavelink.Track = await wavelink.NodePool.get_node().build_track(cls=wavelink.Track,
                                                                                        identifier=track_id)
            runtime += int(full_track.duration)
            title = ""
            title_length = len(full_track.title)
            if title_length > 36:
                if title_length <= 40:
                    title = full_track.title.ljust(40)
                else:
                    title = (full_track.title[:36] + " ...").ljust(40)
            else:
                title = full_track.title.ljust(40)
            if len(track_names_info) < 1600:
                track_names_info += f"{track_pos} {title}" \
                                    f"  -  {int(full_track.duration) // 60 :02}:{int(full_track.duration) % 60:02}\n"
            else:
                track_names_info += f"and {playlist_length-songs_in_message} more songs\n"
                break

            songs_in_message += 1


        message += f"{playlist} has {playlist_length} tracks and a " \
                   f"runtime of {runtime // 3600}:{runtime // 60 :02}:{runtime % 60 % 60 :02}\n"
        message += track_names_info
        message += "```"
        await interaction.edit_original_response(content=message)

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

    @staticmethod
    async def search_song(interaction: discord.Interaction, search: str) -> list[wavelink.Track]:
        is_yt_url = bool(YT_URL_REG.search(search))
        is_url = bool(URL_REG.search(search))
        decoded_spotify_url = spotify.decode_url(search)
        is_spotify_url = bool(decoded_spotify_url is not None)

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
        else:
            tracks = [await wavelink.YouTubeTrack.search(query=search, return_first=True)]

        return tracks


    @app_commands.command(name="play", description="plays/adds the given song")
    async def play_song(self, interaction: discord.Interaction, search: str = None) -> None:
        message = ""
        if interaction.guild.voice_client:
            if search is None:
                await self.players[interaction.guild_id].resume()
                await interaction.response.send_message(content="Resumed the player")
                return
        player: Player = await self.attempt_to_join_channel(interaction)
        if search is None:
            await interaction.response.send_message("I have joined the channel", ephemeral=False)
            return

        await interaction.response.defer()
        tracks = await self.search_song(interaction, search)

        titles = ""
        for i, track in enumerate(tracks):
            title = track.title
            if len(titles + title) < 1800:
                titles += title + "\n"
            else:
                titles += f"and {i} more songs\n"
                break
        await player.add_to_queue(single=False, track=tracks)


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
    music_cog = Music(bot)
    music_cog.load_server_data()
    # atexit.register(music_cog.save_server_data)
    await bot.add_cog(music_cog)
