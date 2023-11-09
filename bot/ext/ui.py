from dataclasses import dataclass
from bot.kagami import Kagami
from discord import ui
from discord.ui import (View, Button, Select, TextInput)
from discord import (ButtonStyle, Interaction)
from typing import (Callable)
from bot.utils.music_utils import (createQueuePage, Player, attemptHaltResume)
from bot.ext.types import *





class CustomView(View):
    def __init__(self, *args, timeout: float | None = 120,
                 bot: Kagami, message_info: MessageInfo,
                 stop_behavior: StopBehavior = StopBehavior(disable_items=True),
                 **kwargs):
        super().__init__(timeout=timeout)
        self.bot: Kagami = bot
        self.m_info: MessageInfo = message_info
        self.stop_behavior = stop_behavior

    def partialMessage(self):
        m_id = self.m_info.id
        ch_id = self.m_info.channel_id
        return self.bot.getPartialMessage(m_id, ch_id)

    async def onStop(self):
        if self.stop_behavior.delete_message:
            if p_message := self.partialMessage():
                await p_message.delete()
        elif self.stop_behavior.remove_view:
            if p_message := self.partialMessage():
                await p_message.edit(view=None)
        elif self.stop_behavior.disable_items:
            item: Button | Select | TextInput
            for item in self.children:
                item.disabled = True


    async def stop(self):
        await self.onStop()

    async def on_timeout(self) -> None:
        await self.stop()

    async def deleteMessage(self):
        if p_message := self.partialMessage():
            await p_message.delete()





# TODO potential idea for PageScroller page refresh method
# Bundle the interaction into a payload datatype that contains other data too
# The Scroller doesn't need to know about those other bits of data
# The payload would be passed along to the callback for usage
# This would bypass the callback needing to know specific data
# Instead the payload simply holds a slew of info that may be useful for a callback
# This is so smart

class PageScroller(CustomView):
    def __init__(self, *args, bot: Kagami,
                 message_info: MessageInfo, page_callbacks: PageGenCallbacks, pages: list[str]=None,
                 timeout: int=180, **kwargs):
        super().__init__(*args, bot=bot, message_info=message_info,
                         timeout=timeout, stop_behavior=StopBehavior(delete_message=True),
                         **kwargs)
        self.pages: list[str] = pages
        self.page_callbacks = page_callbacks
        self.page_index = 0



    async def changePage(self, interaction: Interaction, page_index):
        p_message = self.partialMessage()
        if self.pages:
            left_edge, _ = self.lastPageIndices(interaction)
            adjusted_index = abs(left_edge) + page_index
            page = self.pages[adjusted_index] if adjusted_index < len(self.pages) else None
        else:
            page = self.page_callbacks.genPage(interaction=interaction, page_index=page_index)

        if page:
            await p_message.edit(content=page)

    async def refresh(self, interaction: Interaction):
        await self.changePage(interaction, self.page_index)

    def lastPageIndices(self, interaction: Interaction):
        return self.page_callbacks.getEdgeIndices(interaction=interaction)


    """
    how to keep track of last page
    track count is below 10
    or cant make the next page
    
    """

    @ui.button(emoji="⬆", style=ButtonStyle.gray, custom_id="MessageScroller:first", row=0)
    async def page_first(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        # get first page index
        # generate at index
        first, _ = self.lastPageIndices(interaction)
        self.page_index = first
        await self.changePage(interaction, first)

    @ui.button(emoji="🔼", style=ButtonStyle.gray, custom_id="MessageScroller:prev", row=0)
    async def page_prev(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        first, _ = self.lastPageIndices(interaction)

        if (index:=self.page_index-1) >= first:
            self.page_index = index
            await self.changePage(interaction, index)


    @ui.button(emoji="*️⃣", style=ButtonStyle.gray, custom_id="MessageScroller:home", row=0)
    async def page_home(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        self.page_index = 0
        await self.changePage(interaction, 0)

    @ui.button(emoji="🔽", style=ButtonStyle.gray, custom_id="MessageScroller:next", row=0)
    async def page_next(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        _, last = self.lastPageIndices(interaction)

        if (index := self.page_index + 1) <= last:
            self.page_index = index
            await self.changePage(interaction, index)

    @ui.button(emoji="⬇", style=ButtonStyle.gray, custom_id="MessageScroller:last", row=0)
    async def page_last(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        _, last = self.lastPageIndices(interaction)
        self.page_index = last
        await self.changePage(interaction, last)

    """
    page_counts:
        history: int = n
        upnext: int = m
        
    54321>0<12345
    -+-+-X-+-+-
    page #( 4 )
    page #(-4 )
    
    History: #1
    Up Next: #5
    """


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
                if voice_client.is_paused():
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
        await interaction.response.edit()
        await voice_client.cyclePlayPrevious()
        await self.refreshButtonState()

    @ui.button(emoji="⏹", style=ButtonStyle.green, custom_id="PlayerControls:stop")
    async def stop_playback(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await interaction.response.edit()
        await voice_client.stop(halt=True)
        await self.refreshButtonState()

    @ui.button(emoji="⏯", style=ButtonStyle.green, custom_id="PlayerControls:pause_play")
    async def pause_play(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await interaction.response.edit()
        await attemptHaltResume(interaction)
        if voice_client.is_paused():
            await voice_client.resume()
        else:
            await voice_client.pause()
        await self.refreshButtonState()

    @ui.button(emoji="⏭", style=ButtonStyle.green, custom_id="PlayerControls:skip")
    async def skip(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await interaction.response.edit()
        await voice_client.cyclePlayNext()
        await self.refreshButtonState()

    @ui.button(emoji="🔁", style=ButtonStyle.gray, custom_id="PlayerControls:loop")
    async def loop(self, interaction: Interaction, button: Button):
        voice_client: Player = interaction.guild.voice_client
        await interaction.response.edit()
        loop_mode = voice_client.loop_mode
        loop_mode = loop_mode.next()
        await self.refreshButtonState()


