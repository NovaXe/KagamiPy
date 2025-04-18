import asyncio
import json
import logging
import os
import sys
import traceback

import discord
import discord.utils
from discord import Interaction
from discord import app_commands
from discord.app_commands import AppCommandError
from discord.ext.commands import Context

from discord.ext import commands
from typing import (
    Any,
    override, )

from bot import config
from common import errors
from common.interactions import respond

from common import errors
from common.depr_context_vars import CVar
from common.database import DatabaseManager
from common.tables import Guild
from common.logging import bot_log_handler, discord_log_handler, setup_logging

intents = discord.Intents.all()
# intents.message = True
# intents.voice_states = True
# intents.
my_logger = setup_logging(__name__)

class Kagami(commands.Bot):
    def __init__(self):
        # config: Configuration = config
        # print(config)
        super().__init__(command_prefix=config.prefix,
                         intents=intents,
                         owner_id=config.owner_id)
        self.activity = discord.CustomActivity("Testing new things")
        self.raw_data = {}
        self.database = None
        self.dbman: DatabaseManager = None
        self.changeCmdError()
        self.init_data()
        # self.restart_on_close = False


    def init_data(self):
        self.dbman = DatabaseManager(config.data_path + config.db_name, pool_size=config.connection_pool_size)

    def changeCmdError(self):
        tree = self.tree
        self._old_tree_error = tree.on_error
        tree.on_error = self.on_app_command_error

    async def setup_hook(self):
        # await self.dbman.setup(table_group="common.database")
        # This the common database group is instead setup by the DatabaseManager instance as part of its initializer
        await self.dbman.setup(table_group="common.tables",
                               drop_tables=config.drop_tables,
                               drop_triggers=config.drop_triggers,
                               ignore_schema_updates=config.ignore_schema_updates,
                               ignore_trigger_updates=config.ignore_trigger_updates)

        await self.load_all_extensions()

    async def load_all_extensions(self):
        for file in os.listdir("cogs"):
            await self.load_cog_extension(file)

    async def load_cog_extension(self, filename: str):
        if not (filename.startswith("~") or filename.endswith("__pycache__")):
            if filename.endswith(".py"):
                name = filename[:-3]
            else:
                name = filename
            if name in config.excluded_cogs:
                return
            path = f"cogs.{name}"
            await self.load_extension(path)

    @override
    async def start(self, token: str, *, reconnect: bool=True):
        await super().start(token, reconnect=reconnect)

    def run_bot(self):
        logger = logging.getLogger("discord")
        logger.propagate = True
        self.run(token=config.token, log_handler=discord_log_handler, log_level=logging.INFO) # Set to info so it isn't nonsense webhook spam

    async def close(self):
        for cog in self.cogs:
            cog_obj = self.get_cog(cog)
            await cog_obj.cog_unload()
        print("unloaded cogs\n")
        await super().close()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        guild_data = Guild.fromDiscord(guild)
        async with self.dbman.conn() as db:
            await guild_data.upsert(db)
            await db.commit()
        my_logger.info(f"Registered new guild: {guild} to the Guild Table")

    async def on_guild_leave(self, guild: discord.Guild) -> None:
        async with self.dbman.conn() as db:
            await Guild.deleteWhere(guild_id=guild.id)
            await db.commit()
        my_logger.info(f"Removed guild: {guild} from the Guild Table")

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            async with self.dbman.conn() as db:
                guild_data = Guild.fromDiscord(after)
                await guild_data.upsert(db)
        my_logger.info(f"Updated data for guild: {guild_data} in the Guild Table")

    def getPartialMessage(self, message_id, channel_id) -> discord.PartialMessage | None:
        channel = self.get_channel(channel_id)
        if channel:
            return channel.get_partial_message(message_id)
        else:
            return None

    async def on_interaction(self, interaction: Interaction):
        """Could potentially implement some fancy behind the scene interaction handling or something. Not sure what use case tho"""
        pass

    async def on_command_error(self, context: Context | Interaction, exception: commands.CommandError, /) -> None:
        await super().on_command_error(context, exception)
        async def send(message: str):
            if isinstance(context, Interaction):
                await respond(context, message, delete_after=8, ephemeral=True)
            else:
                await asyncio.gather(
                    context.message.delete(delay=8),
                    context.message.reply(message, delete_after=8, ephemeral=True)
                )
        if isinstance(exception, commands.MissingPermissions):
            await send("You don't have the necessary permissions to use this command")
        else:
            await send(str(exception))
            my_logger.error(f"Command Exception Encountered\n{exception}", exc_info=True)
            
    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        await super().on_error(event_method, *args, **kwargs)
        my_logger.exception(event_method, *args, **kwargs)

    async def on_ready(self):
        login_message = f"Logged in as {self.user} (ID: {self.user.id})"
        print(login_message)
        my_logger.info(login_message)

    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        match error_type:=type(error):
            case errors.CustomCheck:
                await respond(interaction, f"**{error.args[0]}**", ephemeral=error_type.EPHEMERAL)
                # my_logger.error(f"CustomCheck Error:\n{error}", exc_info=True)
            case app_commands.CheckFailure:
                await respond(interaction, f"**{error.args[0]}**")
                # my_logger.error(f"CheckFailure Error:\n{error}", exc_info=True)
            case _:
                await respond(interaction, content=f"**Command encountered an error:**\n{error}")
                my_logger.error(f"Command encountered an error:\n{error}", exc_info=True)
                # traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)
