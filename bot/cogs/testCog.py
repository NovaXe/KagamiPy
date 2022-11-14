import json
import os
import discord
import discord.utils
from discord.ext import commands
from discord import app_commands


class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @app_commands.command(name="echo", description="repeats the sender's message")
    async def echo(self, interaction: discord.interactions):
        await interaction.response.send_message()

    @app_commands.command(name="test", description="test reply")
    async def test(self, interaction: discord.interactions):
        await interaction.response.send_message("test")


async def setup(bot):
    await bot.add_cog(TestCog(bot))
