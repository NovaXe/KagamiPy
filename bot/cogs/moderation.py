import json
import os
import discord
import discord.utils
from discord.ext import commands
from discord import app_commands


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @app_commands.command(name="purge", description="deletes a number of messages")
    async def purge(self, interaction: discord.Interaction, count: int = 5) -> None:
        # await interaction.response.defer(ephemeral=True)
        await interaction.channel.purge(limit=count)
        # await interaction.edit_original_response(content=f"Deleted {count} messages")
        await interaction.response.send_message(content=f"Deleted {count} messages", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
