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
from typing import (
    Literal,
    Dict,
    Union,
    Optional,
    List,
)
from bot.utils.bot_data import Server
from bot.utils.music_helpers import Playlist

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
        self.servers: dict[str, Server] = {}
        self.create_server_list()

    def fetch_server(self, server_id: int):
        if str(server_id) not in self.servers:
            self.servers[str(server_id)] = Server(server_id)
        return self.servers[str(server_id)]


    def create_server_list(self):
        for server_id, server in self.server_data.items():
            self.servers[server_id] = Server(server_id)
            for playlist_name, playlist_tracks in self.server_data[server_id]["playlists"].items():
                self.servers[server_id].playlists[playlist_name] = Playlist(playlist_name, playlist_tracks)

            for sound_name, sound_id in self.server_data[server_id]["soundboard"].items():
                self.servers[server_id].soundboard[sound_name] = sound_id

    def update_server_data(self):
        data: dict[int, dict[str, dict[str, str]]] = {}
        for server_id, server in self.servers.items():
            data[server_id] = {"playlists": {},
                               "soundboard": {}
                               }
            for playlist_name, playlist in server.playlists.items():
                data[server_id]["playlists"].update({playlist_name: playlist.tracks})

            for sound_name, sound_id in server.soundboard.items():
                data[server_id]["soundboard"].update({sound_name: sound_id})

        self.server_data = data


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

        self.update_server_data()
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

