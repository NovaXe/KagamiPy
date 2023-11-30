import wavelink
from wavelink import TrackEventPayload
from wavelink.ext import spotify
from typing import (Literal, Any, Union, List)
from discord import (app_commands, Interaction, VoiceChannel, Message)
from discord.app_commands import Group, Transformer, Transform, Choice
from discord.ext.commands import GroupCog
from discord.ext import (commands, tasks)
from discord.utils import MISSING

from bot.ext.ui.custom_view import MessageInfo
from bot.ext.ui.page_scroller import PageScroller, PageGenCallbacks
from bot.utils.bot_data import Playlist, server_data

# context vars
from bot.kagami_bot import bot_var

from bot.utils.music_utils import (
    attemptHaltResume,
    createNowPlayingWithDescriptor, createQueuePage, secondsToTime, respondWithTracks)
from bot.utils.wavelink_utils import createNowPlayingMessage, searchForTracks
from bot.utils.player import Player
from bot.utils.wavelink_utils import WavelinkTrack
from bot.kagami_bot import Kagami
from bot.ext.ui.music import PlayerController
from bot.ext.responses import (PersistentMessage, MessageElements)
from bot.utils.interactions import respond
from bot.ext import errors
from bot.utils.pages import EdgeIndices, getQueueEdgeIndices
from bot.utils.utils import similaritySort


# General functions for music and playlist use
async def searchAndQueue(voice_client: Player, search):
    tracks, source = await searchForTracks(search, 1)
    await voice_client.waitAddToQueue(tracks)
    return tracks, source


async def joinVoice(interaction: Interaction, voice_channel: VoiceChannel):
    voice_client: Player = interaction.guild.voice_client
    if voice_client:
        await voice_client.move_to(voice_channel)
        voice_client = interaction.guild.voice_client
    else:
        voice_client = await voice_channel.connect(cls=Player())
    return voice_client


async def attemptToJoin(interaction: Interaction, voice_channel: VoiceChannel = None, send_response=True):
    voice_client: Player = interaction.guild.voice_client
    user_vc = user_voice.channel if (user_voice := interaction.user.voice) else None
    voice_channel = voice_channel or user_vc
    if not voice_channel: raise errors.NoVoiceChannel

    if voice_client and voice_client.channel == voice_channel:
        raise errors.AlreadyInVC("I'm already in the voice channel")

    if voice_client:
        pass
    # raise errors.AlreadyInVC

    else:
        voice_client = await joinVoice(interaction, voice_channel)
        if send_response: await respond(interaction, f"I have joined {voice_client.channel.name}")
    return voice_client


def requireVoiceclient(begin_session=False, defer_response=True):
    async def predicate(interaction: Interaction):
        if defer_response: await respond(interaction)
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            if begin_session:
                await attemptToJoin(interaction, send_response=False)
                return True
            else:
                raise errors.NoVoiceClient
        else:
            return True

    return app_commands.check(predicate)

class Music(GroupCog,
            group_name="m",
            description="commands relating to music playback"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config

    # music_group = app_commands.Group(name="m", description="commands relating to music playback")
    music_group = app_commands
    # music_group = Group(name="m", description="commands relating to the music player")

    # Wavelink Handling
    @tasks.loop(seconds=10)
    async def connectNodes(self):
        await self.bot.wait_until_ready()
        #  fix the config
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

    def cog_load(self):
        # tree = self.bot.tree
        # self._old_tree_error = tree.on_error
        # tree.on_error = on_app_command_error

        self.bot.loop.create_task(self.connectNodes())

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        message = f"Node: <{node.id}> is ready"
        print(message)
        await self.bot.logToChannel(message)

    # guild.voice_client = player
    # same fucking thing, don't forget it

    # Auto Queue Doesn't work for me
    # Make queue automatically cycle

    @music_group.command(name="join",
                         description="joins the voice channel")
    async def m_join(self, interaction: Interaction, voice_channel: VoiceChannel = None):
        voice_client: Player = await attemptToJoin(interaction, voice_channel)
        pass

    @music_group.command(name="leave",
                         description="leaves the voice channel")
    async def m_leave(self, interaction: Interaction):
        voice_client: Player = interaction.guild.voice_client
        if not voice_client: raise errors.NotInVC

        message = f"I have left {voice_client.channel}"
        await voice_client.disconnect()
        await respond(interaction, message)

    @requireVoiceclient(begin_session=True)
    @music_group.command(name="play",
                         description="plays the given song or adds it to the queue")
    async def m_play(self, interaction: Interaction, search: str = None):
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)
        if not search:
            if voice_client.is_paused():
                await voice_client.resume()
                await respond(interaction, "Resumed music playback")
                # await respond(interaction, ("Resumed music playback")
            else:
                await attemptHaltResume(interaction, send_response=True)
        else:
            tracks, _ = await searchAndQueue(voice_client, search)
            await respondWithTracks(self.bot, interaction, tracks)
            await attemptHaltResume(interaction)



    @requireVoiceclient()
    @music_group.command(name="skip",
                         description="skips the current track")
    async def m_skip(self, interaction: Interaction, count: int = 1):
        voice_client: Player = interaction.guild.voice_client

        # if not voice_client: raise errors.NotInVC
        skipped_count = await voice_client.cycleQueue(count)
        comparison_count = abs(count) if count > 0 else abs(count) + 1

        if skipped_count < comparison_count:
            await voice_client.stop(halt=True)
        else:
            if voice_client.halted:
                await voice_client.stop()
            else:
                # if voice_client.queue.history.count:
                await voice_client.beginPlayback()
                # else:
                #     await voice_client.cyclePlayNext()

        await respond(interaction, f"Skipped {'back ' if count < 0 else ''}{skipped_count} tracks")

    @requireVoiceclient(defer_response=False)
    @music_group.command(name="nowplaying",
                         description="shows the current song")
    async def m_nowplaying(self, interaction: Interaction, minimal: bool=None, move_status: bool=True):
        voice_client: Player = interaction.guild.voice_client
        # await respond(interaction, ephemeral=True)



        if voice_client.now_playing_message:
            msg_channel_id = voice_client.now_playing_message.channel_id

            # kill the fucker
            await voice_client.now_playing_message.halt()
            voice_client.now_playing_message = None

            async def disableRespond(): await respond(interaction, "`Disabled status message`", ephemeral=True, delete_after=3)

            if move_status:
                if interaction.channel.id != msg_channel_id:
                    await respond(interaction, f"`Moved status message to {interaction.channel.name}`", ephemeral=True, delete_after=3)
                elif minimal is not None:
                    await respond(interaction, f"`{'Enabled' if minimal else 'Disabled'} minimal mode`", ephemeral=True, delete_after=3)
                else:
                    await disableRespond()
                    return
            else:
                await disableRespond()
                return
        else:
            await respond(interaction, "`Enabled status message`", ephemeral=True, delete_after=3)




        message: Message = await interaction.channel.send(createNowPlayingWithDescriptor(voice_client, True, True))

        message_info = MessageInfo(id=message.id,
                                   channel_id=message.channel.id)
        if minimal:
            sep = False
            view=MISSING
        else:
            sep = True
            view = PlayerController(bot=self.bot,
                                    message_info=message_info,
                                    timeout=None)

        message_elems = MessageElements(content=message.content,
                                        view=view)

        def callback(guild_id: int, channel_id: int, message_elems: MessageElements) -> str:
            guild = self.bot.get_guild(guild_id)
            message = createNowPlayingWithDescriptor(voice_client=guild.voice_client,
                                                     formatting=False,
                                                     position=True)
            message_elems.content = message
            return message_elems


        voice_client.now_playing_message = PersistentMessage(self.bot,
                                                             guild_id=interaction.guild_id,
                                                             message_info=message_info,
                                                             message_elems=message_elems,
                                                             seperator=sep,
                                                             refresh_callback=callback,
                                                             persist_interval=5)
        voice_client.now_playing_message.begin()

        return

    @requireVoiceclient()
    @music_group.command(name="queue", description="shows the previous and upcoming tracks")
    async def m_queue(self, interaction: Interaction):
        voice_client: Player = interaction.guild.voice_client

        # assert isinstance(interaction.response, InteractionResponse)
        await respond(interaction)
        og_response = await interaction.original_response()
        message_info = MessageInfo(og_response.id,
                                   og_response.channel.id)

        # def pageGen(_voice_client: Player, page_index: int) -> str:
        #     if _voice_client:
        #         return createQueuePage(_voice_client.queue, page_index)
        #     else:
        #         return None
        #
        # def edgeIndices(_voice_client: Player) -> EdgeIndices:
        #     if _voice_client:
        #         return getEdgeIndices(_voice_client.queue)
        #     else:
        #         return None

        def pageGen(interaction: Interaction, page_index: int) -> str:
            voice_client: Player
            if voice_client := interaction.guild.voice_client:
                return createQueuePage(voice_client, page_index)
            else:
                return None

        def edgeIndices(interaction: Interaction) -> EdgeIndices:
            voice_client: Player
            if voice_client := interaction.guild.voice_client:
                return getQueueEdgeIndices(voice_client.queue)
            else:
                return None

        # partialPageGen = partial(pageGen, _voice_client=voice_client)
        # partialEdgeIndices = partial(edgeIndices, _voice_client=voice_client)
        #
        #
        # page_callbacks = PageGenCallbacks(genPage=partialPageGen,
        #                                   getEdgeIndices=partialEdgeIndices)

        page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)

        view = PageScroller(bot=self.bot,
                            message_info=message_info,
                            page_callbacks=page_callbacks,
                            timeout=300)
        home_text = pageGen(interaction=interaction, page_index=0)

        await og_response.edit(content=home_text, view=view)

    @requireVoiceclient()
    @music_group.command(name="loop", description="changes the loop mode, Off->All->Single")
    async def m_loop(self, interaction: Interaction, mode: Player.LoopType = None):
        voice_client: Player = interaction.guild.voice_client
        # TODO Loop needs to work properly

        voice_client.changeLoopMode(mode)
        await respond(interaction, f"Loop Mode:`{mode}`")

    @requireVoiceclient()
    @music_group.command(name="stop", description="Halts the playback of the current track, resuming restarts")
    async def m_stop(self, interaction: Interaction):
        await respond(interaction)
        # TODO Stop implements stopping via calling the halt function
        voice_client: Player = interaction.guild.voice_client
        await voice_client.stop(halt=True)
        await respond(interaction, "Stopped the Player")

    @requireVoiceclient()
    @music_group.command(name="seek", description="Seeks to the specified position in the track in seconds")
    async def m_seek(self, interaction: Interaction, position: float):
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        pos_milliseconds = position * 1000
        await voice_client.seek(pos_milliseconds)
        np, _ = voice_client.currentlyPlaying()
        duration_text = secondsToTime(np.length)
        if pos_milliseconds > np.length:
            new_pos = duration_text
        else:
            new_pos = secondsToTime(position)

        await respond(interaction, f"**Jumped to `{new_pos} / {duration_text}`**")

    @requireVoiceclient()
    @music_group.command(name="pop", description="Removes a track from the queue")
    async def m_pop(self, interaction: Interaction, position: int, source: Literal["history", "queue"]=None):
        await respond(interaction)
        # TODO Extend support for alternate queues, ie next up queue and soundboard queue
        voice_client: Player = interaction.guild.voice_client
        index = position - 1

        queue_source = "unknown queue"

        if position <= 0:
            queue_source = "history"
            track = voice_client.queue.history[index]
            del voice_client.queue.history[index]
        else:
            queue_source = "queue"
            track = voice_client.queue[index]
            del voice_client.queue[index]

        track_text =createNowPlayingMessage(track, position=None, formatting=False, show_arrow=False, descriptor_text='')
        reply = f"Removed `{track_text}` from `{queue_source}`"
        await respond(interaction, reply)

    @requireVoiceclient()
    @music_group.command(name="pause", description="Pauses the music player")
    async def m_pause(self, interaction: Interaction):
        # Pause calls the pause function from the player, functions as a toggle
        # This never needs to do anything fancy ever
        voice_client: Player = interaction.guild.voice_client
        if voice_client.is_paused():
            await voice_client.resume()
            await respond(interaction, "Resumed the player")
        else:
            await voice_client.pause()
            await respond(interaction, "Paused the player")

    @requireVoiceclient()
    @music_group.command(name="resume", description="Resumes the music player")
    async def m_resume(self, interaction: Interaction):
        # Resume which just calls resume on the player, effectively pause toggle alias
        voice_client: Player = interaction.guild.voice_client
        if voice_client.is_paused():
            await voice_client.resume()
            await respond(interaction, "Resumed playback")
        else:
            await attemptHaltResume(voice_client, send_response=True)

    @requireVoiceclient()
    @music_group.command(name="replay", description="Restarts the current song")
    async def m_replay(self, interaction: Interaction):
        # Contextually handles replaying based off of the current track progress
        # Tweak the replay vs restart cutoff based off feedback
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        np, pos = voice_client.currentlyPlaying()

        cutoff_pos = 15  # seconds
        if pos//1000 < cutoff_pos:
            await voice_client.cycleQueue(-1)
            await voice_client.beginPlayback()
            response = await respond(interaction, "Replaying the previous track")
        else:
            await voice_client.seek(0)
            response = await respond(interaction, "Restarted the current track")
        await response.delete(delay=3)


    @requireVoiceclient()
    @music_group.command(name="clear", description="Clears the selected queue")
    async def m_clear(self, interaction: Interaction, choice: Literal["queue", "history"]):
        # TODO Support multiple queue types, up next queue and soundboard queue for example
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        if choice == "queue":
            voice_client.queue.clear()
        elif choice == "history":
            voice_client.queue.history.clear()

        await respond(interaction, f"Cleared {choice}")



    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackEventPayload):
        player: Player = payload.player

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: TrackEventPayload):
        voice_client: Player = payload.player
        reason = payload.reason

        if voice_client.halted:
            return

        if reason == "REPLACED":
            # triggers on a skip when not halted
            # await voice_client.beginPlayback()
            return
        elif reason == "FINISHED":
            # triggers on actually finishing

            # Using early returns to create a priority order
            # if halted do jack shit
            # then handle interruptions

            if voice_client.interrupted:
                await voice_client.resumeInteruptedTrack()
                return

            await voice_client.cyclePlayNext()
        elif reason == "STOPPED:":
            # triggers on a typical skip where the track is stopped
            # via Player.stop()
            pass

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if interaction.guild.voice_client and not isinstance(interaction.guild.voice_client, Player):
            raise errors.WrongVoiceClient("`Incorrect command for Player, Try /<command> instead`")
        return True


# TODO Playlist Functionality needs a reimplementation
# Reuse as much stuff from the og implementation as it works quite well but try to clean it up
# IE replace in function checks with decorator checks for parameters to be correct
# New error types such as PlaylistDoesNotExist




# playlist commands
# create: Creates a new playlist
# create new: empty playlist
# create from_queue

# delete: deletes the playlist
# rename: change the playlist name
# edit tracks, order, add / remove
# add \/
# add queue: puts the entire queue at the end of the playlist
# add search: whatever search string is a passed is added
# pop: remove a track at a specific index

# play / queue: use priority param or something
# show \/
# show all
# show tracks

# def playlistExists(create_new=False):
#     async def predicate(inteaction: Interaction):

# assert isinstance(server_data, ServerData)

class PlaylistTransformer(Transformer):
    # def __init__(self, create_new: bool=False):
    #     self.create_new: bool = create_new
    # def __init__(self, bot: Kagami):
    #     self.bot: Kagami = bot

    async def autocomplete(self,
                           interaction: Interaction,
                           value: Union[int, float, str], /) -> List[Choice[str]]:

        # close_matches: dict[str, Playlist] = find_closely_matching_dict_keys(value, server_data.playlists, 25)
        server_data.value = bot_var.value.getServerData(interaction.guild_id)
        playlists = server_data.value.playlists
        keys = list(playlists.keys()) if len(playlists) else []
        # close_matches = find_closely_matching_list_elems(value, keys, 25)
        #
        # def match_to_split(key:str):
        #     words = key.split(' ')
        #     for word in words:
        #         if word.startswith(value):
        #             return key
        #
        #
        # starts_with = [match_to_split(key) for key in keys if match_to_split(key)]
        # in_lower = [key for key in keys if value.lower() in key.lower()]
        #
        # options = list(set(starts_with + close_matches + in_lower))

        options = similaritySort(keys, value)

        choices = [Choice(name=key, value=key) for key in options][:25]
        return choices

    # async def transform(self, interaction: Interaction, value: Any, /) -> tuple[str, Playlist]:
    #     if value in server_data.playlists.keys():
    #         return value, server_data.playlists[value]
    #     else:
    #         return value, None

    async def transform(self, interaction: Interaction, value: Any, /) -> Playlist:
        playlists = server_data.value.playlists
        if playlists and value in playlists.keys():
            return playlists[value]
        else:
            return None
            # if self.create_new:
            #     server_data.playlists[value] = ServerData
            #     createNewPlaylist(interaction, value)
            #     await respond(interaction, f"Created Playlist `{value}`")
            # else:
            #     raise errors.PlaylistNotFound




def createNewPlaylist(name: str, tracks: list[WavelinkTrack]=None):
    # TODO add a overwrite confirmation if a playlist already exists
    # Future functionality have a YES / NO choice for overwriting the old one
    # Send as an ephemeral followup to the original response with a view attached
    # Wait for a view response and timeout default to No after a little bit
    playlists = server_data.value.playlists
    if name in playlists.keys():
        raise errors.PlaylistAlreadyExists
    else:
        if tracks:
            new_playlist = Playlist.initFromTracks(tracks)
        else:
            new_playlist = Playlist()
    playlists[name] = new_playlist
    return new_playlist

class PlaylistCog(GroupCog,
                  group_name="p",
                  description="commands relating to music playlists"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        # self.playlist_transform = Transform[Playlist, PlaylistTransformer(bot=bot)]

    create = Group(name="create", description="creating playlists")
    add = Group(name="add", description="adding tracks to playlists")

    @create.command(name="new", description="create a new empty playlist")
    # @app_commands.rename(playlist_tuple="playlist")
    async def p_create_new(self, interaction: Interaction,
                           playlist: Transform[Playlist, PlaylistTransformer]):
        playlist_name = interaction.namespace.playlist
        createNewPlaylist(playlist_name)
        await respond(interaction, f"Created playlist `{playlist_name}`")

    @requireVoiceclient()
    @create.command(name="queue", description="creates a new playlist using the current queue as a base")
    async def p_create_queue(self, interaction: Interaction,
                             playlist: Transform[Playlist, PlaylistTransformer]):
        voice_client: Player = interaction.guild.voice_client
        playlist_name = interaction.namespace.playlist
        tracks = list(voice_client.queue.history) + list(voice_client.queue)
        createNewPlaylist(playlist_name, tracks)
        await respond(interaction, f"Created playlist `{playlist_name}` with `{len(tracks)} tracks`")


    async def p_delete(self, interaction: Interaction, playlist: str):
        pass

    # this shit needs an autocomplete for the playlist parameter
    async def p_play(self, interaction: Interaction, playlist: str):
        pass

    def setServerDataVar(self, interaction: Interaction):
        server_data.value = self.bot.getServerData(interaction.guild_id)

    async def interaction_check(self, interaction: Interaction):
        self.setServerDataVar(interaction)
        return True
    # async def autocomplete_check


# Music Related Classes


async def setup(bot):
    music_cog = Music(bot)
    playlist_cog = PlaylistCog(bot)
    await bot.add_cog(music_cog)
    await bot.add_cog(playlist_cog)
