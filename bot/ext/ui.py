from dataclasses import dataclass
from bot.kagami import Kagami
from discord import ui
from discord.ui import (View, Button, Select, TextInput)
from discord import (ButtonStyle, Interaction)
from typing import (Callable)
from bot.ext.types import *





class CustomView(View):
    def __init__(self, *args, timeout: float | None = 180,
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
        if self.stop_behavior.remove_view:
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
                 message_info: MessageInfo, page_callbacks: PageGenCallbacks, **kwargs):
        super().__init__(*args, bot=bot, message_info=message_info,
                         **kwargs)
        self.pages: list[str] = []
        self.page_callbacks = page_callbacks
        self.page_index = 0


    async def refresh(self, interaction: Interaction):
        await self.changePage(interaction, self.page_index)

    async def changePage(self, interaction: Interaction, page_index):
        p_message = self.partialMessage()
        page = self.page_callbacks.genPage(interaction=interaction, page_index=page_index)
        if page:
            await p_message.edit(content=page)

    async def refresh(self, interaction: Interaction):
        await self.changePage(interaction, self.page_index)

    def lastPageIndices(self, interaction: Interaction):
        return self.page_callbacks.getEdgeIndices(interaction=interaction)


    # TODO potential idea for PageScroller page refresh method
    # Bundle the interaction into a payload datatype that contains other data too
    # The Scroller doesn't need to know about those other bits of data
    # The payload would be passed along to the callback for usage
    # This would bypass the callback needing to know specific data
    # Instead the payload simply holds a slew of info that may be useful for a callback
    # This is so smart

    @ui.button(emoji="⬆", style=ButtonStyle.gray, custom_id="MessageScroller:first", row=0)
    async def page_first(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        # get first page index
        # generate at index
        first, last = self.lastPageIndices(interaction)
        self.page_index = first
        await self.changePage(interaction, first)

    @ui.button(emoji="🔼", style=ButtonStyle.gray, custom_id="MessageScroller:prev", row=0)
    async def page_prev(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        first, last = self.lastPageIndices(interaction)

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
        first, last = self.lastPageIndices(interaction)

        if (index := self.page_index + 1) <= last:
            self.page_index = index
            await self.changePage(interaction, index)

    @ui.button(emoji="⬇", style=ButtonStyle.gray, custom_id="MessageScroller:last", row=0)
    async def page_last(self, interaction: Interaction, button: Button):
        await interaction.response.edit_message()
        first, last = self.lastPageIndices(interaction)
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

