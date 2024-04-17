import json
from dataclasses import dataclass
import aiosqlite

import discord
from discord import app_commands, Interaction, Message, Member
from discord._types import ClientT
from discord.ext import commands
from discord.app_commands import Transformer, Group, Transform, Choice, Range, autocomplete
from discord.ext.commands import GroupCog, Cog

from bot.ext import errors
from bot.utils.bot_data import Server, OldTag
from bot.utils.database import Database
from bot.utils.interactions import respond
from bot.utils.ui import MessageScroller
from typing import Literal, Union, List, Any
from bot.kagami_bot import Kagami
from datetime import date
from bot.utils.utils import (
    find_closely_matching_dict_keys,
    link_to_attachment
)
from bot.utils.pages import createPageList, createPageInfoText, CustomRepr


class TagDB(Database):
    @dataclass
    class TagSettings(Database.Row):
        guild_id: int
        tags_enabled: bool = True
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS TagSettings(
        guild_id INTEGER NOT NULL,
        tags_enabled INTEGER DEFAULT 1,
        PRIMARY KEY (guild_id),
        FOREIGN KEY (guild_id) REFERENCES Guild(id)
        ON UPDATE CASCADE ON DELETE CASCADE)
        """
        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS TagSettings
        """
        QUERY_UPSERT = """
        INSERT INTO MusicSettings (guild_id, tags_enabled)
        ON CONFLICT (guild_id)
        DO UPDATE SET tags_enabled = :tags_enabled
        """
        QUERY_SELECT = """
        SELECT * FROM TagSettings
        WHERE guild_id = ?
        """
        QUERY_DELETE = """
        DELETE FROM TagSettings
        WHERE guild_id = ?
        """

    @dataclass
    class Tag(Database.Row):
        guild_id: int
        name: str
        content: str
        embed: str # raw json representing a discord embed
        author_id: int
        creation_date: str = None
        modified_date: str = None
        QUERY_CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS Tag(
        guild_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        content TEXT,
        embed TEXT,
        author_id INTEGER NOT NULL,
        creation_date TEXT NOT NULL ON CONFLICT REPLACE DEFAULT CURRENT_DATE,
        modified_date TEXT NOT NULL ON CONFLICT REPLACE DEFAULT CURRENT_DATE,
        PRIMARY KEY(guild_id, name),
        FOREIGN KEY(guild_id) REFERENCES Guild(id)
        ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY(author_id) REFERENCES User(id) 
        ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """ # CHECK (CONTENT NOT NULL OR EMBED NOT NULL)

        QUERY_DROP_TABLE = """
        DROP TABLE IF EXISTS Tag
        """
        QUERY_AFTER_INSERT_TRIGGER = """
        CREATE TRIGGER IF NOT EXISTS set_creation_date_after_insert
        AFTER INSERT ON Tag
        """
        # QUERY_BEFORE_INSERT_INSERT_GUILD_TRIGGER = """
        # CREATE TRIGGER IF NOT EXISTS insert_guild_before_insert
        # """
        TRIGGER_BEFORE_INSERT_GUILD = """
        CREATE TRIGGER IF NOT EXISTS insert_guild_before_insert
        BEFORE INSERT ON Playlist
        BEGIN
            INSERT INTO Guild(id)
            values(NEW.guild_id)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_BEFORE_INSERT_USER_TRIGGER = """
        CREATE TRIGGER IF NOT EXISTS insert_user_before_insert
        BEFORE INSERT ON Tag
        BEGIN
            INSERT INTO User(id)
            values(NEW.author_id)
            ON CONFLICT DO NOTHING;
        END
        """
        QUERY_AFTER_UPDATE_TRIGGER = """
        CREATE TRIGGER IF NOT EXISTS set_modified_data_after_update
        AFTER UPDATE ON Tag
        BEGIN
            UPDATE Tag
            SET modified_date = NULL 
            WHERE (guild_id = NEW.guild_id) AND (name = NEW.name);
        END
        """
        QUERY_INSERT = """
        INSERT INTO Tag (guild_id, name, content, embed, author_id, creation_date, modified_date)
        VALUES (:guild_id, :name, :content, :embed, :author_id, :creation_date, :creation_date)
        ON CONFLICT DO NOTHING
        """
        # QUERY_INSERT = """
        # INSERT INTO Tag (guild_id, name, content, embed, author_id, creation_date)
        # VALUES (:guild_id, :name, :content, :embed, :author_id,
        #         coalesce(:creation_date, date()), coalesce(:creation_date, date()))
        # ON CONFLICT DO NOTHING
        # """
        QUERY_UPSERT = """
        INSERT INTO Tag (guild_id, name, content, embed, author_id, creation_date)
        VALUES (:guild_id, :name, :content, :embed, :author_id, :creation_date)
        ON CONFLICT SET (guild_id, name)
        DO UPDATE SET content = :content AND embed = :embed
        """
        QUERY_UPDATE = """
        UPDATE Tag SET content = :content AND embed = :embed
        WHERE guild_id = :guild_id AND name = :name
        """
        QUERY_EDIT = """
        UPDATE Tag SET name=:name AND content = :content AND embed = :embed
        WHERE guild_id = :guild_id AND name = :old_name
        """
        QUERY_SELECT = """
        SELECT * FROM Tag 
        WHERE guild_id = ? AND name = ?;
        """
        QUERY_DELETE = """
        DELETE FROM Tag
        WHERE guild_id = ? AND name = ?
        RETURNING *
        """
        QUERY_DELETE_FROM_USER = """
        DELETE FROM Tag
        WHERE author_id = ?
        RETURNING *
        """
        QUERY_SELECT_LIKE = """
        SELECT * FROM Tag
        WHERE guild_id = ? AND name LIKE ?
        LIMIT ? OFFSET ?
        """
        QUERY_SELECT_LIKE_NAMES = """
        SELECT name FROM Tag
        WHERE (guild_id = ?) AND (name LIKE ?)
        LIMIT ? OFFSET ?
        """

    class TagsDisabled(errors.CustomCheck):
        MESSAGE = "The tag feature is disabled"

    class TagAlreadyExists(errors.CustomCheck):
        MESSAGE = "There is already a tag with that name"

    class TagNotFound(errors.CustomCheck):
        MESSAGE = "There is no tag with that name"

    async def init(self, drop: bool=False):
        if drop: await self.dropTables()
        await self.createTables()
        await self.createTriggers()

    async def createTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(TagDB.TagSettings.QUERY_CREATE_TABLE)
            await db.execute(TagDB.Tag.QUERY_CREATE_TABLE)
            await db.commit()

    async def createTriggers(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(TagDB.Tag.QUERY_BEFORE_INSERT_USER_TRIGGER)
            await db.execute(TagDB.Tag.TRIGGER_BEFORE_INSERT_GUILD)
            await db.commit()

    async def dropTables(self):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(TagDB.TagSettings.QUERY_DROP_TABLE)
            await db.execute(TagDB.Tag.QUERY_DROP_TABLE)
            await db.commit()

    async def insertTag(self, tag: Tag) -> bool:
        async with aiosqlite.connect(self.file_path) as db:
            cursor = await db.execute(TagDB.Tag.QUERY_INSERT, tag.asdict())
            row_count = cursor.rowcount
            await db.commit()
        return row_count > 0

    async def insertTags(self, tags: list[Tag]):
        async with aiosqlite.connect(self.file_path) as db:
            data = [tag.asdict() for tag in tags]
            await db.executemany(TagDB.Tag.QUERY_INSERT, data)
            await db.commit()

    async def updateTag(self, tag: Tag):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(TagDB.Tag.QUERY_UPDATE, tag.asdict())
            await db.commit()

    async def editTag(self, old_name: str, tag: Tag):
        async with aiosqlite.connect(self.file_path) as db:
            data = tag.asdict()
            data["old_name"] = old_name
            await db.execute(TagDB.Tag.QUERY_EDIT, data)

    async def deleteTag(self, guild_id: int, name: str) -> Tag:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = TagDB.Tag.rowFactory
            result = await db.execute_fetchall(TagDB.Tag.QUERY_DELETE, (guild_id, name))
            await db.commit()
        return result[0] if result else None

    async def fetchTag(self, guild_id: int, tag_name: str) -> Tag:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = TagDB.Tag.rowFactory
            result: list[TagDB.Tag] = await db.execute_fetchall(TagDB.Tag.QUERY_SELECT, (guild_id, tag_name))
        return result[0] if result else None

    async def fetchSimilarTagNames(self, guild_id: int, tag_name: str, limit: int=1, offset=0) -> list[str]:
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(TagDB.Tag.QUERY_SELECT_LIKE_NAMES,
                                                         (guild_id, f"%{tag_name}%", limit, offset))
            names = [n[0] for n in names]
        return names


class LocalTagTransformer(Transformer):
    async def autocomplete(self,
                           interaction: Interaction, value: Union[int, float, str], /
                           ) -> List[Choice[str]]:
        bot: Kagami = interaction.client
        db = TagDB(bot.config.db_path)
        names = await db.fetchSimilarTagNames(guild_id=interaction.guild_id,
                                              tag_name=value,
                                              limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction, value: Any, /) -> TagDB.Tag:
        bot: Kagami = interaction.client
        db = TagDB(bot.config.db_path)
        tag = await db.fetchTag(guild_id=interaction.guild_id,
                                tag_name=value)
        return tag


class GlobalTagTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           value: Union[int, float, str], /
                           ) -> List[Choice[str]]:
        bot: Kagami = interaction.client
        db = TagDB(bot.config.db_path)
        names = await db.fetchSimilarTagNames(guild_id=0, tag_name=value, limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction,
                        value: Any, /) -> TagDB.Tag:
        bot: Kagami = interaction.client
        db = TagDB(bot.config.db_path)
        tag = await db.fetchTag(guild_id=0, tag_name=value)
        return tag


class GuildTagTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           value: Union[int, float, str], /
                           ) -> List[Choice[Union[int, float, str]]]:
        guild_id = int(interaction.namespace.guild)
        bot: Kagami = interaction.client
        db = TagDB(bot.config.db_path)
        names = await db.fetchSimilarTagNames(guild_id=guild_id,
                                              tag_name=value,
                                              limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction,
                        value: str, /) -> TagDB.Tag:
        guild_id = int(interaction.namespace.guild)
        bot: Kagami = interaction.client
        db = TagDB(bot.config.db_path)
        tag = await db.fetchTag(guild_id=guild_id, tag_name=value)
        return tag


class GuildTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           current: str) -> list[Choice[str]]:
        user = interaction.user
        guilds = list(user.mutual_guilds)
        choices = [Choice(name=guild.name, value=str(guild.id)) for guild in guilds
                   if current.lower() in guild.name.lower()][:25]
        return choices

    async def transform(self, interaction: Interaction,
                        value: str, /) -> discord.Guild:
        guild_id = int(value)
        guild = interaction.client.get_guild(guild_id)
        return guild


class Tags(GroupCog, group_name="t"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        self.database = TagDB(bot.config.db_path)
        self.ctx_menus = [
            app_commands.ContextMenu(
                name="Make Local Tag",
                callback=self.ctx_menu_create_local_handler
            ),
            app_commands.ContextMenu(
                name="Make Global Tag",
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

    @commands.is_owner()
    @commands.command(name="migrate_tags")
    async def migrateCommand(self, ctx):
        await self.migrateTagData()
        await ctx.send("migrated tags probably")

    async def migrateTagData(self):
        async def convertTag(_guild_id: int, _tag_name: str, _tag: OldTag) -> TagDB.Tag:
            user = discord.utils.get(self.bot.get_all_members(), name=_tag.author)
            user_id = user.id if user else 0
            return TagDB.Tag(guild_id=_guild_id, name=_tag_name,
                             content=_tag.content, embed=None, author_id=user_id,
                             creation_date=_tag.creation_date)

        for server_id, server in self.bot.data.servers.items():
            server_id = int(server_id)
            try: guild = await self.bot.fetch_guild(server_id)
            except discord.NotFound: continue
            new_tags = [await convertTag(server_id, tag_name, tag) for tag_name, tag in server.tags.items()]
            await self.database.insertTags(new_tags)

        new_global_tags = [await convertTag(0, tag_name, tag)
                           for tag_name, tag in self.bot.data.globals.tags.items()]
        await self.database.insertTags(new_global_tags)

    async def cog_unload(self) -> None:
        for ctx_menu in self.ctx_menus:
            self.bot.tree.remove_command(ctx_menu.name, type=ctx_menu.type)

    async def cog_load(self) -> None:
        await self.database.init(drop=self.bot.config.drop_tables)
        await self.migrateTagData()

    async def interaction_check(self, interaction: discord.Interaction[ClientT], /) -> bool:
        # await self.bot.database.upsertGuild(interaction.guild)
        return True

    get_group = Group(name="get", description="gets a tag")
    set_group = Group(name="set", description="sets a tag")
    delete_group = Group(name="delete", description="deletes a tag")
    edit_group = Group(name="edit", description="edits a tag")
    # list_group = app_commands.Group(name="list", description="lists the tags")
    # search_group = app_commands.Group(name="search", description="searches for tags")

    LocalTag_Transform = Transform[TagDB.Tag, LocalTagTransformer]
    GlobalTag_Transform = Transform[TagDB.Tag, GlobalTagTransformer]
    GuildTag_Transform = Transform[TagDB.Tag, GuildTagTransformer]
    Guild_Transform = Transform[discord.Guild, GuildTransformer]

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

    @set_group.command(name="global", description="add a new global tag")
    async def set_global(self, interaction: Interaction, tag: GlobalTag_Transform,
                         content: str=None, embed: str=None):
        await respond(interaction)
        if tag: raise TagDB.TagAlreadyExists

        tag = TagDB.Tag(guild_id=0,
                        name=interaction.namespace.tag,
                        content=content,
                        embed=embed,
                        author_id=interaction.user.id)
        await self.database.insertTag(tag)
        await respond(interaction, f"Created the global tag `{tag.name}`")

    @set_group.command(name="here", description="add a new local tag")
    async def set_here(self, interaction: Interaction, tag: LocalTag_Transform,
                       content: str=None, embed: str=None):
        await respond(interaction)
        if tag: raise TagDB.TagAlreadyExists

        tag = TagDB.Tag(guild_id=interaction.guild_id,
                        name=interaction.namespace.tag,
                        content=content,
                        embed=embed,
                        author_id=interaction.user.id)
        await self.database.insertTag(tag)
        await respond(interaction, f"Created the local tag `{tag.name}`")

    # @set_group.command(name="elsewhere", description="add a new tag to another server")
    async def set_elsewhere(self, interaction: Interaction,
                            guild: Guild_Transform, tag: GuildTag_Transform,
                            content: str=None, embed: str=None):
        await respond(interaction)
        if tag: raise TagDB.TagAlreadyExists
        guild_name = guild.name
        tag = TagDB.Tag(guild_id=guild.id,
                        name=interaction.namespace.tag,
                        content=content,
                        embed=embed,
                        author_id=interaction.user.id)
        await self.database.insertTag(tag)
        await respond(interaction, f"Created tag `{tag.name}` for guild `{guild_name}`")



    @get_group.command(name="global", description="fetch a global tag")
    async def get_global(self, interaction: Interaction,
                         tag: GlobalTag_Transform):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        if tag.embed:
            embed_dict = json.loads(tag.embed)
            embeds = [discord.Embed.from_dict(embed_dict)]
        else:
            embeds = []
        content = tag.content if tag.content and tag.content != '' else "`The tag has no content`"
        await respond(interaction, content=content, embeds=embeds)


    @get_group.command(name="here", description="fetch a local tag")
    async def get_here(self, interaction: Interaction,
                       tag: LocalTag_Transform):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        if tag.embed:
            embed_dict = json.loads(tag.embed)
            embeds = [discord.Embed.from_dict(embed_dict)]
        else:
            embeds = []
        content = tag.content if tag.content and tag.content != '' else "`The tag has no content`"
        await respond(interaction, content=content, embeds=embeds)

    @get_group.command(name="elsewhere", description="fetch a tag from another server")
    async def get_elsewhere(self, interaction: Interaction,
                            guild: Guild_Transform, tag: GuildTag_Transform):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        if tag.embed:
            embed_dict = json.loads(tag.embed)
            embeds = [discord.Embed.from_dict(embed_dict)]
        else:
            embeds = []
        content = tag.content if tag.content and tag.content != '' else "`The tag has no content`"
        await respond(interaction, content=content, embeds=embeds)

    @delete_group.command(name="global", description="delete a global tag")
    async def delete_global(self, interaction: Interaction,
                            tag: GlobalTag_Transform):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        await self.database.deleteTag(guild_id=0, name=tag.name)
        await respond(interaction, f"Deleted the global tag `{tag.name}`")

    @delete_group.command(name="here", description="delete a local tag")
    async def delete_here(self, interaction: Interaction,
                          tag: LocalTag_Transform):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        await self.database.deleteTag(guild_id=interaction.guild_id, name=tag.name)
        await respond(interaction, f"Deleted the local tag `{tag.name}`")

    @edit_group.command(name="global", description="edit a global tag")
    async def edit_global(self, interaction: Interaction, tag: GlobalTag_Transform, new: GlobalTag_Transform=None,
                          content: str=None, embed: str=None):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        if new: raise TagDB.TagAlreadyExists
        new = tag
        new_name = interaction.namespace.new
        if new_name: new.name = new_name
        if content: new.content = content if content != "" else None
        if embed: new.embed = embed if embed != "" else None

        await self.database.editTag(old_name=tag.name, tag=new)
        response = f"Edited the global tag `{tag.name}`"
        if new_name: response += f", New Name: {new.name}"
        await respond(interaction, response)

    @edit_group.command(name="here", description="edit a local tag")
    async def edit_local(self, interaction: Interaction, tag: LocalTag_Transform, new: LocalTag_Transform = None,
                         content: str = None, embed: str = None):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        if new: raise TagDB.TagAlreadyExists
        new = tag
        new_name = interaction.namespace.new
        if new_name: new.name = new_name
        if content: new.content = content if content != "" else None
        if embed: new.embed = embed if embed != "" else None

        await self.database.editTag(old_name=tag.name, tag=new)
        response = f"Edited the local tag `{tag.name}`"
        if new_name: response += f", New Name: {new.name}"
        await respond(interaction, response)

    """
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
    """

    # Create Modal Handlers
    async def ctx_menu_create_local_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='local')

    async def ctx_menu_create_global_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='global')

    async def send_create_modal(self, interaction: discord.Interaction, message: discord.Message,
                                tag_type: Literal["local", "global"]):
        await interaction.response.send_modal(TagCreationModal(cog=self, tag_type=tag_type, message=message))
    """
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
    """

    """
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
        """


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
        # await respond(interaction, thinking=False)
        # attachments = self.tag_attachments.value.split('\n') if self.tag_attachments.value else []
        # await interaction.response.defer(thinking=False)
        # await respond(interaction, force_defer=True, thinking=False)
        bot: Kagami = interaction.client
        db = TagDB(bot.config.db_path)
        if self.tag_type == "global":
            tag = await db.fetchTag(guild_id=0,
                                    tag_name=self.tag_name.value)
            if tag: raise TagDB.TagAlreadyExists
            tag = TagDB.Tag(guild_id=0,
                            name=self.tag_name,
                            content=self.tag_content.value + "\n" + self.tag_attachments.value,
                            embed=None,
                            author_id=interaction.user.id)
            await db.insertTag(tag)
            await respond(interaction, f"Created the global tag `{tag.name}`", send_followup=True)
        elif self.tag_type == "local":
            tag = await db.fetchTag(guild_id=interaction.guild_id,
                                    tag_name=self.tag_name.value)
            if tag: raise TagDB.TagAlreadyExists

            tag = TagDB.Tag(guild_id=interaction.guild_id,
                            name=self.tag_name,
                            content=self.tag_content.value + "\n" + self.tag_attachments.value,
                            embed=None,
                            author_id=interaction.user.id)
            await db.insertTag(tag)
            await respond(interaction, f"Created the local tag `{tag.name}`", send_followup=True)
        #
        # await self.cog.set_handler(interaction=interaction, tag_name=self.tag_name.value,
        #                            content=self.tag_content.value, mode=self.tag_type, attachment_links=attachments)


async def setup(bot):
    await bot.add_cog(Tags(bot))
