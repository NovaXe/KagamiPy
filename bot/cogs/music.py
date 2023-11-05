import asyncio
import copy
import functools
import math
import sys
import traceback
from functools import partial

import wavelink
from wavelink import TrackEventPayload
from wavelink.ext import spotify
from enum import (
    Enum, auto
)
import discord
from discord import (utils, app_commands, Interaction, InteractionResponse, VoiceChannel, Message, InteractionMessage)
from discord.app_commands import AppCommandError
from discord.ext import (commands, tasks)
from collections import namedtuple
from bot.utils.music_utils import *
from bot.utils.utils import (createPageInfoText, createPageList)
from bot.ext.types import *
from bot.utils.ui import (MessageScroller, QueueController)
from bot.ext.smart_functions import (respond)
from bot.ext import (errors, ui)


# assert type(Interaction.response) is InteractionResponse

class Music(commands.GroupCog,
            group_name="m",
            description="commands relating to music playback"):
    def __init__(self, bot):
        self.bot:Kagami = bot
        self.config = bot.config

    # music_group = app_commands.Group(name="m", description="commands relating to music playback")
    playlist_group = app_commands.Group(name="playlist", description="commands relating to music playlists")
    music_group = app_commands

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
        tree = self.bot.tree
        self._old_tree_error = tree.on_error
        tree.on_error = self.on_app_command_error


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



    @staticmethod
    async def attemptToJoin(interaction: Interaction, voice_channel:VoiceChannel=None, send_response=True):
        voice_client: Player = interaction.guild.voice_client
        user_vc = user_voice.channel if (user_voice:=interaction.user.voice) else None
        voice_channel = voice_channel or user_vc
        if not voice_channel: raise errors.NoVoiceChannel

        if voice_client and voice_client.channel == voice_channel:
            raise errors.AlreadyInVC("I'm already in the voice channel")


        if voice_client: pass
            # raise errors.AlreadyInVC

        else:
            voice_client = await Music.joinVoice(interaction, voice_channel)
            if send_response: await respond(interaction, f"I have joined {voice_client.channel.name}")
        return voice_client

    @staticmethod
    async def joinVoice(interaction: Interaction, voice_channel:VoiceChannel):
        voice_client: Player = interaction.guild.voice_client
        if voice_client:
            await voice_client.move_to(voice_channel)
            voice_client = interaction.guild.voice_client
        else:
            voice_client = await voice_channel.connect(cls=Player())
        return voice_client

    @staticmethod
    def requireVoiceclient(begin_session=False, defer_response=True):
        async def predicate(interaction: Interaction):
            if defer_response: await respond(interaction)
            voice_client = interaction.guild.voice_client

            if voice_client is None:
                if begin_session:
                    await Music.attemptToJoin(interaction, send_response=False)
                    return True
                else:
                    raise errors.NoVoiceClient
            else:
                return True
        return app_commands.check(predicate)


    @music_group.command(name="join",
                         description="joins the voice channel")
    async def m_join(self, interaction: Interaction, voice_channel: VoiceChannel=None):
        voice_client: Player = await self.attemptToJoin(interaction, voice_channel)
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
    async def m_play(self, interaction: Interaction, search: str=None):
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)

        # if voice_client is None:
        #     if search:
        #         voice_client = await self.attemptToJoin(interaction, interaction.user.voice.channel, send_response=False)
        #     else:
        #         voice_client = await self.attemptToJoin(interaction, interaction.user.voice.channel)
        #         return

        # if voice_client.halted:
        #     voice_client.halt(False)


        if not search:
            if voice_client.is_paused():
                await voice_client.resume()
                await respond(interaction, "Resumed music playback")
                # await respond(interaction, ("Resumed music playback")
        else:
            tracks, source = await searchForTracks(search, 1)
            await voice_client.waitAddToQueue(tracks)
            data, duration = trackListData(tracks)
            track_count = len(tracks)
            if track_count > 1:
                info_text = f"{track_count} tracks with a duration of {secondsToTime(duration // 1000)} were added to the queue"
                pages = createPageList(info_text=info_text,
                                       data=data,
                                       total_item_count=track_count,
                                       custom_reprs={
                                           "duration": CustomRepr("", "")
                                       },
                                       max_key_length=50,
                                       sort_items=False)
                message = await (await interaction.original_response()).fetch()
                view = MessageScroller(message=message, pages=pages, home_page=0)
                await respond(interaction, content=pages[0], view=view)
            else:
                await respond(interaction,
                              content=f"`{tracks[0].title}  -  {secondsToTime(tracks[0].length // 1000)} was added to the queue`")

        # return
        if voice_client.halted:
            await voice_client.cyclePlayNext()
            await asyncio.sleep(1)
            # await voice_client.cyclePlayNext()
            # return
            track, pos = voice_client.currentlyPlaying()
            if track is None:
                await voice_client.beginPlayback()

            # await respond(interaction, f"`Began Playback`")






        #
        # if voice_client.currentlyPlaying()[0] is None:
        #     await voice_client.cycleQueue()
        #     await voice_client.beginPlayback()
        #
        # if voice_client.currentlyPlaying()[0] is None:
        #     await voice_client.beginNext()





    @requireVoiceclient()
    @music_group.command(name="skip",
                         description="skips the current track")
    async def m_skip(self, interaction: Interaction, count: int=1):
        voice_client: Player = interaction.guild.voice_client

        # if not voice_client: raise errors.NotInVC
        skipped_count = await voice_client.cycleQueue(count)
        comparison_count = abs(count) if count > 0 else abs(count)+1

        if skipped_count < comparison_count:
            await voice_client.haltPlayback()
        else:
            if voice_client.halted:
                await voice_client.stop()
            else:
                # if voice_client.queue.history.count:
                await voice_client.beginPlayback()
                # else:
                #     await voice_client.cyclePlayNext()

        await respond(interaction, f"Skipped {'back' if count<0 else ''}{skipped_count} tracks")



    @requireVoiceclient(defer_response=False)
    @music_group.command(name="nowplaying",
                         description="shows the current song")
    async def m_nowplaying(self, interaction: Interaction):
        voice_client: Player = interaction.guild.voice_client
        # await respond(interaction, ephemeral=True)

        if voice_client.np_message_id is None:
            channel = interaction.channel
            response = "`Enabled the NowPlaying message`"
            await respond(interaction, response, ephemeral=True, delete_after=3)
            msg: InteractionMessage = await channel.send( createNowPlayingMessage(*voice_client.currentlyPlaying()))
            voice_client.setNowPlayingInfo(msg.channel.id, msg.id)
            await self.nowplayingMessage.start(voice_client)
        else:
            response = "`Disabled the NowPlaying message`"
            await respond(interaction, response, ephemeral=True, delete_after=3)
            self.nowplayingMessage.cancel()
            channel = discord.utils.get(voice_client.guild.text_channels, id=voice_client.np_channel_id)
            message = channel.get_partial_message(voice_client.np_message_id)
            try:
                await message.delete()
            except discord.NotFound:
                pass
            voice_client.setNowPlayingInfo()

        await respond(interaction, content=response)
        # og_response = await interaction.original_response()
        # await og_response.edit(content=response)
        # await og_response.delete(delay=3)




    @tasks.loop(seconds=5)
    async def nowplayingMessage(self, voice_client: Player):
        np_text = createNowPlayingMessage(*voice_client.currentlyPlaying())
        channel = discord.utils.get(voice_client.guild.text_channels, id=voice_client.np_channel_id)
        message_id = voice_client.np_message_id
        try:
            message = await channel.get_partial_message(message_id).fetch()
        except discord.NotFound:
            message = None

        last_message_id = channel.last_message_id


        async def sendNewMessage(ch):
            msg: InteractionMessage = await ch.send(np_text)
            voice_client.setNowPlayingInfo(msg.channel.id, msg.id)


        if not message:
            await sendNewMessage(channel)
        elif message.id != last_message_id:
            await asyncio.gather(
                message.delete(),
                sendNewMessage(channel)
            )
        else:
            await message.edit(content=np_text)


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
                return getEdgeIndices(voice_client.queue)
            else:
                return None

        # partialPageGen = partial(pageGen, _voice_client=voice_client)
        # partialEdgeIndices = partial(edgeIndices, _voice_client=voice_client)
        #
        #
        # page_callbacks = PageGenCallbacks(genPage=partialPageGen,
        #                                   getEdgeIndices=partialEdgeIndices)

        page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)

        view = ui.PageScroller(bot=self.bot,
                               message_info=message_info,
                               page_callbacks=page_callbacks)
        home_text = pageGen(interaction=interaction, page_index=0)

        await og_response.edit(content=home_text, view=view)

    @requireVoiceclient()
    @music_group.command(name="loop", description="changes the loop mode, Off->All->Single")
    async def m_loop(self, interaction: Interaction, mode: Player.LoopType=None):
        voice_client:Player = interaction.guild.voice_client
        voice_client.changeLoopMode(mode)
        await respond(interaction, f"Loop Mode:`{mode}`")



    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        if isinstance(error, errors.CustomCheck):
            og_response = await respond(interaction, f"**{error}**")
        else:
            og_response = await interaction.original_response()
            await og_response.channel.send(content=f"**Command encountered an error:**\n"
                                                   f"{error}")
            traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)


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







# Music Related Classes




async def setup(bot):
    music_cog = Music(bot)
    await bot.add_cog(music_cog)
