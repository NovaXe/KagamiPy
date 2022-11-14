import json
import os
import discord
import discord.utils
from discord.ext import commands


class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    @commands.hybrid_command()
    async def echo(self, ctx, *args):
        await ctx.send(args)

