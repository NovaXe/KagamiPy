import asyncio
import os
import sys
import traceback

import discord.utils
from discord.ext import commands
from discord import app_commands
from bot import Kagami
from common.interactions import respond
from common.database import TableMetadata

type Context = commands.Context[Kagami]


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
        exts = list(self.bot.extensions.keys())
        for ext in exts:
            await self.bot.reload_extension(ext)
        await ctx.send("Reloaded all cogs")

    @commands.command(name="list-ext")
    @commands.is_owner()
    async def list_ext(self, ctx):
        await ctx.send(" ".join(self.bot.extensions))

    @commands.command(name="reload", description="reloads a  cog")
    @commands.is_owner()
    async def reload_cog(self, ctx, cog_name):
        name = f"cogs.{cog_name}"
        if name in self.bot.extensions:
            await self.bot.reload_extension(name)
            await ctx.send(f"Reloaded cog: `{cog_name}`")
        # for file in os.listdir("cogs"):
        #     if file.endswith(".py"):
        #         name = file[:-3]
        #         if name.lower() == cog_name.lower():
        #             await self.bot.reload_extension(f"cogs.{name}")
        #             break
        else:
            await ctx.send(f"No cog with that name could be found")
            return
    
    @commands.command(name="load")
    async def load_cog(self, ctx, cog_name: str):
        await self.bot.load_cog_extension(f"cogs.{cog_name}")
        await ctx.send(f"Loaded cog: `{cog_name}`")
        
    @commands.command(name="unload")
    async def unload_cog(self, ctx, cog_name):
        await self.bot.unload_extension(f"cogs.{cog_name}")
        await ctx.send(f"Unloaded cog: `{cog_name}`")
    
    @commands.command(name="drop-unregisterd")
    @commands.is_owner()
    async def drop_unregistered(self, ctx):
        await self.bot.dbman.drop_unregistered()
        await ctx.send("Dropped all unregistered tables")

    @commands.command(name="close", description="closes the bot")
    @commands.is_owner()
    async def close_bot(self, ctx):
        await ctx.send("Shutting Down")
        await self.bot.close()

    @commands.command(name="resetpool")
    async def reset_connection_pool(self, ctx):
        await ctx.send("Resetting Pool")
        await self.bot.dbman.pool.reset()

    @commands.command(name="clear_global", description="clears the global command tree")
    @commands.is_owner()
    async def clear_global(self, ctx: Context):
        self.bot.tree.clear_commands(guild=None)
        await ctx.send("Cleared the global command tree, the tree needs to be synced")

    @commands.command(name="clear_local", description="clears the local command tree")
    @commands.is_owner()
    async def clear_local(self, ctx: Context):
        self.bot.tree.clear_commands(guild=ctx.guild)
        await ctx.send("Cleared the local command tree, the tree needs to be synced")

    @commands.command(name="tablever")
    @commands.is_owner()
    async def tablever(self, ctx: Context, table_name: str) -> None:
        async with self.bot.dbman.conn() as db:
            res = await TableMetadata.selectData(db, table_name)
            if res:
                await ctx.send(f"Schema Version: {res.schema_version}, Trigger Version: {res.trigger_version}")
            else:
                await ctx.send(f"The query returned with nothing, there is no table with that name")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("Only developers can use that command")
        else:
            await ctx.send(error)
            traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)








async def setup(bot):
    await bot.add_cog(Admin(bot))

