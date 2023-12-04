import json
import os
import discord
import discord.utils
from discord.ext import commands
from discord import app_commands
from typing import Literal


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @app_commands.command(name="purge", description="deletes a number of messages")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, count: int = 5) -> None:
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.purge(limit=count)
        # await interaction.edit_original_response(content=f"Deleted {count} messages")
        await interaction.edit_original_response(content=f"Deleted {count} messages")

    @app_commands.command(name="role", description="gives or takes a role")
    @app_commands.default_permissions(manage_roles=True)
    async def role(self, interaction: discord.Interaction, mode: Literal["give", "take"], role: discord.Role, user: discord.Member=None):
        if user is None:
            user = interaction.user

        user_roles = user.roles
        if mode == "give":
            user_roles.append(role)
        elif mode == "take":
            user_roles.pop(role)
        await interaction.user.edit(roles=user_roles)
        await interaction.response.send_message(f"Gave role: '{role.name}' to {user.name}")




async def setup(bot):
    await bot.add_cog(Moderation(bot))
