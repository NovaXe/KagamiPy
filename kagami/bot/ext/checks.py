import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import check


def has_access_role(access_name: str):
    def predicate(interaction: discord.Interaction) -> bool:
        pass
    return check(predicate)