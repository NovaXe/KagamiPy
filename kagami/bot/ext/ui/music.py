from discord import ui
from discord.ui import (Modal)
from discord import (ButtonStyle, Interaction)

from bot.utils.interactions import respond
from bot.utils.music_utils import (attemptHaltResume, respondWithTracks, addedToQueueMessage)
from bot.utils.wavelink_utils import searchForTracks
from bot.utils.player import Player
from bot.ext.ui.custom_view import *


class PlayerController(CustomView):
    def __init__(self, *args, bot: Kagami,
                 message_info: MessageInfo, timeout: int=None, **kwargs):
        super().__init__(*args, bot=bot, message_info=message_info, timeout=timeout, **kwargs)


    async def refreshButtonState(self):
        p_message = self.partialMessage()
        voice_client: Player = p_message.guild.voice_client
        for item in self.children:
            assert isinstance(item, Button)

            if item.custom_id == "PlayerControls:pause_play":
                if voice_client.is_paused() or voice_client.halted:
                    item.emoji = "▶"
                else:
                    item.emoji = "⏸"
            elif item.custom_id == "PlayerControls:loop":
                loop_mode = voice_client.loop_mode
                NO_LOOP = loop_mode.NO_LOOP
                LOOP_ALL = loop_mode.LOOP_ALL
                LOOP_TRACK = loop_mode.LOOP_TRACK
                if loop_mode == NO_LOOP:
                    item.emoji = "🔁"
                    item.style = ButtonStyle.gray
                elif loop_mode == LOOP_ALL:
                    item.emoji = "🔁"
                    item.style = ButtonStyle.blurple
                elif loop_mode == LOOP_TRACK:
                    item.emoji = "🔂"
                    item.style = ButtonStyle.blurple

        await p_message.edit(view=self)




    @ui.button(emoji="⏮", style=ButtonStyle.green, custom_id="PlayerControls:skip_back")
    async def skip_back(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)
        await voice_client.cyclePlayPrevious()
        await self.refreshButtonState()

    @ui.button(emoji="⏹", style=ButtonStyle.green, custom_id="PlayerControls:stop")
    async def stop_playback(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)
        await voice_client.stop(halt=True)
        await self.refreshButtonState()

    @ui.button(emoji="⏯", style=ButtonStyle.green, custom_id="PlayerControls:pause_play")
    async def pause_play(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)

        if voice_client.halted:
            await attemptHaltResume(interaction)
        elif voice_client.is_paused():
            await voice_client.resume()
        else:
            await voice_client.pause()
        await self.refreshButtonState()

    @ui.button(emoji="⏭", style=ButtonStyle.green, custom_id="PlayerControls:skip")
    async def skip(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)
        await voice_client.cyclePlayNext()
        await self.refreshButtonState()

    @ui.button(emoji="🔁", style=ButtonStyle.gray, custom_id="PlayerControls:loop")
    async def loop(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)
        voice_client.loop_mode = voice_client.loop_mode.next()
        await self.refreshButtonState()

    @ui.button(emoji="🔎", style=ButtonStyle.blurple, custom_id="PlayerControls:search")
    async def search(self, interaction: Interaction, button: Button):
        # await interaction.response.edit_message()
        await interaction.response.send_modal(SearchModal(self.bot))


class SearchModal(Modal, title="Search Prompt"):
    def __init__(self, bot: Kagami):
        super().__init__()
        self.bot = bot

    search = TextInput(label="Search Query")

    async def on_submit(self, interaction: Interaction, /) -> None:
        voice_client: Player = interaction.guild.voice_client
        await respond(interaction)
        tracks, _ = await searchForTracks(self.search.value)
        track_count = len(tracks)
        duration = sum([track.duration for track in tracks])
        await voice_client.waitAddToQueue(tracks)
        info_text = addedToQueueMessage(track_count, duration)
        await respondWithTracks(self.bot, interaction, tracks, info_text=info_text, followup=True, timeout=30)
        await attemptHaltResume(interaction)