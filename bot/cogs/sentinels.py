import re
import typing
from abc import ABC

import discord
import discord.ui
from discord.ext import commands
from discord import app_commands
from bot.kagami import Kagami
from bot.utils.bot_data import Server
from bot.utils.ui import MessageScroller



class SentinelTransformer(app_commands.Transformer, ABC):
    def __init__(self, cog: 'Sentinels', mode: typing.Literal['global', 'local']):
        self.mode = mode
        self.cog: 'Sentinels' = cog


    async def transform(self, interaction: discord.Interaction, value: str) -> dict[str, dict]:
        source = None
        if self.mode == 'server':
            server: Server = self.cog.bot.fetch_server(interaction.guild_id)
            source = server.sentinels
        elif self.mode == 'global':
            source = self.cog.bot.global_data['sentinels']

        return source[value]

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        source = None
        if self.mode == 'server':
            server: Server = self.cog.bot.fetch_server(interaction.guild_id)
            source = server.sentinels
        elif self.mode == 'global':
            source = self.cog.bot.global_data['sentinels']

        options = [app_commands.Choice(name=sentinel_phrase, value=sentinel_phrase)
                   for sentinel_phrase, sentinel_data in source['sentinels']
                   if current.lower() in sentinel_phrase.lower()][:25]



class Sentinels(commands.GroupCog, group_name="sentinel"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        # self.globalTransformer = SentinelTransformer(self, 'global')
        # self.localTransformer = SentinelTransformer(self, 'local')
        # self.local_sentinel_autocomplete = self.wrapped_sentinel_autocomplete(mode='global')



    add_group = app_commands.Group(name="add", description="Create a new sentinel")
    remove_group = app_commands.Group(name="remove", description="Remove a sentinel")
    edit_group = app_commands.Group(name="edit", description="Edit an existing sentinel")
    list_group = app_commands.Group(name="list", description="Lists all sentinels")
    info_group = app_commands.Group(name="info", description="Gets sentinel info")

    async def sentinel_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        source = None
        if interaction.command.name == 'server':
            server: Server = self.bot.fetch_server(interaction.guild_id)
            source = server.sentinels
        elif interaction.command.name == 'global':
            source = self.bot.global_data['sentinels']

        options = [
                      app_commands.Choice(name=sentinel_phrase, value=sentinel_phrase)
                      for sentinel_phrase, sentinel_data in source.items()
                      if current.lower() in sentinel_phrase.lower()
        ][:25]
        return options

    # def wrapped_sentinel_autocomplete(self, mode: typing.Literal['local', 'global']):
    #     async def callback(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    #         source = None
    #         if mode == 'server':
    #             server: Server = self.bot.fetch_server(interaction.guild_id)
    #             source = server.sentinels
    #         elif mode == 'global':
    #             source = self.bot.global_data['sentinels']
    #
    #         options = [app_commands.Choice(name=sentinel_phrase, value=sentinel_phrase)
    #                    for sentinel_phrase, sentinel_data in source['sentinels']
    #                    if current.lower() in sentinel_phrase.lower()][:25]
    #     return callback


    @add_group.command(name="global", description="Creates a new global sentinel")
    async def add_global(self, interaction: discord.Interaction, sentinel_phrase: str, response: str=None, reactions: str=None):
        await interaction.response.defer(thinking=True)
        # reactions = re.findall('(<a?:[a-zA-Z0-9_]+:[0-9]+>)', reactions)
        # reaction_names = [f":{re.match(r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>$', reaction).group(2)}:" for reaction in reactions]
        # discord.PartialEmoji.from_str(reaction)
        if reactions:
            reactions = [reaction for reaction in reactions.split(' ') if reaction]


        print(reactions)
        new_sentinel = {
            'response': response,
            'reactions': reactions,
            'uses': 0
        }
        self.bot.global_data['sentinels'].update({
            sentinel_phrase: new_sentinel
        })
        await interaction.edit_original_response(content=f'Added the global sentinel `{sentinel_phrase}`')

    @add_group.command(name="local", description="Creates a new global sentinel")
    async def add_local(self, interaction: discord.Interaction, sentinel_phrase: str, response: str = None, reaction: str = None):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        new_sentinel = {
            'response': response,
            'reactions': reaction,
            'uses': 0
        }
        server.sentinels.update({
            sentinel_phrase: new_sentinel
        })
        await interaction.edit_original_response(content=f'Added the sentinel `{sentinel_phrase}` to {interaction.guild.name}')
        pass

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @remove_group.command(name="global", description="Remove a global sentinel")
    async def remove_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        await interaction.response.defer(thinking=True)
        if sentinel_phrase not in self.bot.global_data['sentinels'].keys():
            await interaction.edit_original_response(content=f"The global sentinel **`{sentinel_phrase}`** doesn't exist")
            return

        self.bot.global_data['sentinels'].pop(sentinel_phrase, None)
        await interaction.edit_original_response(content=f'Removed the global sentinel `{sentinel_phrase}`')
        pass

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @remove_group.command(name="local", description="Remove a local sentinel")
    async def remove_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        await interaction.response.defer(thinking=True)
        if sentinel_phrase not in server.sentinels.keys():
            await interaction.edit_original_response(content=f"The sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        server.sentinels.pop(sentinel_phrase, None)
        await interaction.edit_original_response(content=f'Removed the sentinel `{sentinel_phrase}` from `{interaction.guild.name}`')

        pass

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @edit_group.command(name='global', description='Edit a global sentinel')
    async def edit_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        if sentinel_phrase not in self.bot.global_data['sentinels'].keys():
            await interaction.response.send_message(content=f"The global sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        await interaction.response.send_modal(SentinelEditorModal(self.bot.global_data['sentinels'], sentinel_phrase))

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @edit_group.command(name='local', description='Edit a local sentinel')
    async def edit_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if sentinel_phrase not in server.sentinels.keys():
            await interaction.response.send_message(content=f"The sentinel **`{sentinel_phrase}`** doesn't exist on `{interaction.guild.name}`")
            return
        await interaction.response.send_modal(SentinelEditorModal(self.bot.fetch_server(interaction.guild_id).sentinels, sentinel_phrase))


    @list_group.command(name='global', description="List all global sentinels")
    async def list_global(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        pages = self.create_sentinel_pages('global', self.bot.global_data['sentinels'])
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(content=pages[0], view=view)

    @list_group.command(name='local', description="List all local sentinels")
    async def list_local(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        pages = self.create_sentinel_pages('local', server.sentinels)
        message = await(await interaction.edit_original_response(content=pages[0])).fetch()
        view = MessageScroller(message=message, pages=pages, home_page=0, timeout=300)
        await interaction.edit_original_response(content=pages[0], view=view)

    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @info_group.command(name='global', description='Gets the info of a global sentinel')
    async def info_global(self, interaction: discord.Interaction, sentinel_phrase: str):
        await interaction.response.defer(thinking=True)
        if sentinel_phrase not in self.bot.global_data['sentinels'].keys():
            await interaction.edit_original_response(content=f"The global sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        sentinel_data = self.bot.global_data['sentinels'][sentinel_phrase]
        content = await self.info_response(sentinel_phrase, sentinel_data)

        await interaction.edit_original_response(content=content)


    @app_commands.autocomplete(sentinel_phrase=sentinel_autocomplete)
    @info_group.command(name='local', description='Gets the info of a local sentinel')
    async def info_local(self, interaction: discord.Interaction, sentinel_phrase: str):
        await interaction.response.defer(thinking=True)
        server: Server = self.bot.fetch_server(interaction.guild_id)
        if sentinel_phrase not in server.sentinels.keys():
            await interaction.edit_original_response(content=f"The sentinel **`{sentinel_phrase}`** doesn't exist")
            return
        sentinel_data = server.sentinels[sentinel_phrase]
        content = await self.info_response(sentinel_phrase, sentinel_data)

        await interaction.edit_original_response(content=content)


    @staticmethod
    async def info_response(sentinel_phrase, sentinel_data):
        reactions = []
        if _reactions := sentinel_data['reactions']:
            for reaction in _reactions:
                partial_emoji = discord.PartialEmoji.from_str(reaction)
                if partial_emoji.is_custom_emoji():
                    name = f':{partial_emoji.name}:'  # {partial_emoji.id}
                else:
                    name = partial_emoji.name
                reactions.append(name)
        else:
            reactions.append('None')
        reactions = f"[ {' '.join(reactions)} ]"

        content = f'```swift\n' \
                  f'Local Sentinel Info: {sentinel_phrase}\n' \
                  f'──────────────────────────────────────\n' \
                  f'Reactions:  {reactions}\n' \
                  f'Uses:       {sentinel_data["uses"]}\n' \
                  f'```'
        return content

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return
        server: Server = self.bot.fetch_server(message.guild.id)

        await self.process_sentinel_event(message, self.bot.global_data['sentinels'])
        await self.process_sentinel_event(message, server.sentinels)

        # for sentinel_phrase, sentinel_data in self.bot.global_data['sentinels']:
        #     if sentinel_phrase in message.content:
        #         for reaction in sentinel_data['reactions']:
        #             await message.add_reaction(reaction)
        #         await message.reply(content=sentinel_data['response'])
        #         sentinel_data['uses'] += 1
        #
        # for sentinel_phrase, sentinel_data in server.sentinels:
        #     if sentinel_phrase in message.content:
        #         for reaction in sentinel_data['reactions']:
        #             await message.add_reaction(reaction)
        #         await message.reply(content=sentinel_data['response'])
        #         sentinel_data['uses'] += 1
        # pass

    @staticmethod
    async def process_sentinel_event(message: discord.Message, sentinels):
        content = message.content.lower()
        if content := content.split(' '):
            pass

        for sentinel_phrase, sentinel_data in sentinels.items():
            if sentinel_phrase.lower() in content:
                if reactions := sentinel_data['reactions']:
                    for reaction in reactions:
                        await message.add_reaction(reaction)
                if response := sentinel_data['response']:
                    await message.reply(content=response)
                sentinel_data['uses'] += 1



    @staticmethod
    def create_sentinel_pages(source: str, sentinels: dict, is_search=False):
        sentinel_count = len(sentinels)
        num_full_pages, last_page_elem_count = divmod(sentinel_count, 10)
        page_count = num_full_pages + 1 if last_page_elem_count else 0
        pages = [""] * page_count
        info_text = f"```swift\n{'Kagami' if source == 'global' else source} has {sentinel_count}{' global' if source == 'global' else ''} tags registered\n"
        if is_search:
            info_text = f"```swift\nFound {sentinel_count}{' global' if source == 'global' else ''} tags that are similar to your search {f'on {source}' if source != 'global' else ''}\n"
        else:
            info_text = f"```swift\n{'Kagami' if source == 'global' else source} has {sentinel_count}{' global' if source == 'global' else ''} tags registered\n"

        page_index = 0
        elem_count = 0
        for sentinel_phrase, sentinel_data in sorted(sentinels.items()):
            if len(sentinel_phrase) <= 20:
                new_name = sentinel_phrase.ljust(20)
            else:
                new_name = (sentinel_phrase[:16] + " ...").ljust(20)

            response = sentinel_data['response'] if 'response' in sentinel_data else 'None'
            reactions = []
            if sentinel_data['reactions']:
                for reaction in sentinel_data['reactions']:
                    partial_emoji = discord.PartialEmoji.from_str(reaction)
                    if partial_emoji.is_custom_emoji():
                        name = f':{partial_emoji.name}:'  # {partial_emoji.id}
                    else:
                        name = partial_emoji.name
                    reactions.append(name)
            else:
                reactions.append('None')
            reactions = f"[ {' '.join(reactions)} ]"


            uses = sentinel_data['uses'] if 'uses' in sentinel_data else 0
            content = f"{f'{page_index * 10 + elem_count + 1})'.ljust(4)}{new_name} - Reactions: {reactions}  Uses: {uses}\n"
            pages[page_index] += content

            elem_count += 1
            if elem_count == 10 or (page_index + 1 == page_count and elem_count == last_page_elem_count):
                pages[page_index] = info_text + pages[page_index] + f"Page #: {page_index + 1} / {page_count}\n```"
                page_index = 1
                elem_count = 0
        if not pages:
            pages.append(info_text + "\n```")
        return pages


class SentinelEditorModal(discord.ui.Modal, title='Edit Sentinels'):
    def __init__(self, sentinel_source, sentinel_phrase):
        super().__init__()
        self.sentinel_source = sentinel_source
        self.original_sentinel_phrase = sentinel_phrase
        self.sentinel_phrase.default = sentinel_phrase
        self.response.default = sentinel_source[sentinel_phrase]['response']
        self.reactions_txt.default = ' '.join(sentinel_source[sentinel_phrase]['reactions'])

    sentinel_phrase = discord.ui.TextInput(label='Phrase', placeholder='Enter the phrase the bot will listen for')
    response = discord.ui.TextInput(label="Response", placeholder='Enter the response to the sentinel event')
    reactions_txt = discord.ui.TextInput(label="Reactions", placeholder="Type your reactions like this :emote: :emote:")


    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.sentinel_source.pop(self.original_sentinel_phrase, None)
        self.sentinel_source.update({
            self.sentinel_phrase.value: {
                'response': self.response.value,
                'reactions': [f':{emote}:' for emote in self.reactions_txt.value.split(':') if emote]
            }
        })
        await interaction.response.send_message(content=f'Edited the sentinel `{self.original_sentinel_phrase}`'
                                                        f' {f"now called {self.sentinel_phrase.value}" if self.original_sentinel_phrase != self.sentinel_phrase.value else ""}')




async def setup(bot):
    await bot.add_cog(Sentinels(bot))
