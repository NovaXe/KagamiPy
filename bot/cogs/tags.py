import datetime

import discord
from discord import app_commands
from discord.ext import commands
from bot.utils.bot_data import Server
from bot.utils.ui import MessageScroller
from bot.utils.utils import link_to_file

from typing import Literal
from bot.kagami import Kagami
from datetime import date
from difflib import (
    get_close_matches,
    SequenceMatcher
)
from functools import partial
from io import BytesIO



class Tags(commands.GroupCog, group_name="tag"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        self.ctx_menus = [
            app_commands.ContextMenu(
                name="Create Local Tag",
                callback=self.create_local_tag_handler
            ),
            app_commands.ContextMenu(
                name="Create Global Tag",
                callback=self.create_global_tag_handler
            )
        ]

        for ctx_menu in self.ctx_menus:
            self.bot.tree.add_command(ctx_menu)

    async def cog_unload(self) -> None:
        for ctx_menu in self.ctx_menus:
            self.bot.tree.remove_command(ctx_menu.name, type=ctx_menu.type)

    get_group = app_commands.Group(name="get", description="gets a tag")
    set_group = app_commands.Group(name="set", description="sets a tag")
    delete_group = app_commands.Group(name="delete", description="deletes a tag")
    list_group = app_commands.Group(name="list", description="lists the tags")
    search_group = app_commands.Group(name="search", description="searches for tags")

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

    # Was going to write my own but snagged this baby off stack overflow lol
    @staticmethod
    def find_closely_matching_tags(search: str, tags: dict, n, cutoff=0.45):
        input_list = tags.items()
        matches = list()
        for key, value in input_list:
            if len(matches) > n:
                break
            if SequenceMatcher(None, search, key).ratio() >= cutoff:
                matches.append([key, value])
        return dict(matches)

    # Search Commands
    @search_group.command(name="global", description="searches for a global tag")
    async def search_global(self, interaction: discord.Interaction, search: str, count: int=10):
        await interaction.response.defer(thinking=True)
        matches = self.find_closely_matching_tags(search, self.bot.global_data['tags'], count)

        pages = self.create_tag_pages(source="global", tags=matches, is_search=True)
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        if count > 10:
            view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
            await interaction.edit_original_response(content=pages[0], view=view)

    @search_group.command(name="local", description="searches for a tag on this server_id")
    async def search_local(self, interaction: discord.Interaction, search: str, count: int = 10):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        matches = self.find_closely_matching_tags(search, server.tags, count)
        pages = self.create_tag_pages(source=interaction.guild.name, tags=matches, is_search=True)
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        if count > 10:
            view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
            await interaction.edit_original_response(content=pages[0], view=view)

    @app_commands.autocomplete(server=server_autocomplete)
    @search_group.command(name="server", description="searches for a tag on another server_id")
    async def search_server(self, interaction: discord.Interaction, server: str, search: str, count: int=10):
        await interaction.response.defer(thinking=True)
        guild_name = discord.utils.get(self.bot.guilds, id=int(server)).name
        server: Server = self.bot.fetch_server(server)
        matches = self.find_closely_matching_tags(search, server.tags, count)
        pages = self.create_tag_pages(source=guild_name, tags=matches, is_search=True)
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        if count > 10:
            view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
            await interaction.edit_original_response(content=pages[0], view=view)

    # Fetch Commands
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

        if "attachments" in tag_data:
            attachment_files = [discord.File(BytesIO(await link_to_file(link)), link.split('/')[-1]) for link in tag_data['attachments']][:10]
        else:
            attachment_files = []

        await interaction.edit_original_response(content=tag_data["content"], attachments=attachment_files)

    @app_commands.autocomplete(tag_name=tag_autocomplete)
    @get_group.command(name="local", description="get a tag from the server")
    async def get_local(self, interaction: discord.Interaction, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data = server.tags[tag_name]

        if "attachments" in tag_data:
            attachment_files = [discord.File(BytesIO(await link_to_file(link))) for link in tag_data['attachments']][
                               :10]
        else:
            attachment_files = []

        await interaction.edit_original_response(content=tag_data["content"], attachments=attachment_files)

    @app_commands.autocomplete(server=server_autocomplete, tag_name=tag_autocomplete)
    @get_group.command(name="server", description="get a tag from another server")
    async def get_server(self, interaction: discord.Interaction, server: str, tag_name: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(server)

        if tag_name not in server.tags.keys():
            await interaction.edit_original_response(content=f"The tag **`{tag_name}`** doesn't exist")
            return
        tag_data: dict = server.tags[tag_name]

        if "attachments" in tag_data:
            attachment_files = [discord.File(BytesIO(await link_to_file(link))) for link in tag_data['attachments']][:10]
        else:
            attachment_files = []

        await interaction.edit_original_response(content=tag_data["content"], attachments=attachment_files)


    async def create_local_tag_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='local')

    async def create_global_tag_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='global')

    async def send_create_modal(self, interaction: discord.Interaction, message: discord.Message, tag_type: Literal["local", "global"]):
        await interaction.response.send_modal(TagCreationModal(cog=self, tag_type=tag_type, message=message))

    # Set Commands
    @set_group.command(name="local", description="set a tag for this server")
    async def set_local(self, interaction: discord.Interaction, tag_name: str, content: str):
        print(interaction.user.name)
        await self.set_handler(interaction, tag_name, content, 'local')

    @set_group.command(name="global", description="set a global tag")
    async def set_global(self, interaction: discord.Interaction, tag_name: str, content: str):
        await self.set_handler(interaction, tag_name, content, 'global')

    async def set_handler(self, interaction: discord.Interaction, tag_name: str, content: str, mode: Literal['local', 'global'], attachment_links: list[str]=None):
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
            pass

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
    @list_group.command(name="global", description="lists the global tags")
    async def list_global(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        pages = self.create_tag_pages('global', self.bot.global_data['tags'])
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(content=pages[0], view=view)

    @list_group.command(name="local", description="lists this server's tags")
    async def list_local(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        pages = self.create_tag_pages(interaction.guild.name, server.tags)
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(content=pages[0], view=view)

    @app_commands.autocomplete(server=server_autocomplete)
    @list_group.command(name="server", description="lists another server's tags")
    async def list_server(self, interaction: discord.Interaction, server: str):
        await interaction.response.defer(thinking=True)
        guild_name = discord.utils.get(self.bot.guilds, id=int(server)).name
        server: Server = self.bot.fetch_server(server)
        pages = self.create_tag_pages(guild_name, server.tags)
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(view=view)


    @staticmethod
    def create_tag_pages(source: str, tags: dict, is_search=False):
        tag_count = len(tags)
        num_full_pages, last_page_elem_count = divmod(tag_count, 10)
        page_count = num_full_pages + 1 if last_page_elem_count else 0
        pages = [""] * page_count
        info_text = f"```swift\n{'Kagami' if source=='global' else source} has {tag_count}{' global' if source=='global' else ''} tags registered\n"
        if is_search:
            info_text = f"```swift\nFound {tag_count}{' global' if source == 'global' else ''} tags that are similar to your search {f'on {source}' if source !='global' else ''}\n"
        else:
            info_text = f"```swift\n{'Kagami' if source == 'global' else source} has {tag_count}{' global' if source == 'global' else ''} tags registered\n"

        page_index = 0
        elem_count = 0
        for tag_name, tag_data in sorted(tags.items()):
            if len(tag_name) <= 20:
                new_name = tag_name.ljust(20)
            else:
                new_name = (tag_name[:16] + " ...").ljust(20)

            creation_date = tag_data['creation_date'] if 'creation_date' in tag_data else '##/##/##'
            tag_author = tag_data['author'] if 'author' in tag_data else 'Unknown'
            content = f"{f'{page_index*10 + elem_count+1})'.ljust(4)}{new_name} - Created: {creation_date}  By: {tag_author}\n"
            pages[page_index] += content




            elem_count += 1
            if elem_count == 10 or (page_index + 1 == page_count and elem_count == last_page_elem_count):
                pages[page_index] = info_text + pages[page_index] + f"Page #: {page_index+1} / {page_count}\n```"
                page_index = 1
                elem_count = 0
        if not pages:
            pages.append(info_text + "\n```")
        return pages


class TagCreationModal(discord.ui.Modal, title="Create Tag"):
    def __init__(self, cog: Tags, tag_type: Literal["global", "local"], message: discord.Message):
        super().__init__()
        self.message = message
        self.cog = cog
        self.tag_type = tag_type
        self.tag_content.default = message.content
        self.tag_attachments.default = '\n'.join([attachment.url for attachment in message.attachments])


    tag_name = discord.ui.TextInput(label="Tag Name", placeholder='Enter the tag name')
    tag_content = discord.ui.TextInput(label="Tag Content", placeholder='Enter the tag content', style=discord.TextStyle.paragraph, max_length=2000)
    tag_attachments = discord.ui.TextInput(label="Attachments", placeholder="Put each link on a separate line", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        attachments = self.tag_attachments.value.split('\n') if self.tag_attachments.value else []
        await self.cog.set_handler(interaction=interaction, tag_name=self.tag_name.value, content=self.tag_content.value, mode=self.tag_type, attachment_links=attachments)


async def setup(bot):
    await bot.add_cog(Tags(bot))
