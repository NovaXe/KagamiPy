import json
import os
import discord
import discord.utils
import asyncio
from discord.ext import commands

with open("data/config.json") as f:
    config = json.load(f)


class Kagami(commands.Bot):
    def __init__(self):
        super(Kagami, self).__init__(command_prefix=config["prefix"], intents=discord.Intents().all())

    async def setup_hook(self):
        for file in os.listdir("cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                await self.load_extension(f"cogs.{name}")
        await bot.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")


if __name__ == '__main__':
    bot = Kagami()
    bot.run(config["token"])

