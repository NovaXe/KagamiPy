from discord.app_commands import CheckFailure


class CustomCheck(CheckFailure):
    """
    The ephemeral flag on this error is checked when the error is handled by the global app_command handler. \
    When True it dictates that the error messsage sent to the user of the command is ephemeral
    """
    MESSAGE: str = "Failed Custom Check"
    EPHEMERAL: bool = True
    def __init__(self, message: str | None=None, *args) -> None:
        message = message or self.MESSAGE
        super().__init__(message, *args)

class NotImplementedYet(CustomCheck):
    MESSAGE = "Command not implemented yet, check back later"

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

class WrongVoiceClient(CustomCheck):
    MESSAGE = "Wrong command, try the other play command"

class MissingParameters(CustomCheck):
    MESSAGE = "You are missing required parameters"

