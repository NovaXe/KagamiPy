import json
import os
import discord
import discord.utils
from discord.ext import commands
from discord import app_commands


class MessageReply(discord.ui.Modal, title="Message Reply"):
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    response = discord.ui.TextInput(label="Reply Text")

    async def on_submit(self, interaction: discord.Interaction):
        await self.message.reply(f"{self.response}")
        await interaction.response.defer(ephemeral=True)


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