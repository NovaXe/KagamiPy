import asyncio
import json
import logging
import os
import sys
import traceback

from discord.app_commands import AppCommandError
from discord.ext.commands import Context

import discord
import discord.utils
from discord import Interaction
from discord.ext import commands
from typing import (
    Any, )

from common.errors import CustomCheck
from common.interactions import respond

from .config import Configuration, config

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
        self.config: Configuration = config
        # print(self.config)
        super().__init__(command_prefix=self.config.prefix,
                         intents=intents,
                         owner_id=self.config.owner_id)
        self.activity = discord.CustomActivity("Testing new things")
        self.raw_data = {}
        self.database = None
        self.dbman: DatabaseManager = None
        self.changeCmdError()
        self.init_data()
        # self.restart_on_close = False


    def init_data(self):
        self.dbman = DatabaseManager(self.config.data_path + self.config.db_name, pool_size=self.config.connection_pool_size)

    def changeCmdError(self):
        tree = self.tree
        self._old_tree_error = tree.on_error
        tree.on_error = self.on_app_command_error

    async def setup_hook(self):
        await self.dbman.setup(table_group="database")
        await self.dbman.setup(table_group="common",
                               drop_tables=self.config.drop_tables,
                               drop_triggers=self.config.drop_triggers,
                               ignore_schema_updates=self.config.ignore_schema_updates,
                               ignore_trigger_updates=self.config.ignore_trigger_updates)

        for file in os.listdir("cogs"):
            if file.endswith(".py") and not file.startswith("~"):
                name = file[:-3]
                if name in self.config.excluded_cogs:
                    continue
                path = f"cogs.{name}"
                await self.load_extension(path)

    async def start(self, token, reconnect=True):
        await super().start(token, reconnect=reconnect)

    def run_bot(self):
        logger = logging.getLogger("discord")
        logger.propagate = True
        self.run(token=self.config.token, log_handler=discord_log_handler, log_level=logging.INFO) # Set to info so it isn't nonsense webhook spam

    async def close(self):
        for cog in self.cogs:
            cog_obj = self.get_cog(cog)
            await cog_obj.cog_unload()
        print("unloaded cogs\n")
        await super().close()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        guild_data = Guild.fromDiscord(guild)
        async with self.dbman() as db:
            await guild_data.upsert(db)
            await db.commit()
        my_logger.info(f"Registered new guild: {guild} to the Guild Table")

    async def on_guild_leave(self, guild: discord.Guild) -> None:
        async with self.dbman() as db:
            await Guild.deleteWhere(guild_id=guild.id)
            await db.commit()
        my_logger.info(f"Removed guild: {guild} from the Guild Table")

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            async with self.dbman() as db:
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
            my_logger.error(f"Command Exception Encountered\n{exception}")
            
    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        await super().on_error(event_method, *args, **kwargs)
        my_logger.exception(event_method, *args, **kwargs)

    async def on_ready(self):
        login_message = f"Logged in as {self.user} (ID: {self.user.id})"
        print(login_message)
        my_logger.info(login_message)

    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        if isinstance(error, CustomCheck):
            message = await respond(interaction, f"**{error}**")
        else:
            await respond(interaction, content=f"**Command encountered an error:**\n{error}")
            my_logger.error(f"Command encountered an error:\n{error}")
            # traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)
