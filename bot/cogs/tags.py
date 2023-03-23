import discord
from discord import app_commands
from discord.ext import commands
from bot.utils.bot_data import Server

from typing import Literal




class Tags(commands.GroupCog, group_name="tag"):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config


    get = app_commands.Group(name="get", description="gets a tag")
    set = app_commands.Group(name="set", description="sets a tag")
    delete = app_commands.Group(name="delete", description="deletes a tag")

    async def server_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        user = interaction.user
        bot_guilds = list(self.bot.guilds)
        mutual_guilds = list(user.mutual_guilds)
        guilds: list[discord.Guild] = None

        if user.id == self.config["owner"]:
            guilds = mutual_guilds
        else:
            guilds = mutual_guilds
        return [
            app_commands.Choice(name=guild.name, value=str(guild.id))
            for guild in guilds if current.lower() in guild.name.lower()
        ]

    async def tag_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        command_name = interaction.command.name

        tags = {}
        # print("tag current", current)
        # print(command_name)
        if "global" == command_name:
            # print("global tag")
            tags = self.bot.global_tags
        elif "local" == command_name:
            # print("local tag")
            tags = self.bot.fetch_server(interaction.guild_id).tags
        elif "server" == command_name:
            # print("server tag")

            # print(interaction.namespace["server"])
            # guild = discord.utils.get(interaction.user.mutual_guilds, name=interaction.namespace["server"])
            server_id = interaction.namespace["server"]
            if server_id:
                tags = self.bot.fetch_server(server_id).tags


        return [
            app_commands.Choice(name=tag_name, value=tag_name)
            for tag_name, tag_data in tags.items() if current.lower() in tag_name.lower()
        ]

    @app_commands.command(name="search", description="search for a tag")
    async def _search(self, interaction: discord.Interaction, search: str):
        await interaction.response.defer(thinking=True)

        await interaction.edit_original_response(content="lol haven't added this yet")


    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @get.command(name="global", description="get a global tag")
    async def get_global(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        # if not self.bot.global_tags:
        #     await interaction.edit_original_response(content="There are no global tags")
        #     return
        if tag_name not in self.bot.global_tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data = self.bot.global_tags[tag_name]
        await interaction.edit_original_response(content=tag_data["content"])

    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @get.command(name="local", description="get a tag from the server")
    async def get_local(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data = server.tags[tag_name]
        await interaction.edit_original_response(content=tag_data["content"])

    @app_commands.autocomplete(server=server_autocomplete, tag_name=tag_autocomplete)
    @get.command(name="server", description="get a tag from another server")
    async def get_server(self, interaction: discord.Interaction, server: str, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(server)

        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data = server.tags[tag_name]
        await interaction.edit_original_response(content=tag_data["content"])


    # @app_commands.command(name="set", description="set a new tag")
    # async def _set(self, interaction: discord.Interaction, tag_name: str, content: str):
    #     pass


    @set.command(name="local", description="set a tag for this server")
    async def set_local(self, interaction: discord.Interaction, tag_name: str, content: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if tag_name in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** already exists")
            return
        server.tags.update({
            tag_name: {
                "content": content
            }})

        await interaction.edit_original_response(content=f"Added tag **`{tag_name}`** to the server")


    @set.command(name="global", description="set a global tag")
    async def set_global(self, interaction: discord.Interaction, tag_name: str, content: str):
        await interaction.response.defer(thinking=True)
        if tag_name in self.bot.global_tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** already exists")
            return
        self.bot.global_tags.update({
            tag_name: {
                "content": content
            }})

        await interaction.edit_original_response(content=f"Added tag **`{tag_name}`** to globals")
        pass



    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @delete.command(name="local", description="Deletes a tag from this server")
    async def delete_local(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return

        server.tags.pop(tag_name, None)
        await interaction.edit_original_response(content=f"The tag **`{tag_name}`** has been deleted")

    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @delete.command(name="global", description="Deletes a global tag")
    async def delete_global(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        if tag_name not in self.bot.global_tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        self.bot.global_tags.pop(tag_name, None)
        await interaction.edit_original_response(content=f"The global tag **`{tag_name}`** has been deleted")






async def setup(bot):
    await bot.add_cog(Tags(bot))
