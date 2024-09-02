import asyncio
import json
import logging
import os
import sys
from discord.ext.commands import Context

import utils.old_db_interface

import discord
import discord.utils
from discord import Interaction
from discord.ext import commands
from typing import (
    Any, )

from common import errors
from utils.bot_data import BotData, BotConfiguration
from common.depr_context_vars import CVar
from common.database import DatabaseManager

intents = discord.Intents.all()
# intents.message = True
# intents.voice_states = True
# intents.

class Kagami(commands.Bot):
    def __init__(self):
        self.config = BotConfiguration.initFromEnv()
        # print(self.config)
        super().__init__(command_prefix=self.config.prefix,
                         intents=intents,
                         owner_id=self.config.owner_id)
        self.activity = discord.CustomActivity("Testing new things")
        self.raw_data = {}
        self.data: BotData = None
        self.database = None
        self.db_man: DatabaseManager = None
        self.changeCmdError()
        self.init_data()

    def init_data(self):
        self.loadData()
        self.database = utils.old_db_interface.InfoDB(self.config.db_path)
        self.db_man = DatabaseManager(self.config.db_path)

    def changeCmdError(self):
        tree = self.tree
        self._old_tree_error = tree.on_error
        tree.on_error = errors.on_app_command_error

    async def setup_hook(self):
        await self.database.init(drop=self.config.drop_tables)
        # guilds = [self.database.Guild.fromDiscord(guild) for guild in list(self.guilds)]
        # await self.database.upsertGuilds(guilds)

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
        log_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
        self.run(token=self.config.token, log_handler=log_handler, log_level=logging.DEBUG)

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

    def loadData(self): # this is the old shit that uses json, needs to go at some point
        data_path = self.config.local_data_path
        try:
            with open(f"{data_path}/data.json") as f:
                self.raw_data = json.load(f)
        except FileNotFoundError:
            print(f"Missing data.json file at {data_path}")
            print("path=", os.path.dirname(sys.argv[0]))
            raise FileNotFoundError
        self.data = BotData.fromDict(self.raw_data)

    def saveData(self):
        data_path = self.config.local_data_path
        self.raw_data = self.data.toDict()
        with open(f"{data_path}/data.json", "w") as f:
            json.dump(self.raw_data, f, indent=4)

    def getPartialMessage(self, message_id, channel_id) -> discord.PartialMessage | None:
        channel = self.get_channel(channel_id)
        if channel:
            return channel.get_partial_message(message_id)
        else:
            return None



    LOG_CHANNEL = 825529492982333461
    # TODO change the config system to utilize a dataclass
    # Add LOG_CHANNEL to the config

    async def logToChannel(self, message:str, channel: discord.TextChannel|int=LOG_CHANNEL, big_bold=True, code_block=True):
        if not isinstance(channel, discord.TextChannel):
            channel = self.get_channel(channel)

        if code_block:
            message = f"`{message}`"
        if big_bold:
            message = f"## {message}"

        await channel.send(message)

    # async def on_interaction(self, interaction: Interaction):
    #     print("-----------------------------\nON INTERACTION HAS FIRED")
    #     print(f"{interaction.command.name}")
    #     # current_interaction.value = interaction
    #     server_data.value = self.getServerData(interaction.guild_id)

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
        await self.logToChannel(login_message)
