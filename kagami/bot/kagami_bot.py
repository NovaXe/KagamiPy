import json
import os

import discord
import discord.utils
from discord.ext import commands
from typing import (
    Any,
)

from bot.ext import errors
from bot.utils.bot_data import Server, BotData, Tag, Sentinel, Track, Playlist, ServerData
from bot.utils.music_helpers import OldPlaylist
from bot.utils.context_vars import CVar

intents = discord.Intents.all()
# intents.message = True
# intents.voice_states = True
# intents.

BOT_CONFIG_PATH = "bot/data/config.json"
BOT_DATA_PATH = "bot/data/old_data.json"
BOT_NEW_DATA_PATH = "bot/data/data.json"

class Kagami(commands.Bot):
    def __init__(self):
        with open(BOT_CONFIG_PATH) as f:
            self.config = json.load(f)

        super(Kagami, self).__init__(command_prefix=self.config["prefix"],
                                     intents=intents,
                                     owner_id=self.config["owner"])
        self.changeCmdError()

        self.old_data = {}
        self.servers: dict[str, Server] = {}
        self.global_data = {}
        self.global_tags = {}
        self.global_sentinels = {}

        self.raw_data = {}
        self.data: BotData = BotData()

        self.load_data()
        self.newLoadData()
        bot_var.value = self


    def changeCmdError(self):
        tree = self.tree
        self._old_tree_error = tree.on_error
        tree.on_error = errors.on_app_command_error


    # DATA_PATH = "bot/data/old_data.json"
    def newLoadData(self):
        with open(BOT_DATA_PATH) as f:
            self.raw_data = json.load(f)
        self.data = BotData.fromDict(self.raw_data)

        # self.loadGlobals()
        # self.loadServers()

    def newSaveData(self):
        self.raw_data = self.data.toDict()
        with open(BOT_NEW_DATA_PATH, "w") as f:
            json.dump(self.raw_data, f, indent=4)

    def loadGlobals(self):
        _globals = self.raw_data["globals"]
        g_tags = _globals['tags']
        g_sentinels = _globals['sentinels']

        self.data.globals.tags = {name: Tag(**data) for name, data in g_tags.items()}
        self.data.globals.sentinels = {name: Sentinel(**data) for name, data in g_sentinels.items()}
        pass # eof

    def loadServers(self):
        _servers = self.raw_data["servers"]
        for s_id, data in _servers.items():
            s_playlists = data["playlists"]
            s_soundboard = data["soundboard"]
            s_tags = data["tags"]
            s_sentinels = data["sentinels"]
            s_fish_mode = data["fish_mode"] if "fish_mode" in data else False

            # data: playlists, soundboard, tags, sentinels
            # playlist : duration, tracks
            # track: duration, name, encoded_id

            # intiializing playlist data
            playlists = {}
            for p_name, p_data in s_playlists.items():
                if "tracks" in p_data:
                    tracks = [Track(**track) for track in p_data["tracks"]]
                    duration = p_data["duration"]
                else:
                    tracks = p_data
                    duration = 0
                playlist = Playlist(tracks=tracks, duration=duration)
                playlists.update({
                    p_name: playlist
                })

            soundboard = {s_name: s_id for s_name, s_id in s_soundboard.items()}
            tags = {t_name: Tag(**t_data) for t_name, t_data in s_tags.items()}
            sentinels = {name: Sentinel(**data) for name, data in s_sentinels.items()}

            self.data.servers.update({
                s_id: ServerData(
                    playlists=playlists,
                    soundboard=soundboard,
                    tags=tags,
                    sentinels=sentinels,
                    fish_mode=s_fish_mode
                )
            })
        pass # eol

    def getPartialMessage(self, message_id, channel_id) -> discord.PartialMessage | None:
        channel = self.get_channel(channel_id)
        if channel:
            return channel.get_partial_message(message_id)
        else:
            return None



    def getServerData(self, server_id: int | str) ->ServerData:
        server_id = str(server_id)
        if server_id not in self.data.servers.keys():
            self.data.servers[server_id] = ServerData()
        return self.data.servers[server_id]

    def fetch_server(self, server_id: [int, str]):
        if str(server_id) not in self.servers:
            self.servers[str(server_id)] = Server(server_id)
        return self.servers[str(server_id)]


    def create_server_list(self):
        if "servers" not in self.old_data.keys():
            # print("no servers")
            return
        for server_id, server in self.old_data["servers"].items():
            self.servers[server_id] = Server(server_id)
            server_data_keys = self.old_data["servers"][server_id].keys()

            if "playlists" in server_data_keys:
                for playlist_name, playlist_tracks in self.old_data["servers"][server_id]["playlists"].items():
                    self.servers[server_id].playlists[playlist_name] = OldPlaylist(playlist_name, playlist_tracks)

            if "soundboard" in server_data_keys:
                for sound_name, sound_id in self.old_data["servers"][server_id]["soundboard"].items():
                    self.servers[server_id].soundboard[sound_name] = sound_id

            if "tags" in server_data_keys:
                self.servers[server_id].tags = self.old_data["servers"][server_id]["tags"]

            if 'sentinels' in server_data_keys:
                self.servers[server_id].sentinels = self.old_data['servers'][server_id]['sentinels']


    def update_data(self):
        # print(self.data)
        data: dict[str, dict[str, dict[str, dict[str, str]]]] = {
            "globals": {},
            "servers": {}
        }


        data["globals"].update(self.global_data)

        for server_id, server in self.servers.items():
            data["servers"][server_id] = {"playlists": {},
                                          "soundboard": {},
                                          "tags": {},
                                          "sentinels": {},
                                          }
            for playlist_name, playlist in server.playlists.items():
                data["servers"][server_id]["playlists"].update({playlist_name: playlist.tracks})

            for sound_name, sound_id in server.soundboard.items():
                data["servers"][server_id]["soundboard"].update({sound_name: sound_id})

            data["servers"][server_id]["tags"].update(server.tags.items())
            data["servers"][server_id]["sentinels"].update(server.sentinels.items())


            # for tag_name, tag_data in server_id.tags.items():
            #     data["servers"][server_id]["tags"].update({tag_name: tag_data})


        self.old_data = data


    async def start(self, token, reconnect=True):
        await super().start(token, reconnect=reconnect)


    def start_bot(self):
        self.run(self.config["token"])


    def save_data(self):
        self.update_data()
        with open(BOT_DATA_PATH, "w") as f:
            json.dump(self.old_data, f, indent=4)

    def load_data(self):
        with open(BOT_DATA_PATH, "r") as f:
            self.old_data = json.load(f)


        self.create_server_list()

        if "globals" in self.old_data.keys():
            self.global_data: dict[str, dict] = self.old_data["globals"]
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
                path = f"bot.cogs.{name}"
                await self.load_extension(path)
        # await self.tree.sync()

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


bot_var = CVar[Kagami]('kagami')
