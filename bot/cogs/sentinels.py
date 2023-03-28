import discord
from discord.ext import commands
from discord import app_commands


class Sentinel(commands.GroupCog, group_name="sentinel"):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config


    add_group = app_commands.Group(name="add", description="Create a new sentinel")
    remove_group = app_commands.Group(name="remove", description="Remove a sentinel")
    edit_group = app_commands.Group(name="edit", description="Edit an existing sentinel")
    list_group = app_commands.Group(name="list", description="Lists all sentinels")
    info_group = app_commands.Group(name="info", description="Gets sentinel info")



    async def sentinel_phrase_autocomplete(self, interaction: discord.Interaction, current: str):
        pass

    @add_group.command(name="global", description="Creates a new global sentinel")
    async def add_global(self, interaction: discord.Interaction, sentinel_phrase: str, response: str=None, reaction:str=None):

        pass

    @add_group.command(name="local", description="Creates a new global sentinel")
    async def add_local(self, interaction: discord.Interaction, sentinel_phrase: str, response: str = None, reaction: str = None):
        pass


    @remove_group.command(name="global", description="Remove a global sentinel")
    async def remove_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        pass

    @remove_group.command(name="local", description="Remove a local sentinel")
    async def remove_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        pass

    @edit_group.command(name='global', description='Edit a global sentinel')
    async def edit_global(self, interaciton: discord.Interaction, sentinel_phrase: str):
        pass

    @edit_group.command(name='local', description='Edit a local sentinel')
    async def edit_local(self, interaciton: discord.Interaction, sentinel_phrase: str):
        pass


    @list_group.command(name='global', description="List all global sentinels")
    async def list_local(self, interaction: discord.Interaction):
        pass

    @list_group.command(name='local', description="List all local sentinels")
    async def list_local(self, interaction: discord.Interaction):
        pass


    @info_group.command(name='local', description='Gets the info of a local sentinel')
    async def info_local(self, interaciton: discord.Interaction, sentinel_phrase: str):
        pass

    @info_group.command(name='global', description='Gets the info of a global sentinel')
    async def info_global(self, interaciton: discord.Interaction, sentinel_phrase: str):
        pass





