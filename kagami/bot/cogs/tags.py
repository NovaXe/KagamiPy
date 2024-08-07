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
        class Queries:
            CREATE_TABLE = """
            CREATE TABLE IF NOT EXISTS TagSettings(
            guild_id INTEGER NOT NULL,
            tags_enabled INTEGER DEFAULT 1,
            PRIMARY KEY (guild_id),
            FOREIGN KEY (guild_id) REFERENCES Guild(id)
            ON UPDATE CASCADE ON DELETE CASCADE)
            """
            DROP_TABLE = """
            DROP TABLE IF EXISTS TagSettings
            """
            TRIGGER_BEFORE_INSERT_GUILD = """
            CREATE TRIGGER IF NOT EXISTS TagSettings_insert_guild_before_insert
            BEFORE INSERT ON TagSettings
            BEGIN
                INSERT OR IGNORE INTO Guild(id)
                values(NEW.guild_id);
            END
            """
            UPSERT = """
            INSERT INTO MusicSettings (guild_id, tags_enabled)
            VALUES(:guild_id, :tags_enabled)
            ON CONFLICT (guild_id)
            DO UPDATE SET tags_enabled = :tags_enabled
            """
            SELECT = """
            SELECT * FROM TagSettings
            WHERE guild_id = ?
            """
            DELETE = """
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
        class Queries:
            CREATE_TABLE = """
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
            DROP_TABLE = """
            DROP TABLE IF EXISTS Tag
            """
            QUERY_AFTER_INSERT_TRIGGER = """
            CREATE TRIGGER IF NOT EXISTS set_creation_date_after_insert
            AFTER INSERT ON Tag
            """
            # QUERY_BEFORE_INSERT_INSERT_GUILD_TRIGGER = """
            # CREATE TRIGGER IF NOT EXISTS insert_guild_before_insert
            # """
            TRIGGER_BEFORE_INSERT_SETTINGS = """
            CREATE TRIGGER IF NOT EXISTS Tag_insert_settings_before_insert
            BEFORE INSERT ON Tag
            BEGIN
                INSERT INTO TagSettings(guild_id)
                VALUES(NEW.guild_id)
                ON CONFLICT DO NOTHING;
            END
            """
            TRIGGER_BEFORE_INSERT_USER = """
            CREATE TRIGGER IF NOT EXISTS Tag_insert_user_before_insert
            BEFORE INSERT ON Tag
            BEGIN
                INSERT INTO User(id)
                VALUES(NEW.author_id)
                ON CONFLICT DO NOTHING;
            END
            """
            TRIGGER_DATE_AFTER_UPDATE = """
            CREATE TRIGGER IF NOT EXISTS Tag_set_modified_data_after_update
            AFTER UPDATE ON Tag
            BEGIN
                UPDATE Tag
                SET modified_date = NULL 
                WHERE (guild_id = NEW.guild_id) AND (name = NEW.name);
            END
            """
            INSERT = """
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
            UPSERT = """
            INSERT INTO Tag (guild_id, name, content, embed, author_id, creation_date)
            VALUES (:guild_id, :name, :content, :embed, :author_id, :creation_date)
            ON CONFLICT (guild_id, name)
            DO UPDATE SET content = :content, embed = :embed
            """
            UPDATE = """
            UPDATE Tag SET content = :content, embed = :embed
            WHERE guild_id = :guild_id AND name = :name
            """
            EDIT = """
            UPDATE OR REPLACE Tag SET name=:name, content = :content, embed = :embed
            WHERE guild_id = :guild_id AND name = :old_name
            """
            SELECT = """
            SELECT * FROM Tag 
            WHERE guild_id = ? AND name = ?;
            """
            DELETE = """
            DELETE FROM Tag
            WHERE guild_id = ? AND name = ?
            RETURNING *
            """
            DELETE_FROM_USER = """
            DELETE FROM Tag
            WHERE author_id = ?
            RETURNING *
            """
            SELECT_LIKE = """
            SELECT * FROM Tag
            WHERE guild_id = ? AND name LIKE ?
            LIMIT ? OFFSET ?
            """
            SELECT_LIKE_NAMES = """
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

    async def insertTag(self, tag: Tag) -> bool:
        async with aiosqlite.connect(self.file_path) as db:
            cursor = await db.execute(TagDB.Tag.Queries.INSERT, tag.asdict())
            row_count = cursor.rowcount
            await db.commit()
        return row_count > 0

    async def insertTags(self, tags: list[Tag]):
        async with aiosqlite.connect(self.file_path) as db:
            data = [tag.asdict() for tag in tags]
            await db.executemany(TagDB.Tag.Queries.INSERT, data)
            await db.commit()

    async def updateTag(self, tag: Tag):
        async with aiosqlite.connect(self.file_path) as db:
            await db.execute(TagDB.Tag.Queries.UPDATE, tag.asdict())
            await db.commit()

    async def editTag(self, old_name: str, tag: Tag):
        async with aiosqlite.connect(self.file_path) as db:
            data = tag.asdict()
            data["old_name"] = old_name
            await db.execute(TagDB.Tag.Queries.EDIT, data)
            await db.commit()

    async def deleteTag(self, guild_id: int, name: str) -> Tag:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = TagDB.Tag.rowFactory
            result = await db.execute_fetchall(TagDB.Tag.Queries.DELETE, (guild_id, name))
            await db.commit()
        return result[0] if result else None

    async def fetchTag(self, guild_id: int, tag_name: str) -> Tag:
        async with aiosqlite.connect(self.file_path) as db:
            db.row_factory = TagDB.Tag.rowFactory
            result: list[TagDB.Tag] = await db.execute_fetchall(TagDB.Tag.Queries.SELECT, (guild_id, tag_name))
        return result[0] if result else None

    async def fetchSimilarTagNames(self, guild_id: int, tag_name: str, limit: int=1, offset=0) -> list[str]:
        async with aiosqlite.connect(self.file_path) as db:
            names: list[str] = await db.execute_fetchall(TagDB.Tag.Queries.SELECT_LIKE_NAMES,
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
        if self.bot.config.migrate_data: await self.migrateTagData()

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

    @app_commands.rename(new="name")
    @edit_group.command(name="global", description="edit a global tag")
    async def edit_global(self, interaction: Interaction, tag: GlobalTag_Transform, new: GlobalTag_Transform=None,
                          content: str=None, embed: str=None):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        if new: raise TagDB.TagAlreadyExists
        new = TagDB.Tag(guild_id=0,
                        name=interaction.namespace.name or tag.name,
                        author_id=interaction.user.id,
                        content=content if content != "" else None,
                        embed=embed if embed != "" else None)
        await self.database.editTag(old_name=tag.name, tag=new)
        response = f"Edited the global tag `{tag.name}`"
        if interaction.namespace.name: response += f", New Name: {new.name}"
        await respond(interaction, response)

    @app_commands.rename(new="name")
    @edit_group.command(name="here", description="edit a local tag")
    async def edit_local(self, interaction: Interaction, tag: LocalTag_Transform, new: LocalTag_Transform = None,
                         content: str = None, embed: str = None):
        await respond(interaction)
        if not tag: raise TagDB.TagNotFound
        if new: raise TagDB.TagAlreadyExists
        new = TagDB.Tag(guild_id=interaction.guild_id,
                        name=interaction.namespace.name or tag.name,
                        author_id=interaction.user.id,
                        content=content if content != "" else None,
                        embed=embed if embed != "" else None)
        await self.database.editTag(old_name=tag.name, tag=new)
        response = f"Edited the local tag `{tag.name}`"
        if interaction.namespace.name: response += f", New Name: {new.name}"
        await respond(interaction, response)

    async def ctx_menu_create_local_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='local')

    async def ctx_menu_create_global_handler(self, interaction: discord.Interaction, message: discord.Message):
        await self.send_create_modal(interaction, message, tag_type='global')

    async def send_create_modal(self, interaction: discord.Interaction, message: discord.Message,
                                tag_type: Literal["local", "global"]):
        await interaction.response.send_modal(TagCreationModal(cog=self, tag_type=tag_type, message=message))


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
                            name=self.tag_name.value,
                            content=self.tag_content.value + "\n" + self.tag_attachments.value,
                            embed=None,
                            author_id=interaction.user.id)
            await db.insertTag(tag)
            await respond(interaction, f"Created the global tag `{tag.name}`")
        elif self.tag_type == "local":
            tag = await db.fetchTag(guild_id=interaction.guild_id,
                                    tag_name=self.tag_name.value)
            if tag: raise TagDB.TagAlreadyExists

            tag = TagDB.Tag(guild_id=interaction.guild_id,
                            name=self.tag_name.value,
                            content=self.tag_content.value + "\n" + self.tag_attachments.value,
                            embed=None,
                            author_id=interaction.user.id)
            await db.insertTag(tag)
            await respond(interaction, f"Created the local tag `{tag.name}`")
        #
        # await self.cog.set_handler(interaction=interaction, tag_name=self.tag_name.value,
        #                            content=self.tag_content.value, mode=self.tag_type, attachment_links=attachments)


async def setup(bot):
    await bot.add_cog(Tags(bot))
