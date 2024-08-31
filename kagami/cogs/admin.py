import asyncio
import os
import sys
import traceback

import discord.utils
from discord.ext import commands
from discord import app_commands
from bot import Kagami
from common.interactions import respond


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config


    # @commands.is_owner()
    @app_commands.command()
    async def test(self, interaction: discord.Interaction):
        print(f"-------------\nentered test command\n"
              f"interaction:{interaction.command}")
        await respond(interaction)
        print("-------------\ndoing stuff")
        await asyncio.sleep(2)
        print("------------\nfinished doing stuff")
        await respond(interaction, "did some stuff")

    # @commands.is_owner()
    @app_commands.command()
    async def defer(self, interaction: discord.Interaction):
        print(f"-------------\nentered defer command\n"
              f"interaction:{interaction.command}")
        await respond(interaction, force_defer=True)
        print("-------------\ndoing stuff")
        await asyncio.sleep(2)
        print("------------\nfinished doing stuff")
        await respond(interaction, "did some deferred stuff")

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
                    await self.bot.reload_extension(f"bot.cogs.{name}")
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
        self.bot.saveData()
        await ctx.send("Saved the data to file")

    @commands.command(name="load", description="loads data")
    @commands.is_owner()
    async def load_data(self, ctx):
        self.bot.loadData()
        await ctx.send("Loaded data from file")

    @commands.command(name="clear_global", description="clears the global command tree")
    @commands.is_owner()
    async def clear_global(self, ctx: commands.Context):
        self.bot.tree.clear_commands(guild=None)
        await ctx.send("Cleared the global command tree, the tree needs to be synced")

    @commands.command(name="clear_local", description="clears the local command tree")
    @commands.is_owner()
    async def clear_local(self, ctx: commands.Context):
        self.bot.tree.clear_commands(guild=ctx.guild)
        await ctx.send("Cleared the local command tree, the tree needs to be synced")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("Only developers can use that command")
        else:
            await ctx.send(error)
            traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)








async def setup(bot):
    await bot.add_cog(Admin(bot))

