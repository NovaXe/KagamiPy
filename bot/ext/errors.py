import discord
from discord import app_commands
from discord.app_commands import CheckFailure


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