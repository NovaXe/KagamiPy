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
from common.logging import bot_log_handler, discord_log_handler

intents = discord.Intents.all()
# intents.message = True
# intents.voice_states = True
# intents.

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
        tree.on_error = on_app_command_error

    async def setup_hook(self):
        await self.dbman.setup(table_group="database")
        await self.dbman.setup(table_group="common",
                               drop_tables=self.config.drop_tables,
                               drop_triggers=self.config.drop_triggers,
                               ignore_schema_updates=self.config.ignore_schema_updates,
                               ignore_trigger_updates=self.config.ignore_trigger_updates)

        for file in os.listdir("cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                # if name == "sentinels":
                #     continue
                path = f"cogs.{name}"
                await self.load_extension(path)

    async def start(self, token, reconnect=True):
        await super().start(token, reconnect=reconnect)

    def run_bot(self):
        logger = logging.getLogger("discord")
        logger.propagate = False
        self.run(token=self.config.token, log_handler=discord_log_handler, log_level=logging.DEBUG)

    async def close(self):
        for cog in self.cogs:
            cog_obj = self.get_cog(cog)
            await cog_obj.cog_unload()
        print("unloaded cogs\n")
        await super().close()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.database.upsertGuild(self.database.Guild.fromDiscord(guild))

    async def on_guild_leave(self, guild: discord.Guild) -> None:
        await self.database.deleteGuild(guild.id)

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            await self.database.upsertGuild(self.database.Guild.fromDiscord(after))

    def getPartialMessage(self, message_id, channel_id) -> discord.PartialMessage | None:
        channel = self.get_channel(channel_id)
        if channel:
            return channel.get_partial_message(message_id)
        else:
            return None

    async def logToChannel(self, message: str, channel: discord.TextChannel=None, big_bold=True, code_block=True):
        if not channel:
            channel = self.get_channel(self.config.log_channel_id)
            # channel = await self.fetch_channel(self.config.log_channel_id)

        if code_block:
            message = f"`{message}`"
        if big_bold:
            message = f"## {message}"

        await channel.send(message)


    async def on_interaction(self, interaction: Interaction):
        pass
        # guild = self.database.Guild.fromDiscord(interaction.guild)
        # await self.database.upsertGuild(guild)

    async def on_command_error(self, context: Context | Interaction, exception: commands.CommandError, /) -> None:
        await super().on_command_error(context, exception)
        if isinstance(exception, commands.MissingPermissions):
            if isinstance(context, Interaction):
                await context.response.send_message("You don't have the necessary permissions to use this command",
                                                    ephemeral=True)
            else:
                await asyncio.gather(
                    context.message.delete(delay=5),
                    context.send("You don't have the necessary permissions to use this command", delete_after=5)
                )


    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        await super().on_error(event_method, *args, **kwargs)
        # await self.logToChannel(
        #     message=f"**{event_method}** \n **args:**\n{args}\n **kwargs:**\n{kwargs}",
        #     channel=self.get_channel(self.LOG_CHANNEL),
        #     big_bold=False,
        #     code_block=False)


    async def on_ready(self):
        login_message = f"Logged in as {self.user} (ID: {self.user.id})"
        print(login_message)
        # await self.logToChannel(login_message)



async def on_app_command_error(interaction: Interaction, error: AppCommandError):
    if isinstance(error, CustomCheck):
        og_response = await respond(interaction, f"**{error}**")
    else:
        og_response = await interaction.original_response()
        await og_response.channel.send(content=f"**Command encountered an error:**\n"
                                               f"{error}")
        traceback.print_exception(error, error, error.__traceback__, file=sys.stderr)
