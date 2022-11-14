import json
import os
import discord
import discord.utils
from discord.ext import commands

with open("data/config.json") as f:
    config = json.load(f)


class Kagami(commands.bot):
    def __init__(self):
        super(Kagami, self).__init__(command_prefix=config["prefix"], intents=discord.Intents().all())

        for file in os.listdir("cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                self.load_extension(f"cogs.{name}")


if __name__ == '__main__':
    bot = Kagami()
    bot.run(config["token"])

