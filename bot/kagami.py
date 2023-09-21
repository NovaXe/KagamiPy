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


intents = discord.Intents.all()
# intents.message = True
# intents.voice_states = True
# intents.


class Kagami(commands.Bot):
    def __init__(self):
        with open("bot/data/config.json") as f:
            self.config = json.load(f)

        super(Kagami, self).__init__(command_prefix=self.config["prefix"],
                                     intents=intents,
                                     owner_id=self.config["owner"])
        self.data = {}
        self.servers: dict[str, Server] = {}
        self.global_data = {}
        self.global_tags = {}
        self.global_sentinels = {}

        self.load_data()



    def fetch_server(self, server_id: [int, str]):
        if str(server_id) not in self.servers:
            self.servers[str(server_id)] = Server(server_id)
        return self.servers[str(server_id)]


    def create_server_list(self):
        if "servers" not in self.data.keys():
            # print("no servers")
            return
        for server_id, server in self.data["servers"].items():
            self.servers[server_id] = Server(server_id)
            server_data_keys = self.data["servers"][server_id].keys()

            if "playlists" in server_data_keys:
                for playlist_name, playlist_tracks in self.data["servers"][server_id]["playlists"].items():
                    self.servers[server_id].playlists[playlist_name] = Playlist(playlist_name, playlist_tracks)

            if "soundboard" in server_data_keys:
                for sound_name, sound_id in self.data["servers"][server_id]["soundboard"].items():
                    self.servers[server_id].soundboard[sound_name] = sound_id

            if "tags" in server_data_keys:
                self.servers[server_id].tags = self.data["servers"][server_id]["tags"]

            if 'clean_sentinels' in server_data_keys:
                self.servers[server_id].sentinels = self.data['servers'][server_id]['clean_sentinels']


    def update_data(self):
        # print(self.data)
        data: dict[str, dict[str, dict[str, dict[str, str]]]] = {
            "global": {},
            "servers": {}
        }


        data["global"].update(self.global_data)

        for server_id, server in self.servers.items():
            data["servers"][server_id] = {"playlists": {},
                                          "soundboard": {},
                                          "tags": {},
                                          "clean_sentinels": {},
                                          }
            for playlist_name, playlist in server.playlists.items():
                data["servers"][server_id]["playlists"].update({playlist_name: playlist.tracks})

            for sound_name, sound_id in server.soundboard.items():
                data["servers"][server_id]["soundboard"].update({sound_name: sound_id})

            data["servers"][server_id]["tags"].update(server.tags.items())
            data["servers"][server_id]["clean_sentinels"].update(server.sentinels.items())


            # for tag_name, tag_data in server_id.tags.items():
            #     data["servers"][server_id]["tags"].update({tag_name: tag_data})


        self.data = data


    async def start(self, token, reconnect=True):
        await super().start(token, reconnect=reconnect)


    def start_bot(self):
        self.run(self.config["token"])


    def save_data(self):
        self.update_data()
        with open("bot/data/data.json", "w") as f:
            json.dump(self.data, f, indent=4)

    def load_data(self):
        with open("bot/data/data.json", "r") as f:
            self.data = json.load(f)


        self.create_server_list()

        if "global" in self.data.keys():
            self.global_data: dict[str, dict] = self.data["global"]
        else:
            self.global_data = {}


    async def close(self):
        # for node_id, node in wavelink.NodePool.nodes.values():
        #     await node.disconnect()

        for cog in self.cogs:
            cog_obj = self.get_cog(cog)
            await cog_obj.cog_unload()

        self.update_data()
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
