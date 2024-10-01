import collections
import dataclasses
import traceback
from typing import Any, Callable
from math import floor, ceil
import sys

import discord
from discord import ButtonStyle, Interaction
import discord.ui as ui
from discord.ui import Item

from common.interactions import respond



# class OwnedView(ui.View)
# class CustomView(ui.View)
# class PublicView(ui.View)


@dataclasses.dataclass
class ScrollerState:
    user: discord.User
    message: discord.Message
    initial_offset: int
    relative_offset: int

T_Callback = Callable[[Interaction, ScrollerState], list[str]]
class Scroller(ui.View):
    def __init__(self, message: discord.Message, user: discord.User,
                 page_callback: Callable[[Interaction, ScrollerState], list[str]],
                 count_callback: Callable[[Interaction, ScrollerState], list[str]],
                 initial_offset=0, max_page_size=10,
                 timeout: float=300):
        super().__init__(timeout=timeout)
        self.message: discord.Message = message
        self.user: discord.User = user
        self.initial_offset: int = initial_offset
        self.relative_offset = 0
        self.page_callback: Callable[[Interaction, ScrollerState], list[str]] = page_callback
        self.count_callback: Callable[[Interaction, ScrollerState], int] = count_callback 
        self.max_page_size = max_page_size

    # def getStatePayload(self):
    #     return ScrollerState(
    #         message=self.message,
    #         user=self.user,
    #         home_offset=self.initial_offset,
    #         relative_offset=self.relative_offset
    #     )

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
    def buttons(self):
        return (item for item in self.children if isinstance(item, ui.Button))
    
    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if interaction.user == self.user:
            return True

        await respond(interaction, f"Only {self.user.mention} can use this view", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        for button in self.children:
            button.disabled = True
        if self.message:
            await self.message.edit(view=self, delete_after=30)
# Instead of using delete after, I should instead have a system that changes the color of the buttons.
# That way the user of the message is able to click it to refresh the timer

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any], /) -> None:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        message = f"An error occurred while processing the interaction for {str(item)}:\n```py\n{tb}\n```"
        await interaction.response.send_message(message)

    async def update(self, interaction: Interaction):
        item_count = await self.count_callback(interaction, self.state)
        max_offset = ((item_count - self.initial_offset) // self.max_page_size) * self.max_page_size
        
        # 0 ............    i    ..... i + r  ..... max
        # -initial ..... initial ..... offset ..... max
        self.relative_offset = min(max(self.offset, -self.initial_offset), max_offset) - self.initial_offset
        # self.relative_offset *= self.max_page_size
        
        button: ui.Button
        for button in self.buttons:
            if button.custom_id == "Scroller:first":
                button.disabled = self.offset == 0
            elif button.custom_id == "Scroller:prev":
                button.disabled = self.offset == 0
            elif button.custom_id == "Scroller:home":
                button.disabled = self.relative_offset == 0
            elif button.custom_id == "Scroller:next":
                button.disabled = self.offset == max_offset
            elif button.custom_id == "Scroller:last":
                button.disabled = self.offset == max_offset

        items: list[str] = await self.page_callback(interaction, self.state)
        content = "\n".join(items)
        content = f"```\n{content}\n```"

        await self.message.edit(content=content, view=self)
    
    @ui.button(emoji="⬆", custom_id="Scroller:first")
    async def first(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset = 0 - self.initial_offset
        await self.update(interaction)

    @ui.button(emoji="🔼", custom_id="Scroller:prev")
    async def prev(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset -= self.max_page_size
        await self.update(interaction)

    @ui.button(emoji="*️⃣", custom_id="Scroller:home")
    async def home(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset = 0
        await self.update(interaction)

    @ui.button(emoji="🔽", custom_id="Scroller:next")
    async def next(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset += self.max_page_size
        await self.update(interaction)
    
    @ui.button(emoji="⬇", custom_id="Scroller:last")
    async def last(self, interaction: Interaction, button: ui.Button):
        await respond(interaction)
        self.relative_offset = sys.maxsize
        await self.update(interaction)



