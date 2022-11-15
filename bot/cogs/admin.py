import json
import os
import discord
import discord.utils
from discord.ext import commands
from discord import app_commands


def is_developer():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == json.load(open("bot/data/config.json"))["developer"]
    return app_commands.check(predicate)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @commands.hybrid_command(name="sync", description="syncs the command tree")
    @is_developer()
    async def sync_command_tree(self, ctx):
        await self.bot.tree.sync()
        await ctx.send("Command Tree Synced", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
