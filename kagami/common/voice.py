from code import interact
from typing import Any, Literal, cast
import asyncio

from urllib.parse import urlparse, parse_qs

import discord
from discord import VoiceClient, VoiceChannel, ui, ButtonStyle, TextStyle
from wavelink import Player, AutoPlayMode, QueueMode, Playable, Search
import wavelink
from bot import Kagami
from common.interactions import respond
from common.errors import CustomCheck
from common.utils import acstr, ms_timestamp
from common.types import MessageableGuildChannel

type Interaction = discord.Interaction[Kagami]

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

    async def search_and_queue(self, query: str) -> list[Playable] | wavelink.Playlist:
        results: Search = await Playable.search(query)
        if isinstance(results, wavelink.Playlist):
            parsed_query = cast(str, urlparse(results.url).query)
            params = parse_qs(parsed_query)
            if "v" in params.items():
                await self.queue.put_wait(results[results.selected])
            else:
                await self.queue.put_wait(results)
        else:
            await self.queue.put_wait(results[0])
        return results

class SearchQueryModal(ui.Modal, title="Search Query"):
    query: ui.TextInput["SearchQueryModal"] = ui.TextInput(label="Search Query", required=True, style=TextStyle.short)

    async def on_submit(self, interaction: Interaction, /) -> None:
        await respond(interaction)


class StatusBar(ui.View):
    type Button = ui.Button["StatusBar"]
    def __init__(self, channel: MessageableGuildChannel, style: str):
        super().__init__()
        self.message: discord.Message | None = None
        self.channel: MessageableGuildChannel = channel
        self.style: str = style
        self.seek_milliseconds: int = 5000
        if style == "minimal":
            self.clear_items()

    def get_content(self) -> str:
        assert (guild:=self.channel.guild) is not None, "Can't exist outside of a guild"
        assert (voice_client:=guild.voice_client) is not None, "Voice session must exist"
        session = cast(PlayerSession, voice_client)
        current_track = session.current
        rep = "```swift\nNothing is currently playing\n```"
        if self.style == "minimal" or self.style == "remote":
            if current_track is not None:
                status = "Playing" if session.playing and not session.paused else ("Paused" if session.paused else "Stopped")
                rep = f"```swift" + \
                f"\n{acstr(status, 7)} {acstr(current_track.title, 100)}" + \
                f"\n- Artist: {current_track.author}" + \
                f"\n- Duration: {ms_timestamp(current_track.length)}" + \
                "\n```"
        elif self.style == "mini-queue":
            assert session.queue.history is not None, "There is no good reason the history shouldn't exist"
            history_len = len(session.queue.history)
            queue_len = len(session.queue)
            # handles the case where a track is playing and it is the same as the last history track
            # the only case where this isn't true is when playback has been interupted in some way
            # No reason to have the previous track listed as the currently playing track, that's retarded
            rep = "```swift\n"
            if history_len > 0 and (track:=session.queue.history[-1]) != current_track:
                rep += f"\n{acstr("Prev", 7)} {acstr(track.title, 60)} - {acstr(ms_timestamp(track.length), 8, just="r")}"
                rep += "\n-------"
            elif history_len > 1:
                track = session.queue.history[-2]
                rep += f"\n{acstr("Prev", 7)} {acstr(track.title, 60)} - {acstr(ms_timestamp(track.length), 8, just="r")}"
                rep += "\n-------"
            if current_track is not None:
                status = "Playing" if session.playing and not session.paused else ("Paused" if session.paused else "Stopped")
                rep = f"```swift" + \
                f"\n{acstr(status, 7)} {acstr(current_track.title, 100)}" + \
                f"\n- Artist: {current_track.author}" + \
                f"\n- Duration: {ms_timestamp(current_track.length)}" + \
                "\n```"

            if queue_len > 0:
                track = session.queue[0]
                rep += "\n-------"
                rep += f"\n{acstr("Next", 7)} {acstr(track.title, 60)} - {acstr(ms_timestamp(track.length), 8, just="r")}"
            rep += "\n```"
        return rep

    async def resend(self) -> None:
        """
        Used to resend the status by by deleting the old and sending a new message
        """
        if self.message is not None:
            # print(f"{self.message.id=}")
            await self.message.delete()
            self.message = await self.channel.send(content=self.get_content(), view=self)
            # _, self.message = await asyncio.gather(old_message.delete(), self.channel.send(content=self.get_content()))
        else:
            self.message = await self.channel.send(content=self.get_content(), view=self)

    async def refresh(self) -> None:
        voice_client = self.channel.guild.voice_client
        if voice_client is None:
            await self.kill()
        else:
            if self.message != self.channel.last_message:
                await self.resend()
            else:
                await self.update()

    async def update(self) -> None:
        if self.message is None:
            return
        await self.message.edit(content=self.get_content(), view=self)

    async def kill(self) -> None:
        if self.message is not None:
            await self.message.delete()
        self.stop()

    # First row begins here
    @ui.button(emoji="⏪", style=ButtonStyle.green, row=0)
    async def rewind(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        if session.current:
            await session.seek(max(session.position - self.seek_milliseconds, 0))
        await self.update()

    @ui.button(emoji="⏯", style=ButtonStyle.green, row=0)
    async def play_pause(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
            # raise SessionInactive 
            # (in reference to raise SessionInactive) Note this may not work properly as it will edit the view message with the error message 
            # Consider changing the way the error handler works or something like that, maybe just send the error as a followup or reply instead of a proper error
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.pause(not session.paused)
        button.emoji = "▶️" if session.paused else "⏸️"
        await self.update()

    @ui.button(emoji="⏩", style=ButtonStyle.green, row=0)
    async def fastforward(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        if session.current:
            await session.seek(min(session.position + self.seek_milliseconds, session.current.length))
        await self.update()

    @ui.button(emoji="🔁", style=ButtonStyle.grey, row=0)
    async def loop_mode(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        match session.queue.mode:
            case QueueMode.normal:
                session.queue.mode = QueueMode.loop
                button.emoji = "🔂"
                button.style = ButtonStyle.blurple
            case QueueMode.loop:
                session.queue.mode = QueueMode.loop_all
                button.emoji = "🔁"
                button.style = ButtonStyle.blurple
            case QueueMode.loop_all:
                session.queue.mode = QueueMode.normal
                button.emoji = "🔁"
                button.style = ButtonStyle.grey
        await self.update()

    @ui.button(emoji="🔊", style=ButtonStyle.secondary, row=0)
    async def volume_up(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.set_volume(min(200, session.volume + 5))
        await self.update()

    # Second row begins here
    @ui.button(emoji="⏮️", style=ButtonStyle.green, row=1)
    async def skip_back(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.skipto(-1)
        await self.update()

    @ui.button(emoji="⏹️", style=ButtonStyle.green, row=1)
    async def stop_playback(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.pause(True)
        await session.seek(0)
        self.play_pause.emoji = "▶️"
        await self.update()

    @ui.button(emoji="⏭", style=ButtonStyle.green, row=1)
    async def skip_forward(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.skipto(1)
        await self.update()

    @ui.button(emoji="🔎", style=ButtonStyle.primary, row=1)
    async def search(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        modal = SearchQueryModal()
        await interaction.response.send_modal(modal)
        if (await modal.wait()):
            results = await session.search_and_queue(modal.query.value)
            if not results:
                await respond(interaction, "I couldn't find any tracks that matched",
                              send_followup=True, ephemeral=True, delete_after=5)
            else:
                # await session.queue.put_wait(results[0])
                if session.current is None:
                    await session.play(await session.queue.get_wait())
                await respond(interaction, f"Added {results[0]} to the queue", 
                              send_followup=True, ephemeral=True, delete_after=5)
        await self.update()

    @ui.button(emoji="🔉", style=ButtonStyle.secondary, row=1)
    async def volume_down(self, interaction: Interaction, button: Button):
        await respond(interaction)
        assert interaction.guild is not None
        if interaction.guild.voice_client is None:
            await self.kill()
        session = cast(PlayerSession, interaction.guild.voice_client)
        await session.set_volume(max(0, session.volume - 5))
        await self.update()
