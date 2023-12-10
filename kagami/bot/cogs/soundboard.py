import discord
from discord import app_commands, Interaction
from discord._types import ClientT
from discord.app_commands import autocomplete, Range, Transformer, Transform, Choice
from discord.ext import commands
from discord.ext.commands import GroupCog, Group

from bot.ext import errors
from bot.kagami_bot import Kagami
from bot.utils.bot_data import Sound, server_data
from bot.utils.interactions import respond
from bot.utils.utils import similaritySort


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
                raise errors.PlaylistNotFound
            else:
                return None


class SoundboardCog(commands.GroupCog, group_name="s"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config

    @app_commands.command(
        name="add",
        description="add a sound to the server's soundboard")
    async def s_add(self, interaction: Interaction):
        await respond(interaction)

    @app_commands.command(
        name="remove",
        description="removes a sound from the server's soundboard")
    async def s_remove(self, interaction: Interaction, sound):
        await respond(interaction)

    @app_commands.command(
        name="view",
        description="view all of the server's sounds")
    async def s_view(self, interaction: Interaction):
        await respond(interaction)

    @app_commands.command(
        name="info",
        description="shows the sound's info")
    async def s_info(self, interaction: Interaction):
        await respond(interaction)

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