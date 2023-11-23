import sys
import traceback

import discord
from discord import app_commands, Interaction
from discord.app_commands import CheckFailure, AppCommandError

from bot.utils.interactions import respond


class CustomCheck(CheckFailure):
    MESSAGE = "Failed Custom Check"
    def __init__(self, message: str | None=None, *args) -> None:
        message = message or self.MESSAGE
        super().__init__(message, *args)

class NoVoiceChannel(CustomCheck):
    MESSAGE = "Specify or join a voice channel"

class AlreadyInVC(CustomCheck):
    MESSAGE = "I am already in another voice channel"

class NotInVC(CustomCheck):
    MESSAGE = "I am not in a voice channel"

class NoVoiceClient(CustomCheck):
    MESSAGE = "There is currently no voice session"

class PlaylistNotFound(CustomCheck):
    MESSAGE = "There is no playlist with that name"

class PlaylistAlreadyExists(CustomCheck):
    MESSAGE = "There is already a playlist with that name"

async def on_app_command_error(interaction: Interaction, error: AppCommandError):
    if isinstance(error, CustomCheck):
        og_response = await respond(interaction, f"**{error}**")
    else:
        og_response = await interaction.original_response()
        await og_response.channel.send(content=f"**Command encountered an error:**\n"
                                               f"{error}")
        traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)

