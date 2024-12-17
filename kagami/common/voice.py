from readline import add_history
from typing import Any, Literal, cast
import asyncio

import discord
from discord import VoiceClient, VoiceChannel, ui, Interaction, ButtonStyle
from wavelink import Player, AutoPlayMode
from bot import Kagami
from common.utils import acstr, ms_timestamp

class PlayerSession(Player):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.autoplay = AutoPlayMode.partial
        self.status_bar: StatusBar | None = None

    def shift_queue(self, shift: int) -> int:
        assert self.queue.history is not None
        count: int = 0
        if shift > 0:
            tracks = self.queue[:shift]
            count = len(tracks)
            del self.queue[:shift]
            self.queue.history.put(tracks)
        elif shift < 0:
            shift = max(shift, -len(self.queue.history))
            tracks = self.queue.history[shift:]
            count = -len(tracks)
            del self.queue.history[shift:]
            self.queue._items = tracks + self.queue._items
        return count

    async def skipto(self, index: int) -> int:
        assert self.queue.history is not None
        new_index = self.shift_queue(index)
        if len(self.queue.history) > 0:
            await self.play(self.queue.history[-1], add_history=False)
        else:
            self.autoplay = AutoPlayMode.disabled
            await self.pause(True)
            # self._current = None
            await self.skip()
            self.autoplay = AutoPlayMode.partial
            # await self.pause(True)
        return new_index
    

class StatusBar(ui.View):
    type Button = ui.Button["StatusBar"]
    def __init__(self, message: discord.Message, style: str):
        super().__init__()
        self.message = message
        self.channel = message.channel
        self.style = style
        self.button_page = 0
        if style == "minimal":
            self.clear_items()


    def get_content(self) -> str:
        assert (guild:=self.message.guild) is not None, "Can't exist outside of a guild"
        assert (voice_client:=guild.voice_client) is not None, "Voice session must exist"
        session = cast(PlayerSession, voice_client)
        current_track = session.current
        rep = "Nothing is currently playing"
        if self.style == "minimal" or self.style == "remote":
            if current_track is not None:
                status = "Playing" if session.playing and not session.paused else ("Paused" if session.paused else "Stopped")
                rep = f"{acstr(status, 7)} {acstr(current_track.title, 60)} - {acstr(ms_timestamp(current_track.length), 8, just="r")}"
        elif self.style == "mini-queue":
            assert session.queue.history is not None, "There is no good reason the history shouldn't exist"
            history_len = len(session.queue.history)
            queue_len = len(session.queue)
            # handles the case where a track is playing and it is the same as the last history track
            # the only case where this isn't true is when playback has been interupted in some way
            # No reason to have the previous track listed as the currently playing track, that's retarded
            rep = ""
            if history_len > 0 and (track:=session.queue.history[-1]) != current_track:
                rep += f"{acstr("Prev", 7)} {acstr(track.title, 60)} - {acstr(ms_timestamp(track.length), 8, just="r")}"
                rep += "-------"
            elif history_len > 1:
                track = session.queue.history[-2]
                rep += f"{acstr("Prev", 7)} {acstr(track.title, 60)} - {acstr(ms_timestamp(track.length), 8, just="r")}"
                rep += "-------"

            if current_track is not None:
                status = "Playing" if session.playing and not session.paused else ("Paused" if session.paused else "Stopped")
                rep = f"{acstr(status, 7)} {acstr(current_track.title, 60)} - {acstr(ms_timestamp(current_track.length), 8, just="r")}"

            if queue_len > 0:
                track = session.queue[0]
                rep += "-------"
                rep += f"{acstr("Next", 7)} {acstr(track.title, 60)} - {acstr(ms_timestamp(track.length), 8, just="r")}"
        return rep


    async def resend(self) -> None:
        await asyncio.gather(self.message.delete(), self.channel.send(content=self.get_content()))

    async def update(self) -> None:
        await self.message.edit(content=self.get_content())

    # First row begins here
    @ui.button(emoji="⏪", style=ButtonStyle.green, row=0)
    async def rewind(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="⏯", style=ButtonStyle.green, row=0)
    async def play_pause(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="⏩", style=ButtonStyle.green, row=0)
    async def fastforward(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="🔁", style=ButtonStyle.primary, row=0)
    async def loop_mode(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="🔊", style=ButtonStyle.secondary, row=0)
    async def volume_up(self, interaction: Interaction, button: Button):
        pass

    # Second row begins here
    @ui.button(emoji="⏮️", style=ButtonStyle.green, row=1)
    async def skip_back(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="⏹️", style=ButtonStyle.green, row=1)
    async def stop_playback(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="⏭", style=ButtonStyle.green, row=1)
    async def skip_forward(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="🔎", style=ButtonStyle.primary, row=1)
    async def search(self, interaction: Interaction, button: Button):
        pass

    @ui.button(emoji="🔉", style=ButtonStyle.secondary, row=1)
    async def volume_down(self, interaction: Interaction, button: Button):
        pass
