import collections
import dataclasses
import traceback
from typing import Any, Callable

import discord
from discord import ButtonStyle, Interaction
import discord.ui as ui
from discord.ui import Item

from interactions import respond



# class OwnedView(ui.View)
# class CustomView(ui.View)
# class PublicView(ui.View)


@dataclasses.dataclass
class ScrollerState:
    user: discord.User
    message: discord.Message
    home_offset: int
    relative_offset: int


class Scroller(ui.View):
    def __init__(self, message: discord.Message, user: discord.User,
                 page_callback: Callable[[Interaction, ScrollerState], list[str]],
                 home_offset=0,
                 timeout: float=300):
        super().__init__(timeout=timeout)
        self.message: discord.Message = message
        self.user: discord.User = user
        self.home_offset: int = home_offset
        self.relative_offset = 0

    def getStatePayload(self):
        return ScrollerState(
            message=self.message,
            user=self.user,
            home_offset=self.home_offset,
            relative_offset=self.relative_offset
        )

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

    @ui.button(emoji="⬆")
    async def first(self, interaction: Interaction, button: ui.Button):
        pass



    async def home(self, interaction: Interaction, button: ui.Button):




