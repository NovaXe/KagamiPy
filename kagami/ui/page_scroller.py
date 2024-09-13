from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from discord import Interaction, ui, ButtonStyle
from discord.ui import Button

from ui.custom_view import CustomView, StopBehavior, MessageInfo
from bot import Kagami
from common.interactions import respond


@dataclass
class PageGenCallbacks:
    genPage: Callable
    getEdgeIndices: Callable


class ITL(Enum):
    """
    Info Text Location Enum\n
    Values:
    TOP, MIDDLE, BOTTOM
    """
    TOP = auto()
    MIDDLE = auto()
    BOTTOM = auto()


class PageScroller(CustomView):
    def __init__(self, *args, bot: Kagami,
                 message_info: MessageInfo, page_callbacks: PageGenCallbacks, pages: list[str]=None, home_index:str=0,
                 timeout: int=180, **kwargs):
        super().__init__(*args, bot=bot, message_info=message_info,
                         timeout=timeout, stop_behavior=StopBehavior(delete_message=True),
                         **kwargs)
        self.pages: list[str] = pages
        self.page_callbacks = page_callbacks
        self.page_index = 0
        self.home_index = home_index
        self.last_interaction = None



    async def updatePage(self, interaction: Interaction=None):
        if interaction:
            self.last_interaction = interaction
        else:
            interaction = self.last_interaction
            # Probably a stupid idea

        p_message = self.partialMessage()
        if self.pages:
            left_edge, _ = self.lastPageIndices(interaction)
            adjusted_index = abs(left_edge) + self.page_index
            page = self.pages[adjusted_index] if adjusted_index < len(self.pages) else None
        else:
            page = self.page_callbacks.genPage(interaction=interaction, page_index=self.page_index)

        if page:
            await p_message.edit(content=page)

    async def refresh(self, interaction: Interaction):
        await self.updatePage(interaction)

    def lastPageIndices(self, interaction: Interaction):
        return self.page_callbacks.getEdgeIndices(interaction=interaction)


    """
    how to keep track of last page
    track count is below 10
    or cant make the next page
    
    """

    @ui.button(emoji="⬆", style=ButtonStyle.gray, custom_id="MessageScroller:first", row=0)
    async def page_first(self, interaction: Interaction, button: Button):
        await respond(interaction)
        # get first page index
        # generate at index
        first, _ = self.lastPageIndices(interaction)
        self.page_index = first
        await self.updatePage(interaction)

    @ui.button(emoji="🔼", style=ButtonStyle.gray, custom_id="MessageScroller:prev", row=0)
    async def page_prev(self, interaction: Interaction, button: Button):
        await respond(interaction)
        first, _ = self.lastPageIndices(interaction)

        if (index:=self.page_index-1) >= first:
            self.page_index = index
            await self.updatePage(interaction)


    @ui.button(emoji="*️⃣", style=ButtonStyle.gray, custom_id="MessageScroller:home", row=0)
    async def page_home(self, interaction: Interaction, button: Button):
        await respond(interaction)
        self.page_index = self.home_index
        await self.updatePage(interaction)

    @ui.button(emoji="🔽", style=ButtonStyle.gray, custom_id="MessageScroller:next", row=0)
    async def page_next(self, interaction: Interaction, button: Button):
        await respond(interaction)
        _, last = self.lastPageIndices(interaction)

        if (index := self.page_index + 1) <= last:
            self.page_index = index
            await self.updatePage(interaction)

    @ui.button(emoji="⬇", style=ButtonStyle.gray, custom_id="MessageScroller:last", row=0)
    async def page_last(self, interaction: Interaction, button: Button):
        await respond(interaction)
        _, last = self.lastPageIndices(interaction)
        self.page_index = last
        await self.updatePage(interaction)

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


# TODO potential idea for PageScroller page refresh method
# Bundle the interaction into a payload datatype that contains other data too
# The Scroller doesn't need to know about those other bits of data
# The payload would be passed along to the callback for usage
# This would bypass the callback needing to know specific data
# Instead the payload simply holds a slew of info that may be useful for a callback
# This is so smart

