import json
import os
import discord
import discord.utils
from bot.utils.utils import ClampedValue
from bot.utils.utils import clamp
from discord.ext import commands
from discord import app_commands

from bot.cogs.music import Server, Player



class MessageReply(discord.ui.Modal, title="Message Reply"):
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    response = discord.ui.TextInput(label="Reply Text")

    async def on_submit(self, interaction: discord.Interaction):
        await self.message.reply(f"{self.response}")
        await interaction.response.defer(ephemeral=True)


class PlayerControls(discord.ui.view):
    def __init__(self, server: Server):
        self.server = server


class MessageScroller(discord.ui.View):
    def __init__(self, message: discord.Message, pages: list[str], home_page: int = 0):
        super().__init__(timeout=300)
        self.message = message
        self.pages = pages
        self.home_page = home_page
        self.page_count = len(pages)
        self.current_page_number = home_page

    def update_pages(self, pages: list[str]):
        self.pages = pages
        self.page_count = len(pages)
        self.current_page_number = clamp(self.current_page_number, 0, self.page_count)

    async def update_message(self):
        await self.message.edit(content=self.pages[self.current_page_number])


    @discord.ui.button(emoji="⬆", style=discord.ButtonStyle.gray)
    async def page_first(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = 0
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="🔼", style=discord.ButtonStyle.gray)
    async def page_prev(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = clamp(self.current_page_number-1, 0, self.page_count-1)
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="*️⃣", style=discord.ButtonStyle.gray)
    async def page_home(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = self.home_page
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="🔽", style=discord.ButtonStyle.gray)
    async def page_next(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = clamp(self.current_page_number + 1, 0, self.page_count - 1)
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="⬇", style=discord.ButtonStyle.gray)
    async def page_last(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = len(self.pages) - 1
        await interaction.response.edit_message()
        await self.update_message()


    @discord.ui.button(emoji="🗑", style=discord.ButtonStyle.red)
    async def delete_scroller(self, interaction: discord.Interaction, button: discord.ui.button):
        await self.message.edit(view=None)
        self.stop()
        del self

    async def on_timeout(self) -> None:
        await self.message.edit(view=None)
        del self


class ScrollableMessageButtons(discord.ui.View):
    def __init__(self, message: discord.Message, full_content: str, pages: list[str] = None, home_page=1):
        super().__init__()
        self.message = message
        self.full_content = full_content
        self.home_page = home_page
        self.current_page = home_page
        self.page_count = 0
        self.pages = pages
        if not pages:
            self.initialize_pages()

    def update_content(self, new_content: str, pages: list[str] = None):
        self.full_content = new_content
        self.pages = pages
        if not pages:
            self.initialize_pages()

    def initialize_pages(self):
        # Not going to be robust, it is expected you handle splitting pages for multi-page messages
        line_split_content = self.full_content.split("\n")
        self.pages = [line_split_content[i:i+10] for i in range(0, len(line_split_content), 10)]
        self.page_count = len(self.pages)

    async def update_message(self):
        await self.message.edit(content=self.pages[self.current_page])


    @discord.ui.button(label="▲")
    async def page_up(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page = self.current_page+1 if self.current_page < self.page_count else self.page_count
        await self.update_message()
        await interaction.response.defer()

    @discord.ui.button(label="▼")
    async def page_down(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page = self.current_page - 1 if self.current_page > 1 else 1
        await self.update_message()

    @discord.ui.button(label="🏠")
    async def page_home(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page = self.home_page
        await self.update_message()

    @discord.ui.button(label="🡄")
    async def page_first(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page = 1
        await self.update_message()
        return

    @discord.ui.button(label="🡆")
    async def page_last(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page = self.page_count
        await self.update_message()
        return




# class MessageReact(discord.ui.Modal, title="Message React"):
#     def __init__(self, message: discord.Message):
#         super().__init__()
#         self.message = message
#
#     response = discord.ui.TextInput(label="Separate multiple emoji with a ','")
#
#     async def on_submit(self, interaction: discord.Interaction):
#         reactions_to_add = self.response.value.split(",")
#         for reaction in reactions_to_add:
#             await self.message.add_reaction(reaction)
#         await interaction.response.defer(ephemeral=True)


# class ScrollableMessage(discord.ui.Modal, title="Scrollable Message")
#     def __init__(self, message: discord.Message):
#         super().__init__()
#         self.message = message




# class ColorSelector(discord.ui.Modal, title="Color Selector"):
#     def __init__(self, guild: discord.Guild):
#         super().__init__()
#     name = discord.ui.
#
#     async def on_submit(self, interaction: discord.Interaction):