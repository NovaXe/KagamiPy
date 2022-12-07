import json
import os
import discord
import discord.utils
import asyncio
from discord.ext import commands
import wavelink
import subprocess
import threading
import multiprocessing
import atexit
import logging

log_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')


class Kagami(commands.Bot):
    def __init__(self):
        with open("bot/data/config.json") as f:
            self.config = json.load(f)
        with open("bot/data/server_data.json", "r") as f:
            self.server_data = json.load(f)
        super(Kagami, self).__init__(command_prefix=self.config["prefix"],
                                     intents=discord.Intents().all(),
                                     owner_id=self.config["owner"])

    async def start(self, token, reconnect=True):
        await super().start(token, reconnect=reconnect)


    def start_bot(self):
        self.run(self.config["token"])

    def save_data(self):
        with open("bot/data/server_data.json", "w") as f:
            json.dump(self.server_data, f, indent=4)


    async def close(self):
        # for node_id, node in wavelink.NodePool.nodes.values():
        #     await node.disconnect()

        for cog in self.cogs:
            cog_obj = self.get_cog(cog)
            await cog_obj.cog_unload()

        self.save_data()
        print("ran atexit\n")
        await super().close()

    async def setup_hook(self):
        for file in os.listdir("bot/cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                await self.load_extension(f"cogs.{name}")
        # await self.tree.sync()




    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")

def main():
    kagami = Kagami()
    kagami.run(kagami.config["token"], log_handler=log_handler, log_level=logging.DEBUG)


if __name__ == '__main__':
    main()

