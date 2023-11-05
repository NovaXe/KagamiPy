import json
import os
import sys
import traceback

import discord
import discord.utils
from discord.ext import commands
from discord import app_commands
from bot.kagami import Kagami


def is_developer():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == json.load(open("bot/data/config.json"))["developer"]
    return app_commands.check(predicate)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config

    @commands.command(name="sync", description="syncs the command tree")
    @commands.is_owner()
    async def sync_command_tree(self, ctx):
        await self.bot.tree.sync()
        await ctx.send("Command Tree Synced", ephemeral=True)

    @commands.command(name="ping", description="checks the latency")
    @commands.is_owner()
    async def ping(self, ctx):
        latency = int(self.bot.latency * 1000)
        await ctx.send(f"Pong! {latency}ms")

    @commands.command(name="reload_all", description="reloads all cogs")
    @commands.is_owner()
    async def reload_all_cogs(self, ctx):
        for file in os.listdir("bot/cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                await self.bot.reload_extension(f"cogs.{name}")
        await ctx.send("Reloaded all cogs")

    @commands.command(name="reload", description="reloads a  cog")
    @commands.is_owner()
    async def reload_cog(self, ctx, cog_name):
        for file in os.listdir("bot/cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                if name.lower() == cog_name.lower():
                    await self.bot.reload_extension(f"cogs.{name}")
                    break
        else:
            await ctx.send(f"No cog with that name could be found")
            return
        await ctx.send(f"Reloaded cog: '{cog_name}'")

    @commands.command(name="close", description="closes the bot")
    @commands.is_owner()
    async def close_bot(self, ctx):
        await ctx.send("Shutting Down")
        await self.bot.close()

    @commands.command(name="save", description="saves data")
    @commands.is_owner()
    async def save_data(self, ctx):
        self.bot.save_data()
        await ctx.send("Saved the data to file")

    @commands.command(name="load", description="loads data")
    @commands.is_owner()
    async def load_data(self, ctx):
        self.bot.load_data()
        await ctx.send("Loaded data from file")



    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("Only developers can use that command")
        else:
            await ctx.send(error)
            traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)








async def setup(bot):
    await bot.add_cog(Admin(bot))
