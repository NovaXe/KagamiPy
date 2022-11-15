import json
import os
from typing import List

import discord
import discord.utils
from discord.ext import commands
from discord import app_commands
from utils import modals
import random

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.ctx_menu = app_commands.ContextMenu(
            name="Reply",
            callback=self.msg_reply,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    @app_commands.command(name="echo", description="repeats the sender's message")
    async def msg_echo(self, interaction: discord.Interaction, string: str) -> None:
        channel: discord.channel = interaction.channel
        await channel.send(string)
        await interaction.response.send_message(content="echoed", ephemeral=True, delete_after=1)

    @app_commands.command(name="status", description="sets the custom status of the bot")
    async def set_status(self, interaction: discord.Interaction, status: str = None):
        await self.bot.change_presence(activity=discord.Game(name=status))
        await interaction.response.send_message("status changed", ephemeral=True, delete_after=1)

    @app_commands.command(name="color", description="lets you select any color from the server")
    async def color_role(self, interaction: discord.Interaction, color: str):
        role = discord.utils.get(interaction.guild.roles, name=color)
        user_roles = [role for role in interaction.user.roles if "C: " not in role.name]
        user_roles.append(role)
        await interaction.user.edit(roles=user_roles)
        await interaction.response.send_message(content="added role", ephemeral=True, delete_after=1)

    @color_role.autocomplete("color")
    async def color_role_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        colors = [role for role in interaction.guild.roles if "C: " in role.name]
        return [
            app_commands.Choice(name=color.name[3:], value=color.name)
            for color in colors if current.lower() in color.name.lower()
        ][:25]

    # context menu commands
    async def msg_reply(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.send_modal(modals.MessageReply(message))


async def setup(bot):
    await bot.add_cog(Fun(bot))
