import json
import os
import discord
import discord.utils
import asyncio
from discord.ext import commands
import subprocess
import threading
import multiprocessing


class Kagami(commands.Bot):
    def __init__(self):
        with open("bot/data/config.json") as f:
            self.config = json.load(f)
        super(Kagami, self).__init__(command_prefix=self.config["prefix"],
                                     intents=discord.Intents().all(),
                                     owner_id=self.config["owner"])

    def start_bot(self):
        self.run(self.config["token"])

    async def setup_hook(self):
        for file in os.listdir("bot/cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                await self.load_extension(f"cogs.{name}")
        # await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")


if __name__ == '__main__':
    kagami = Kagami()
    kagami.start_bot()

