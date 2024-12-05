import collections
import dataclasses
import traceback
from typing import Any, Callable, Awaitable, Generator, Union
import sys

import discord
from discord import ButtonStyle, Interaction
import discord.ui as ui
from discord.ui import Item

from common.logging import setup_logging
from common.interactions import respond

logger = setup_logging(__name__)

@dataclasses.dataclass
class ScrollerState:
    user: discord.User
    message: discord.Message
    initial_offset: int
    relative_offset: int
    @property
    def offset(self):
        return self.initial_offset + self.relative_offset

T_Callback = Callable[[Interaction, ScrollerState], list[str]]
class Scroller(ui.View):
    def __init__(self, message: discord.Message, user: discord.User | discord.Member,
                 page_callback: Callable[[Interaction, ScrollerState], Awaitable[tuple[str, int, int]]],
                #  count_callback: Callable[[Interaction, ScrollerState], list[str]],
                #  margin_callback: Callable[[Interaction, ScrollerState], list[str]],
                 initial_offset=0,
                 timeout: float=300, timeout_delete_delay: float=3):
        """
        page_callback: Returns a string representing the page, and a boolean dictating whether the current page is the last
        initial_offset: What page index the scroller starts on
        timeout: How long until the view enters recovery
        recovery_time: If not 0, specifies how long you have to click on the message before it's deleted
        """
        super().__init__(timeout=timeout)
        self.message: discord.Message = message
        self.timeout_delete_delay = timeout_delete_delay
        self.user: discord.User = user
        self.initial_offset: int = initial_offset
        self.relative_offset: int = 0
        self.page_callback: Callable[[Interaction, ScrollerState], Awaitable[tuple[str, int, int]]] = page_callback

    def __copy__(self):
        scroller = Scroller(
            message=self.message, 
            user=self.user, 
            page_callback=self.page_callback, 
            initial_offset=self.initial_offset, 
            timeout=self.timeout
        )
        scroller.relative_offset = self.relative_offset
        return scroller

    @property
    def state(self):
        return ScrollerState(
            message=self.message,
            user=self.user,
            initial_offset=self.initial_offset,
            relative_offset=self.relative_offset
        )
    
    @property
    def offset(self):
        return self.initial_offset + self.relative_offset

    @property
    def buttons(self) -> Generator[ui.Button, None, None]:
        return (item for item in self.children if isinstance(item, ui.Button))
    
    def add_button(self, callback: Callable[[Interaction, ScrollerState], Awaitable[tuple[str, int]]], 
                   style: ButtonStyle=ButtonStyle.secondary, 
                   label: str=None, 
                   emoji: Union[discord.PartialEmoji, discord.Emoji, str]=None, 
                   row: int=None,
                   ephemeral: bool=False):

        class CustomButtom(ui.Button):
            def __init__(self): # All variables are from the wrapper method so proper initialization isn't needed, kinda hacky but really no different than bind
                super().__init__(self, style=style, label=label, emoji=emoji, row=row)
            
            async def callback(self, interaction: Interaction) -> Any:
                await respond(interaction, ephemeral=ephemeral)
                assert isinstance(self.view, Scroller) # Works under the assumption of the view having a state property
                await callback(interaction, self.view.state)
                await self.view.update() 
        self.add_button(CustomButtom())

    async def getPage(self, interaction: Interaction) -> tuple[str, int, int]:
        content, first_index, last_index = await self.page_callback(interaction, self.state)
        return content, first_index, last_index

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if interaction.user == self.user:
            return True
        await respond(interaction, f"Only {self.user.mention} can use this view", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(view=self, delete_after=self.timeout_delete_delay)
            except discord.NotFound:
                pass

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any], /) -> None:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        message = f"An error occurred while processing the interaction for {str(item)}:\n```py\n{tb}\n```"
        logger.error(message)
        await interaction.response.send_message(message)

    async def update(self, interaction: Interaction):
        content, first_index, last_index = await self.getPage(interaction)
        is_first = self.offset <= first_index
        is_last = self.offset >= last_index
        # print(f"{is_first=}, {is_last=}, {self.offset=}")

        self.first.disabled = is_first
        self.prev.disabled = is_first
        # TODO add an is_first return value that the callbacks must handle
        # this will allow for a queue with history to work properly as well
        self.next.disabled = is_last 
        self.last.disabled = is_last
        if is_last:
            self.relative_offset = last_index - self.initial_offset
        if is_first:
            self.relative_offset = first_index - self.initial_offset
        self.home.style = ButtonStyle.blurple 

        await self.message.edit(content=content, view=self) 

    @ui.button(emoji="⬆", custom_id="Scroller:first", row=0)
    async def first(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset = 0 - self.initial_offset
        await self.update(interaction)

    @ui.button(emoji="🔼", custom_id="Scroller:prev", row=0)
    async def prev(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset -= 1
        await self.update(interaction)

    @ui.button(emoji="*️⃣", custom_id="Scroller:home", style=ButtonStyle.blurple, row=0)
    async def home(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset = 0
        await self.update(interaction)

    @ui.button(emoji="🔽", custom_id="Scroller:next", row=0)
    async def next(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset += 1
        await self.update(interaction)
    
    @ui.button(emoji="⬇", custom_id="Scroller:last", row=0)
    async def last(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset = sys.maxsize
        await self.update(interaction)

    @ui.button(emoji="🗑", custom_id="Scroller:delete", row=4, style=ButtonStyle.red)
    async def delete(self, interaction: Interaction, button: ui.Button):
        await self.message.delete()
        self.stop()

