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
from discord import app_commands, VoiceChannel, StageChannel, interactions
from discord.ext import tasks
from wavelink import YouTubeTrack
from collections import deque
import atexit
import math

from bot.utils.ui import MessageScroller
from bot.utils.ui import QueueController
from bot.utils.bot_data import Server
from bot.utils.music_helpers import *
from bot.utils.utils import (
    secondsDivMod
)
from bot.utils.pages import createPageList, CustomRepr

from bot.utils import ui
from wavelink.ext import spotify




class OldMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        # self.servers: dict[str, Server] = {}




    # soundboard_group = app_commands.Group(name="soundboard", description="commands relating to the custom soundboard")
    playlist_group = app_commands.Group(name="playlist", description="commands relating to music playlists")
    # music_group = app_commands.Group(name="music", description="commands relating to music playback")


    async def cog_unload(self) -> None:
        pass

    async def cog_load(self):
        # self.bot.loop.create_task(self.connect_nodes())
        pass

    @tasks.loop(seconds=10)
    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        node = wavelink.Node(uri='http://localhost:4762', password='KagamiLavalink1337')
        spotify_client = spotify.SpotifyClient(
            client_id=self.config["spotify"]["client_id"],
            client_secret=self.config["spotify"]["client_secret"]
        )
        await wavelink.NodePool.connect(
            client=self.bot,
            nodes=[node],
            spotify=spotify_client
        )

    @staticmethod
    async def close_nodes() -> None:
        for node in wavelink.NodePool.nodes:
            await node.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        """Uneeded"""
        # print(f"Node: <{node.id}> is ready")
        pass


    async def join_voice_channel(self, interaction: discord.Interaction, guild: discord.Guild=None, voice_channel: discord.VoiceChannel=None, keep_existing_player=False):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        voice_client: OldPlayer = interaction.guild.voice_client
        if guild:
            voice_client: OldPlayer = guild.voice_client



        if voice_channel:
            channel_to_join = voice_channel
        else:
            if interaction.user.voice:
                channel_to_join: discord.VoiceChannel = interaction.user.voice.channel
            else:
                raise app_commands.AppCommandError("No VC specified")

        player = None
        is_new_client = False
        if voice_client is not None:
            if keep_existing_player:
                player = voice_client
                await player.move_to(channel=channel_to_join)
            else:
                player = OldPlayer(dj_user=interaction.user, dj_channel=interaction.channel)
                await voice_client.disconnect()
                is_new_client = True
        else:
            player = OldPlayer(dj_user=interaction.user, dj_channel=interaction.channel)
            is_new_client = True

        if is_new_client:
            voice_client = await channel_to_join.connect(cls=player)



        server.has_player = True
        # server.player = voice_client
        return voice_client

    async def attempt_to_join_vc(self, interaction: discord.Interaction, voice_channel=None, should_switch_channel=False):
        voice_client = interaction.guild.voice_client

        if voice_client:
            if should_switch_channel:
                voice_client = await self.join_voice_channel(interaction, voice_channel=voice_channel, keep_existing_player=True)

        else:
            voice_client = await self.join_voice_channel(interaction, voice_channel=voice_channel, keep_existing_player=False)

        return voice_client



    @app_commands.command(name="join", description="joins your current voice channel")
    async def join_channel(self, interaction: discord.Interaction, voice_channel: discord.VoiceChannel=None) -> None:
        voice_client = await self.attempt_to_join_vc(interaction=interaction, voice_channel=voice_channel, should_switch_channel=True)
        if voice_client is None:
            await interaction.response.send_message(f"An issue occurred when attempting to join the channel")
            return

        await interaction.response.send_message(f"I have joined {voice_client.channel.name}")



    @app_commands.command(name="leave", description="leaves the channel")
    async def leave_channel(self, interaction: discord.Interaction):
        voice_client: OldPlayer = interaction.guild.voice_client
        if voice_client is None:
            await interaction.response.send_message("I am not in a voice channel")
            return

        await voice_client.disconnect()
        await interaction.response.send_message("I have left the voice channel")


    @app_commands.command(name="play", description="plays/adds the given song")
    async def play_song(self, interaction: discord.Interaction, search: str = None) -> None:
        current_player: OldPlayer = interaction.guild.voice_client

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
        tracks = await search_song(search)
        track_count = len(tracks)
        total_page_count = math.ceil(track_count / 10)


        if track_count > 1:

            page_data = [(int(i / 10), tracks[i:i + 10]) for i in range(0, len(tracks), 10)]

            pages: List[str] = []
            track_index = 0
            runtime = 0
            for page_index, page_list in page_data:

                content = ""
                content += "──────────────────────────\n"
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

            hours, minutes, seconds = secondsDivMod(runtime)

            playlist_info_text = f"```swift\n{track_count} tracks were added to the queue, adding " \
                                 f"{hours:02}:{minutes:02}:{seconds:02} to the runtime\n"

            pages = [playlist_info_text + page for page in pages]
            message = await(await interaction.edit_original_response(content=pages[0])).fetch()
            view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
            await interaction.edit_original_response(content=pages[0], view=view)
        else:
            hours, minutes, seconds = secondsDivMod(tracks[0].duration)
            await interaction.edit_original_response(content=f"`{tracks[0].title}  -  {f'{hours}:02' + ':' if hours > 0 else ''}{minutes:02}:{seconds:02} was added to the queue`")


        await current_player.add_to_queue(single=False, track=tracks)
        if current_player.current_track is None:
            await current_player.play_next_track()


    @app_commands.command(name="queue", description="shows the track queue")
    async def show_queue(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: OldPlayer = interaction.guild.voice_client
        if current_player is None:
            await interaction.edit_original_response(content="There is currently no voice session")
            return
        pages, home_page = await create_queue_pages(current_player)
        message = await(await interaction.edit_original_response(content=pages[home_page])).fetch()

        # scrolling_view = MessageScroller(message=message, pages=pages, home_page=home_page)
        controller_view = QueueController(player=current_player, message=message, pages=pages, home_page=home_page)
        await interaction.edit_original_response(view=controller_view)

    @app_commands.command(name="pop_track", description="Pops the given track from the queue")
    async def pop_song(self, interaction: discord.Interaction, position: int):
        await interaction.response.defer(thinking=True)
        current_player: OldPlayer = interaction.guild.voice_client
        if current_player is None:
            await interaction.edit_original_response(content="There is currently no voice session")
            return

        popped_track = None
        if position < 0:
            history_length = current_player.history.count

            # new_position_of_track = ((position * -1) - 1)
            new_position_of_track = (history_length-1) - ((position * -1) - 1)
            popped_tracks: wavelink.GenericTrack = current_player.history._queue[new_position_of_track]
            del current_player.history._queue[new_position_of_track]


            await interaction.edit_original_response(content=f"Popped `{popped_track.title}` from the history`")
        elif position == 0:
            popped_track: wavelink.GenericTrack = current_player.current_track
            current_player.current_track = None
            await self.skip_unskip_track(interaction, skip_back=False, skip_count=1)
            await interaction.edit_original_response(content=f"Popped the current track `{popped_track.title}`")

        else:
            popped_track: wavelink.GenericTrack = current_player.queue._queue[position-1]
            del current_player.queue._queue[position-1]
            await interaction.edit_original_response(content=f"Popped `{popped_track.title}` from the queue`")





    @app_commands.command(name="nowplaying", description="shows the currently playing track")
    async def now_playing(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        current_player: OldPlayer = interaction.guild.voice_client
        if current_player is None:
            await interaction.edit_original_response(content="There is currently no voice session")
            return

        now_playing = current_player.current_track
        if current_player.current_track:

            hours, minutes, seconds = secondsDivMod(int(now_playing.duration // 1000))
            p_hours, p_minutes, p_seconds = secondsDivMod(int(current_player.position // 1000))

            now_playing_text = f"**`NOW PLAYING ➤ {now_playing.title}" \
                               f"  -  {f'{p_hours:02}' + ':' if p_hours > 0 else ''}{p_minutes:02}:{p_seconds:02}" \
                               f" / {f'{hours:02}' + ':' if hours > 0 else ''}{minutes:02}:{seconds:02}`**"


        else:
            now_playing_text = f"**`NOW PLAYING ➤ Nothing`**\n"

        current_player.now_playing_message = await interaction.edit_original_response(content=now_playing_text)


    async def toggle_pause(self, interaction: discord.Interaction = None):
        message: str = None
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: OldPlayer = interaction.guild.voice_client
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
        current_player: OldPlayer = interaction.guild.voice_client

        await current_player.resume()
        await interaction.response.send_message(content="Resumed the player", ephemeral=True)

    @staticmethod
    async def skip_unskip_track(interaction: discord.Interaction, skip_back: bool, skip_count: int):
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: OldPlayer = interaction.guild.voice_client
        if current_player is None:
            return False

        if current_player.current_track is None:
            for i in range(skip_count):
                await current_player.cycle_track(reverse=skip_back)
                print("skipped track\n")
            await current_player.start_current_track()
            return True


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
        current_player: OldPlayer = interaction.guild.voice_client

        await current_player.start_current_track()
        await interaction.response.send_message(content="Replaying the current song")

    @app_commands.command(name="skip", description="skips to the next song")
    async def skip_forward(self, interaction: discord.Interaction, count: int = 1):
        if await self.skip_unskip_track(interaction=interaction, skip_back=False, skip_count=count) is False:
            await interaction.response.send_message("There is currently no voice session")
            return
        await interaction.response.send_message("Skipped to next song")

    @app_commands.command(name="unskip", description="skips back to the previous song")
    async def skip_back(self, interaction: discord.Interaction, count: int = 1):
        if await self.skip_unskip_track(interaction=interaction, skip_back=True, skip_count=count) is False:
            await interaction.response.send_message("There is currently no voice session")
            return
        await interaction.response.send_message("Skipped to previous song")

    @app_commands.command(name="loop", description="cycles through loop modes")
    async def loop(self, interaction: discord.Interaction):
        current_player: OldPlayer = interaction.guild.voice_client
        if current_player is None:
            await interaction.response.send_message("There is currently no voice session")
            return
        current_player.loop_mode = current_player.loop_mode.next()

        message = ""
        match current_player.loop_mode:
            case LoopMode.NO_LOOP:
                message = "Loop Off"
            case LoopMode.LOOP_QUEUE:
                message = "Loop Queue"
            case LoopMode.LOOP_SONG:
                message = "Loop Song"


        await interaction.response.send_message(content=f"Loop Mode: `{message}`")

    @app_commands.command(name="seek", description="seeks the currently playing track")
    async def seek(self, interaction: discord.Interaction, position: int):
        await interaction.response.defer(thinking=True)
        current_player: OldPlayer = interaction.guild.voice_client
        if not current_player:
            await interaction.edit_original_response(content="There is no voice session")
            return

        await current_player.seek(position*1000)
        await interaction.edit_original_response(content=f"Seeked to `{position}` seconds")




    @app_commands.command(name="clear", description="clears the entire queue")
    async def clear_queue(self, interaction: discord.Interaction):
        # server: Server = self.fetch_server(interaction.guild_id)
        current_player: OldPlayer = interaction.guild.voice_client

        queue_size = current_player.queue.count

        current_player.queue.clear()
        # self.players[interaction.guild_id].history.clear()
        await interaction.response.send_message(f"Cleared `{queue_size}` tracks from the queue")


    async def playlist_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        server: Server = self.bot.fetch_server(interaction.guild_id)
        return [
                   app_commands.Choice(name=playlist_name, value=playlist_name)
                   for playlist_name, playlist in server.playlists.items() if current.lower() in playlist_name.lower()
               ][:25]

    @playlist_group.command(name="create", description="creates a new playlist")
    @app_commands.describe(source="how to source the playlist")
    async def playlist_create(self, interaction: discord.Interaction, source: Literal["new", "queue"], name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        current_player: OldPlayer = interaction.guild.voice_client

        if name in server.playlists.keys():
            await interaction.edit_original_response(content=f"A playlist named `{name}` already exists")
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


    @playlist_group.command(name="delete", description="deletes the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_delete(self, interaction: discord.Interaction, playlist: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        await interaction.response.defer()
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        server.playlists.pop(playlist)
        # del server.playlists[playlist]
        await interaction.edit_original_response(content=f"Playlist: `{playlist}` was deleted")

    @playlist_group.command(name="rename", description="renames the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_rename(self, interaction: discord.Interaction, playlist: str, new_name: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        await interaction.response.defer()
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return

        if new_name in server.playlists.keys():
            await interaction.response.send_message(f"A playlist named `{new_name}` already exists")
            return

        server.playlists[new_name] = server.playlists.pop(playlist)
        await interaction.edit_original_response(content=f"Playlist: `{playlist}` renamed to `{new_name}`")

    @playlist_group.command(name="update", description="merges the current queue into the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_update(self, interaction: discord.Interaction, playlist: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        current_player: OldPlayer = interaction.guild.voice_client
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
        await interaction.response.send_message(f"Updated playlist: `{playlist}` with the queue")

    @playlist_group.command(name="add_tracks", description="Searches and adds the track(s) to the queue")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_add_tracks(self, interaction: discord.Interaction, playlist: str, song: str):
        await interaction.response.defer()
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        tracks = await search_song(song)
        server.playlists[playlist].update_list(tracks)
        length = len(tracks)
        if length == 1:
            await interaction.edit_original_response(content=f"Added `{tracks[0].title}` to playlist: `{playlist}`")
        else:
            await interaction.edit_original_response(content=f"Added `{length}` tracks to playlist: `{playlist}`")

    @playlist_group.command(name="remove_track", description="Removes the track at the given position")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_remove_track(self, interaction: discord.Interaction, playlist: str, track_position: int):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.response.send_message("Playlist does not exist", ephemeral=True)
            return
        interaction.response.defer()
        track_id = server.playlists[playlist].tracks.pop(track_position - 1)
        full_track = await wavelink.NodePool.get_node().build_track(cls=wavelink.GenericTrack, encoded=track_id)
        await interaction.edit_original_response(
            content=f"Removed track {track_position}: '{full_track.title}' from playlist: `{playlist}`")

    @playlist_group.command(name="play", description="clears the queue and plays the playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_play(self, interaction: discord.Interaction, playlist: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        await interaction.response.defer(thinking=True)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist")
            return
        current_player: OldPlayer = await self.attempt_to_join_vc(interaction)
        current_player.queue.clear()
        current_player.current_track = None
        current_player.history.clear()
        tracks = [await wavelink.NodePool.get_node().build_track(cls=wavelink.GenericTrack, encoded=track_id)
                  for track_id in server.playlists[playlist].tracks
                  ]
        await current_player.add_to_queue(single=False, track=tracks)
        # await player.cycle_track()
        await current_player.play_next_track()
        await interaction.edit_original_response(content=f"Now playing playlist: `{playlist}`")

    @playlist_group.command(name="queue", description="adds the playlist to the end of the queue")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_queue(self, interaction: discord.Interaction, playlist: str):
        await interaction.response.defer()
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist")
            return
        current_player: OldPlayer = await self.attempt_to_join_vc(interaction)
        tracks = []

        tracks = [await wavelink.NodePool.get_node().build_track(cls=wavelink.GenericTrack, encoded=track_id)
                  for track_id in server.playlists[playlist].tracks
                  ]
        await current_player.add_to_queue(single=False, track=tracks)
        await interaction.edit_original_response(content=f"Added playlist: `{playlist}` to the queue")

    @staticmethod
    async def playlistDuration(tracks: list[str]):
        duration = 0
        for track_id in tracks:
            full_track = await wavelink.NodePool.get_node().build_track(cls=wavelink.GenericTrack, encoded=track_id)
            duration += full_track.duration

        hours, minutes, seconds = secondsDivMod(duration)
        value = f"{f'{hours:02}' + ':' if hours > 0 else ''}{minutes:02}:{seconds:02}"
        return value

    @playlist_group.command(name="list_all", description="lists all the server's playlists")
    async def playlist_list(self, interaction: discord.Interaction):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        await interaction.response.defer()

        playlist_count = len(server.playlists)

        info_text = f"{interaction.guild.name} has {playlist_count} {'playlists' if playlist_count > 1 else 'playlist'}"

        def shorten_name(name: str) -> str:
            length = len(name)
            if length > 28:
                if length <= 32:
                    new_name = name.ljust(32)
                else:
                    new_name = (name[:28] + " ...").ljust(32)
            else:
                new_name = name.ljust(32)
            return new_name


        if server.playlists:
            data = {
                shorten_name(playlist_name): {
                    "track_count": len(playlist.tracks),
                    "duration": await self.playlistDuration(playlist.tracks)
                }
                for playlist_name, playlist in server.playlists.items()
            }
        else:
            data = None


        pages = createPageList(info_text,
                               data,
                               playlist_count,
                               custom_reprs={
                                   "track_count": CustomRepr("Tracks"),
                                   "duration": CustomRepr("Duration")}
                               )

        # message = f"```swift\n{interaction.guild.name} Playlists:\n"
        # message += "\n".join([
        #     f"\t{shorten_name(playlist)}   :   tracks: {len(playlist.tracks)}" for playlist, playlist in
        #     server.playlists.items()
        # ])
        # message += "```"

        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(view=view)


    @playlist_group.command(name="show_tracks", description="shows what songs are in a playlist")
    @app_commands.autocomplete(playlist=playlist_autocomplete)
    async def playlist_show_tracks(self, interaction: discord.Interaction, playlist: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if playlist not in server.playlists.keys():
            await interaction.edit_original_response(content="Playlist does not exist")
            return


        playlist = server.playlists[playlist]
        track_count = len(playlist.tracks)


        async def buildTracks(tracks):
            _data = {}
            _duration = 0
            for _track_id in tracks:
                _full_track = await wavelink.NodePool.get_node().build_track(cls=wavelink.GenericTrack, encoded=_track_id)
                track_duration = int(_full_track.duration//1000)
                _duration += track_duration
                _data.update({_full_track.title: {"duration": secondsToTime(track_duration)}})
            return _data, _duration

        def secondsToTime(t):
            hours, minutes, seconds = secondsDivMod(t)
            value = f"{f'{hours:02}' + ':' if hours > 0 else ''}{minutes:02}:{seconds:02}"
            return value


        data, duration = await buildTracks(playlist.tracks)
        duration_text = secondsToTime(duration)

        info_text = f"{playlist.name} has {track_count} tracks and a runtime of {duration_text}"

        pages = createPageList(
            info_text=info_text,
            data=data,
            total_item_count=track_count,
            custom_reprs={
                "duration": CustomRepr("", "")
            },
            max_key_length=50
        )

        message = await(await interaction.edit_original_response(content=pages[0])).fetch()

        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(view=view)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload):
        player: OldPlayer = payload.player
        reason = payload.reason

        if reason == "REPLACED":
            return

        if reason == "FINISHED":
            if player.interrupted_by_sound:
                await player.resume_interrupted_track()
                return

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

        await player.start_current_track()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackEventPayload):
        player: OldPlayer = payload.player
        await player.play_next_track()
        # print("track exception\n")

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackEventPayload):
        player: OldPlayer = payload.player
        await player.play_next_track()
        # print("track stuck\n")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackEventPayload):
        track = payload.track
        player: OldPlayer = payload.player
        # track_title: str = str(player.source)
        #
        # if not player.source:
        #     track_title = track.title
        # await player.dj_channel.send(content=f"Now Playing **{track_title}**")




        track = player.current_track

        hours, minutes, seconds = secondsDivMod(int(track.duration // 1000))

        now_playing_text = f"**`NOW PLAYING ➤ {track.title}" \
                           f"  -  {f'{hours}:02' + ':' if hours > 0 else ''}{minutes:02}:{seconds:02}`**"

        if player.interrupted_by_sound:
            now_playing_text = f"`Playing a Sound`"

        if player.now_playing_message is None:
            player.now_playing_message = await player.dj_channel.send(content=now_playing_text)
        elif player.dj_channel.last_message_id == player.now_playing_message.id:
            await player.now_playing_message.edit(content=now_playing_text)
        else:
            new_message = await player.dj_channel.send(content=now_playing_text)
            await player.now_playing_message.delete()
            player.now_playing_message = new_message

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        server: Server = self.bot.fetch_server(member.guild.encoded)
        current_player: OldPlayer = member.guild.voice_client


        # print("state change")
        if before.channel is None:
            # print("joined a voice channel when previously not in one")
            return

        if current_player is None:
            # print("no voice client")
            return
        else:
            if before.channel == current_player.channel:
                if before.channel != after.channel:
                    # print("user left music channel")
                    if len(before.channel.members)-1 == 0:
                        # print("leaving")
                        await current_player.dj_channel.send(f"Everyone left `{before.channel.name}` so I left too")
                        await current_player.disconnect()
                    # else:
                    #     print("members remain")
                # else:
                #     print("user didn't leave")






async def setup(bot):
    music_cog = OldMusic(bot)
    # atexit.register(music_cog.save_server_data)
    await bot.add_cog(music_cog)
