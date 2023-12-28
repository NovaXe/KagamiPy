from math import ceil

import discord
from discord import app_commands, Interaction
from discord._types import ClientT
from discord.app_commands import autocomplete, Range, Transformer, Transform, Choice
from discord.ext import commands
from discord.ext.commands import GroupCog, Group

from bot.ext import errors
from bot.ext.ui.custom_view import MessageInfo
from bot.ext.ui.page_scroller import PageScroller, PageGenCallbacks, ITL
from bot.kagami_bot import Kagami
from bot.utils.bot_data import Sound, server_data
from bot.utils.interactions import respond
from bot.utils.pages import EdgeIndices, createSinglePage, InfoTextElem, InfoSeparators, CustomRepr, PageBehavior, \
    PageIndices
from bot.utils.utils import similaritySort, secondsToTime


class SoundTransformer(Transformer):
    def __init__(self, raise_error=True):
        self.raise_error = raise_error

    async def autocomplete(self,
                           interaction: Interaction,
                           value: str, /) -> list[Choice[str]]:
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



class SoundboardCog(commands.GroupCog, group_name="s"):
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
                    source: str, start: Range[float, 0, None], end: float=None):
        await respond(interaction, ephemeral=True)
        sound_name = interaction.namespace.sound
        if sound is not None:
            pass  # TODO Send overwrite confirmation buttons
        # if yes proceed to creating a new sound otherwise send a message dictating that the sound has been discarded
        new_sound = server_data.value.createNewSound(name=sound_name, source=source, start_time=start, end_time=end)

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
        name="view",
        description="view all of the server's sounds")
    async def s_view(self, interaction: Interaction):
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
                    "duration": secondsToTime(sound.end_time - sound.start_time)
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
                behavior=PageBehavior(max_key_length=40)
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
        message_text = f"""```swift
        Sound Info: `{interaction.namespace.sound}`
        ────────────────────────────────────────
        Track Title: {sound.title}
        
        ```"""
        await respond(interaction, message_text)


    @app_commands.command(
        name="stop",
        description="stops all sounds from playing")
    async def s_stop(self, interaction: Interaction):
        await respond(interaction)

    @app_commands.command(
        name="pop",
        description="pops the sounds from the player's sound queue")
    async def s_pop(self, interaction: Interaction, position: Range[int, 1, None]=1, count: int=1):
        await respond(interaction)


    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        await self.bot.setContextVars(interaction)


"""
add / delete sound
edit sound
stop command clears the soundboard queue and resumes normal playback


prioritized queue in the bot
sounds with start and stop times

"""