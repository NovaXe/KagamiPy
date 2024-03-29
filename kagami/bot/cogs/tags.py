import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.bot_data import Server
from bot.utils.ui import MessageScroller
from typing import Literal
from bot.kagami_bot import Kagami
from datetime import date
from bot.utils.utils import (
    find_closely_matching_dict_keys,
    link_to_attachment
)
from bot.utils.pages import createPageList, createPageInfoText, CustomRepr


class Tags(commands.GroupCog, group_name="tag"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        self.ctx_menus = [
            app_commands.ContextMenu(
                name="Create Local Tag",
                callback=self.ctx_menu_create_local_handler
            ),
            app_commands.ContextMenu(
                name="Create Global Tag",
                callback=self.ctx_menu_create_global_handler
            )
        ]

        for ctx_menu in self.ctx_menus:
            self.bot.tree.add_command(ctx_menu)

    custom_key_reprs: dict = {
        "author": CustomRepr("Created by"),
        "creation_date": CustomRepr("Created on"),
        "content": CustomRepr(ignored=True),
        "attachments": CustomRepr(ignored=True),
    }

    # ignored_key_values: list = ['content', 'attachments']

    async def cog_unload(self) -> None:
        for ctx_menu in self.ctx_menus:
            self.bot.tree.remove_command(ctx_menu.name, type=ctx_menu.type)

    get_group = app_commands.Group(name="get", description="gets a tag")
    set_group = app_commands.Group(name="set", description="sets a tag")
    delete_group = app_commands.Group(name="delete", description="deletes a tag")
    list_group = app_commands.Group(name="list", description="lists the tags")
    search_group = app_commands.Group(name="search", description="searches for tags")

    # Autocompletes
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
            tags = self.bot.global_data['tags']
        elif "local" == command_name:
            # print("local tag")
            tags = self.bot.fetch_server(interaction.guild_id).tags
        elif "server" == command_name:
            # print("server tag")

            # print(interaction.namespace["server"])
            # guild = discord.utils.get(interaction.user.mutual_guilds, name=interaction.namespace["server_id"])
            server_id = interaction.namespace["server"]
            if server_id:
                tags = self.bot.fetch_server(server_id).tags

        return [
                   app_commands.Choice(name=tag_name, value=tag_name)
                   for tag_name, tag_data in tags.items() if current.lower() in tag_name.lower()
               ][:25]

    # Search Commands
    async def search_handler(self, interaction, data, source, count):
        total_count = len(data)
        info_text = createPageInfoText(total_count, source, 'search', 'tags')
        pages = createPageList(info_text=info_text,
                               data=data,
                               total_item_count=total_count,
                               custom_reprs=self.custom_key_reprs
                               )

        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        if count > 10:
            view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
            await interaction.edit_original_response(content=pages[0], view=view)

    @search_group.command(name="global", description="searches for a global tag")
    async def search_global(self, interaction: discord.Interaction, search: str, count: int = 10):
        await interaction.response.defer(thinking=True)
        data: dict = find_closely_matching_dict_keys(search, self.bot.global_data['tags'], count)
        await self.search_handler(interaction, data, 'global', count)

    @search_group.command(name="local", description="searches for a tag on this server_id")
    async def search_local(self, interaction: discord.Interaction, search: str, count: int = 10):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        data: dict = find_closely_matching_dict_keys(search, server.tags, count)
        await self.search_handler(interaction, data, interaction.guild.name, count)

    @app_commands.autocomplete(server=server_autocomplete)
    @search_group.command(name="server", description="searches for a tag on another server_id")
    async def search_server(self, interaction: discord.Interaction, server: str, search: str, count: int = 10):
        await interaction.response.defer(thinking=True)
        guild_name = discord.utils.get(self.bot.guilds, id=int(server)).name
        server: Server = self.bot.fetch_server(server)
        data: dict = find_closely_matching_dict_keys(search, server.tags, count)
        await self.search_handler(interaction, data, guild_name, count)

    # Tag getter Commands
    @staticmethod
    async def get_handler(interaction: discord.Interaction, tag_name, tag_data):
        if "attachments" in tag_data:
            attachment_files = []
            for index, link in enumerate(tag_data['attachments']):
                file = await link_to_attachment(link, file_name=f"{tag_name}{index}")
                attachment_files.append(file)
        else:
            attachment_files = []

        await interaction.edit_original_response(content=tag_data["content"], attachments=attachment_files[:10])

    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @get_group.command(name="global", description="get a global tag")
    async def get_global(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        # if not self.bot.global_data['tags']:
        #     await interaction.edit_original_response(content="There are no global tags")
        #     return
        if tag_name not in self.bot.global_data['tags'].keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data = self.bot.global_data['tags'][tag_name]
        await self.get_handler(interaction, tag_name, tag_data)

    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @get_group.command(name="local", description="get a tag from the server")
    async def get_local(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data = server.tags[tag_name]
        await self.get_handler(interaction, tag_name, tag_data)

    @app_commands.autocomplete(server=server_autocomplete, tag_name=tag_autocomplete)
    @get_group.command(name="server", description="get a tag from another server")
    async def get_server(self, interaction: discord.Interaction, server: str, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(server)

        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data: dict = server.tags[tag_name]
        await self.get_handler(interaction, tag_name, tag_data)

    # Create Modal Handlers
    async def ctx_menu_create_local_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='local')

    async def ctx_menu_create_global_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='global')

    async def send_create_modal(self, interaction: discord.Interaction, message: discord.Message,
                                tag_type: Literal["local", "global"]):
        await interaction.response.send_modal(TagCreationModal(cog=self, tag_type=tag_type, message=message))

    # Set Commands
    async def set_handler(self, interaction: discord.Interaction, tag_name: str, content: str,
                          mode: Literal['local', 'global'], attachment_links: list[str] = None):
        if attachment_links is not None:
            attachment_links = attachment_links[:10]
        else:
            attachment_links = []

        if mode == 'local':
            await interaction.response.defer(thinking=True)
            server: Server = self.bot.fetch_server(interaction.guild_id)
            if tag_name in server.tags.keys():
                await interaction.edit_original_response(content=f"The tag **`{tag_name}`** already exists")
                return
            server.tags.update({
                tag_name: {
                    "content": content,
                    "author": interaction.user.name,
                    "creation_date": date.today().strftime("%m/%d/%y"),
                    "attachments": attachment_links
                }})

            await interaction.edit_original_response(content=f"Added tag **`{tag_name}`** to the server")

        elif mode == 'global':
            await interaction.response.defer(thinking=True)
            if tag_name in self.bot.global_data['tags'].keys():
                await interaction.edit_original_response(content=f"The tag **`{tag_name}`** already exists")
                return
            self.bot.global_data['tags'].update({
                tag_name: {
                    "content": content,
                    "author": interaction.user.name,
                    "creation_date": date.today().strftime("%m/%d/%y"),
                    "attachments": attachment_links
                }})

            await interaction.edit_original_response(content=f"Added tag **`{tag_name}`** to globals")

    @set_group.command(name="local", description="set a tag for this server")
    async def set_local(self, interaction: discord.Interaction, tag_name: str, content: str):
        print(interaction.user.name)
        await self.set_handler(interaction, tag_name, content, 'local')

    @set_group.command(name="global", description="set a global tag")
    async def set_global(self, interaction: discord.Interaction, tag_name: str, content: str):
        await self.set_handler(interaction, tag_name, content, 'global')

    # Delete Commands
    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @delete_group.command(name="local", description="Deletes a tag from this server")
    async def delete_local(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return

        server.tags.pop(tag_name, None)
        await interaction.edit_original_response(content=f"The tag **`{tag_name}`** has been deleted")

    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @delete_group.command(name="global", description="Deletes a global tag")
    async def delete_global(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        if tag_name not in self.bot.global_data['tags'].keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        self.bot.global_data['tags'].pop(tag_name, None)
        await interaction.edit_original_response(content=f"The global tag **`{tag_name}`** has been deleted")

    # List Commands
    async def list_handler(self, interaction, data, source):
        total_count = len(data)
        info_text = createPageInfoText(total_count, source, 'data', 'tags')
        pages = createPageList(info_text=info_text,
                               data=data,
                               total_item_count=total_count,
                               custom_reprs=self.custom_key_reprs
                               )

        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(content=pages[0], view=view)

    @list_group.command(name="global", description="lists the global tags")
    async def list_global(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        data: dict = self.bot.global_data['tags']
        await self.list_handler(interaction, data, 'global')

    @list_group.command(name="local", description="lists this server's tags")
    async def list_local(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        data: dict = server.tags
        await self.list_handler(interaction, data, interaction.guild.name)

    @app_commands.autocomplete(server=server_autocomplete)
    @list_group.command(name="server", description="lists another server's tags")
    async def list_server(self, interaction: discord.Interaction, server: str):
        await interaction.response.defer(thinking=True)
        guild_name = discord.utils.get(self.bot.guilds, id=int(server)).name
        server: Server = self.bot.fetch_server(server)
        data: dict = server.tags
        await self.list_handler(interaction, data, guild_name)


class TagCreationModal(discord.ui.Modal, title="Create Tag"):
    def __init__(self, cog: Tags, tag_type: Literal["global", "local"], message: discord.Message):
        super().__init__()
        self.message = message
        self.cog = cog
        self.tag_type = tag_type
        self.tag_content.default = message.content
        self.tag_attachments.default = '\n'.join([attachment.url for attachment in message.attachments])

    tag_name = discord.ui.TextInput(label="Tag Name", placeholder='Enter the tag name')
    tag_content = discord.ui.TextInput(label="Tag Content", placeholder='Enter the tag content',
                                       style=discord.TextStyle.paragraph, max_length=2000, required=False)
    tag_attachments = discord.ui.TextInput(label="Attachments", placeholder="Put each link on a separate line",
                                           style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        attachments = self.tag_attachments.value.split('\n') if self.tag_attachments.value else []
        await self.cog.set_handler(interaction=interaction, tag_name=self.tag_name.value,
                                   content=self.tag_content.value, mode=self.tag_type, attachment_links=attachments)


async def setup(bot):
    await bot.add_cog(Tags(bot))
