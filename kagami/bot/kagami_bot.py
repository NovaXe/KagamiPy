import json
import logging
import os
import sys
import aiosqlite
import wavelink
from discord.utils import MISSING
from wavelink.ext import spotify
from bot.utils import database


import discord
import discord.utils
from discord import Interaction
from discord.ext import commands, tasks
from typing import (
    Any, Optional,
)

from bot.ext import errors
from bot.utils.bot_data import Server, BotData, OldTag, OldSentinel, Track, Playlist, ServerData, server_data, \
    BotConfiguration
from bot.utils.music_helpers import OldPlaylist
from bot.utils.context_vars import CVar
from bot.utils.interactions import current_interaction

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
        self.changeCmdError()

        self.old_data = {}
        self.servers: dict[str, Server] = {}
        self.global_data = {}
        self.global_tags = {}
        self.global_sentinels = {}

        self.raw_data = {}
        self.data: BotData = BotData()

        self.newLoadData()
        bot_var.value = self
        self.database = database.InfoDB(self.config.db_path)

    def changeCmdError(self):
        tree = self.tree
        self._old_tree_error = tree.on_error
        tree.on_error = errors.on_app_command_error


    async def setup_hook(self):
        await self.database.init(drop=self.config.drop_tables)
        # guilds = [self.database.Guild.fromDiscord(guild) for guild in list(self.guilds)]
        # await self.database.upsertGuilds(guilds)

        for file in os.listdir("bot/cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                path = f"bot.cogs.{name}"
                await self.load_extension(path)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.database.upsertGuild(self.database.Guild.fromDiscord(guild))

    async def on_guild_leave(self, guild: discord.Guild) -> None:
        await self.database.deleteGuild(guild.id)

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            await self.database.upsertGuild(self.database.Guild.fromDiscord(after))

    # DATA_PATH = "bot/data/old_data.json"
    def newLoadData(self):
        data_path = self.config.local_data_path

        try:
            with open(f"{data_path}/data.json") as f:
                self.raw_data = json.load(f)
        except FileNotFoundError:
            print(f"Missing data.json file at {data_path}")
            print("path=", os.path.dirname(sys.argv[0]))
            raise FileNotFoundError

        self.data = BotData.fromDict(self.raw_data)

        # self.loadGlobals()
        # self.loadServers()

    def newSaveData(self):
        data_path = self.config.local_data_path
        self.raw_data = self.data.toDict()
        with open(f"{data_path}/data.json", "w") as f:
            json.dump(self.raw_data, f, indent=4)

    def loadGlobals(self):
        _globals = self.raw_data["globals"]
        g_tags = _globals['tags']
        g_sentinels = _globals['sentinels']

        self.data.globals.tags = {name: OldTag(**data) for name, data in g_tags.items()}
        self.data.globals.sentinels = {name: OldSentinel(**data) for name, data in g_sentinels.items()}
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
            tags = {t_name: OldTag(**t_data) for t_name, t_data in s_tags.items()}
            sentinels = {name: OldSentinel(**data) for name, data in s_sentinels.items()}

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
        data = self.data.servers.get(server_id, ServerData())
        return data

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

    def run_bot(self):
        log_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
        self.run(token=self.config.token, log_handler=log_handler, log_level=logging.DEBUG)

    # def run(self):
    #     super()


    async def close(self):
        # for node_id, node in wavelink.NodePool.nodes.values():
        #     await node.disconnect()

        for cog in self.cogs:
            cog_obj = self.get_cog(cog)
            await cog_obj.cog_unload()

        self.update_data()
        self.newSaveData()
        print("ran atexit\n")
        await super().close()

    # @tasks.loop(seconds=10)


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
