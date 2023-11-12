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
from bot.utils.music_helpers import OldPlaylist
from kagami import Kagami


log_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')


def main():
    kagami = Kagami()
    kagami.run(kagami.config["token"], log_handler=log_handler, log_level=logging.DEBUG)


if __name__ == '__main__':
    main()

