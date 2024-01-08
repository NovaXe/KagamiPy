from math import ceil

import discord
import wavelink.ext.spotify
from discord import app_commands, Interaction
from discord._types import ClientT
from discord.app_commands import autocomplete, Range, Transformer, Transform, Choice
from discord.ext import commands
from discord.ext.commands import GroupCog, Group

from bot.ext import errors
from bot.ext.ui.custom_view import MessageInfo
from bot.ext.ui.page_scroller import PageScroller, PageGenCallbacks, ITL
from bot.kagami_bot import Kagami, bot_var
from bot.utils.bot_data import Sound, server_data
from bot.utils.interactions import respond
from bot.utils.pages import EdgeIndices, createSinglePage, InfoTextElem, InfoSeparators, CustomRepr, PageBehavior, \
    PageIndices
from bot.utils.player import Player
from bot.utils.utils import similaritySort, secondsToTime
from bot.utils.wavelink_utils import searchForTracks, WavelinkTrack
from bot.utils.music_utils import requireVoiceclient, attemptToJoin, attemptHaltResume


class SoundTransformer(Transformer):
    def __init__(self, raise_error=True):
        self.raise_error = raise_error

    async def autocomplete(self,
                           interaction: Interaction,
                           value: str, /) -> list[Choice[str]]:
        server_data.value = bot_var.value.getServerData(interaction.guild_id)
        soundboard_dict = server_data.value.soundboard
        keys = list(soundboard_dict.keys()) if len(soundboard_dict) else []
        options = similaritySort(keys, value)
        choices = [Choice(name=key, value=key) for key in options][:25]
        return choices

    async def transform(self, interaction: Interaction, value: str, /) -> Sound:
        soundboard_dict = server_data.value.soundboard

        if soundboard_dict and (sound:=soundboard_dict.get(value, None)):
            return sound
        else:
            if self.raise_error:
                raise errors.SoundNotFound
            else:
                return None



class SoundboardCog(commands.GroupCog, group_name="sound"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config


    Soundboard_Transformer = Transform[Sound, SoundTransformer]
    Soundboard_Transformer_NoError = Transform[Sound, SoundTransformer(raise_error=False)]

    @app_commands.command(
        name="add",
        description="add a sound to the server's soundboard")
    @app_commands.rename(sound="sound_name")
    async def s_add(self, interaction: Interaction,
                    sound: Soundboard_Transformer_NoError,
                    source: str, start: Range[float, 0, None]=0, end: float=None):
        await respond(interaction, ephemeral=True)
        sound_name = interaction.namespace.sound_name
        if sound is not None:
            pass  # TODO Send overwrite confirmation buttons
            pass  # if yes proceed to creating a new sound otherwise send a message dictating that the sound has been discarded
        tracks, _ = await searchForTracks(source)
        track = tracks[0]
        if isinstance(track, wavelink.ext.spotify.SpotifyTrack):
            raise errors.CustomCheck("Spotify links are not supported in the soundboard")
        start = start * 1000
        end = end * 1000 if end else None
        new_sound = server_data.value.createNewSound(name=sound_name, source=track, start_time=start, end_time=end)

        await respond(interaction, f"Added sound: `{sound_name}` to the soundboard")




    @app_commands.command(
        name="remove",
        description="removes a sound from the server's soundboard")
    async def s_remove(self, interaction: Interaction, sound: Soundboard_Transformer):
        await respond(interaction)
        soundboard = server_data.value.soundboard
        soundboard.pop(interaction.namespace.sound)
        await respond(interaction, f"Removed the sound `{sound.title}` from the soundboard", delete_after=3)

    @app_commands.command(
        name="list",
        description="list all of the server's sounds")
    async def s_list(self, interaction: Interaction):
        message = await respond(interaction)

        def edge_callback(interaction: Interaction) -> EdgeIndices:
            server_data = self.bot.getServerData(interaction.guild_id)
            sound_count = len(server_data.soundboard)
            page_count = ceil(sound_count/10)
            return EdgeIndices(left=0, right=page_count-1)

        def gen_callback(interaction: Interaction, page_index: int) -> str:
            server_data = self.bot.getServerData(interaction.guild_id)

            first_item_index = page_index * 10
            soundboard = dict(list(server_data.soundboard.items())[first_item_index:first_item_index + 10])

            info_text_elem = InfoTextElem(
                text=f"`{interaction.guild.name}` has `{len(server_data.soundboard)}` sounds in the soundboard",
                loc=ITL.TOP,
                separators=InfoSeparators(bottom="────────────────────────────────────────")
            )

            data = {
                sound_name: {
                    "duration": secondsToTime(
                        ((sound.end_time or sound.duration) - sound.start_time)//1000
                    )
                }
                for sound_name, sound in soundboard.items()
            }

            left, right = edge_callback(interaction)


            page = createSinglePage(
                data=data,
                infotext=info_text_elem,
                first_item_index=page_index*10 + 1,
                page_position=PageIndices(left, page_index, right),
                custom_reprs={
                    "encoded": CustomRepr(ignored=True),
                    "start_time": CustomRepr(ignored=True),
                    "end_time": CustomRepr(ignored=True)
                },
                behavior=PageBehavior(max_key_length=30)
            )

            return page

        view = PageScroller(
            bot=self.bot,
            page_callbacks=PageGenCallbacks(getEdgeIndices=edge_callback, genPage=gen_callback),
            message_info=MessageInfo.init_from_message(message)
        )
        await respond(interaction, content=gen_callback(interaction, 0), view=view)


    @app_commands.command(
        name="info",
        description="shows the sound's info")
    async def s_info(self, interaction: Interaction, sound: Soundboard_Transformer):
        await respond(interaction)
        message_text = f"```swift\n" \
                       f"Sound Info: `{interaction.namespace.sound}`\n" \
                       f"────────────────────────────────────────\n" \
                       f"Track Title: {sound.title}\n" \
                       f"Track Url: {'Unknown'}\n" \
                       f"Track Duration: {secondsToTime(sound.duration//1000)}\n" \
                       f"Playback Range: {secondsToTime(sound.start_time//1000)} -> {secondsToTime((sound.end_time or sound.duration)//1000)}\n" \
                       f"Playback Duration: {secondsToTime( ((sound.end_time or sound.duration)-sound.start_time)//1000)}\n" \
                       f"```"
        await respond(interaction, message_text)


    @app_commands.command(
        name="stop",
        description="stops all sounds from playing")
    async def s_stop(self, interaction: Interaction):
        await respond(interaction)

    @requireVoiceclient(begin_session=True)
    @app_commands.command(
        name="play",
        description="adds a sound to the sound queue")
    async def s_play(self, interaction: Interaction, sound: Soundboard_Transformer, play_now: bool=False):
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        track = await sound.buildWavelinkTrack()
        track.start_time = sound.start_time
        track.end_time = sound.end_time
        await voice_client.queueTracks("soundboard", track)
        await attemptHaltResume(interaction)
        await respond(interaction, f"Queued the sound: `{interaction.namespace.sound}`", delete_after=5)

    @requireVoiceclient()
    @app_commands.command(
        name="queue",
        description="shows the sound queue")
    async def s_queue(self, interaction: Interaction):
        messsage = await respond(interaction)

        def edge_callback(interaction: Interaction) -> EdgeIndices:
            server_data = self.bot.getServerData(interaction.guild_id)
            voice_client: Player = interaction.guild.voice_client
            queue_length = voice_client.sound_queue.count
            page_count = ceil(queue_length/10)
            return EdgeIndices(left=0, right=page_count-1)

        def gen_callback(interaction: Interaction, page_index: int) -> str:
            server_data = self.bot.getServerData(interaction.guild_id)
            voice_client: Player = interaction.guild.voice_client

            first_item_index = page_index * 10
            sound_queue = dict(list(voice_client.sound_queue.items()))[first_item_index:first_item_index + 10]
            info_text_elem = InfoTextElem(
                text=f"`There are {voice_client.sound_queue.count} queued sounds",
                loc=ITL.TOP,
                separators=InfoSeparators(bottom="────────────────────────────────────────")
            )

            data = {
                sound_name: {
                    "duration": secondsToTime(
                        ((sound.end_time or sound.duration) - sound.start_time)//1000
                    )
                }
                for sound_name, sound in sound_queue.items()
            }

            left, right = edge_callback(interaction)


            page = createSinglePage(
                data=data,
                infotext=info_text_elem,
                first_item_index=page_index*10 + 1,
                page_position=PageIndices(left, page_index, right),
                custom_reprs={
                    "encoded": CustomRepr(ignored=True),
                    "start_time": CustomRepr(ignored=True),
                    "end_time": CustomRepr(ignored=True)
                },
                behavior=PageBehavior(max_key_length=30)
            )

            return page

        view = PageScroller(
            bot=self.bot,
            page_callbacks=PageGenCallbacks(getEdgeIndices=edge_callback, genPage=gen_callback),
            message_info=MessageInfo.init_from_message(messsage)
        )
        await respond(interaction, content=gen_callback(interaction, 0), view=view)

    @requireVoiceclient()
    @app_commands.command(
        name="skip",
        description="skips the currently playing sound")
    async def s_skip(self, interaction: Interaction, count: Range[int, 1, None]=1):
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        if voice_client.currentlyPlaying() is voice_client.sound_queue.history[-1]:
            sound_queue_length = voice_client.sound_queue.count
            skip_count = max(min(count, sound_queue_length), 1)
            await voice_client.cycleQueue(min(count, skip_count))
            if voice_client.halted: await voice_client.stop()
            else: await voice_client.beginPlayback()

            await respond(interaction, f"Skipped `{skip_count} sound{'s' if skip_count > 1 else ''}`")
        else:
            await respond(interaction, "There are no sounds to skip", delete_after=3)

    @requireVoiceclient()
    @app_commands.command(
        name="pop",
        description="pops the sounds from the player's sound queue")
    async def s_pop(self, interaction: Interaction, position: Range[int, 1, None]=1, count: int=1):
        await respond(interaction)
        voice_client: Player = interaction.guild.voice_client
        sound_queue_length = voice_client.sound_queue.count
        if not sound_queue_length:
            raise errors.SoundQueueEmpty
        elif position > sound_queue_length:
            raise errors.CustomCheck(f"Queue: `0 -> {sound_queue_length}`: pos `{position}` out of range")

        tracks = list(reversed([voice_client.sound_queue.pop(i) for i in reversed(range(position-1, min(position-1+count, sound_queue_length)))]))
        if track_count:=len(tracks) > 1:
            await respond(interaction, f"Removed `{track_count}` tracks")
            # TODO make this a list scrolling thing even though it probably isn't necessary and no one cares
        else:
            await respond(interaction, f"Removed track `{tracks[0]}` from the sound queue")


    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        await self.bot.setContextVars(interaction)
        return True


"""
add / delete sound
edit sound
stop command clears the soundboard queue and resumes normal playback


prioritized queue in the bot
sounds with start and stop times

"""

async def setup(bot):
    soundboard_cog = SoundboardCog(bot)
    await bot.add_cog(soundboard_cog)
