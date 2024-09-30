import asyncio
import json
from dataclasses import dataclass
import aiosqlite

import discord
from discord import app_commands, Interaction
from discord._types import ClientT
from discord.ext import commands
from discord.app_commands import Transformer, Group, Transform, Choice
from discord.ext.commands import GroupCog

from common import errors
from utils.depr_db_interface import Database
from common.interactions import respond
from typing import Literal, Union, List, Any
from bot import Kagami
from utils.pages import CustomRepr
from common.database import Table, DatabaseManager, exec_query
from common.tables import Guild, GuildSettings, User


@dataclass
class TagSettings(Table, schema_version=1, trigger_version=1, table_group="tags"):
    guild_id: int
    enforce_ownership = True

    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {TagSettings}(
            guild_id INTEGER NOT NULL,
            enforce_ownership INTEGER DEFAULT 1,
            PRIMARY KEY (guild_id),
            FOREIGN KEY (guild_id) REFERENCES {Guild}(id)
            ON UPDATE CASCADE ON DELETE CASCADE
        )
        """
        await exec_query(db, query)

    @classmethod
    async def insert_from_temp(cls, db: aiosqlite.Connection):
        # query = f"""
        #     INSERT INTO {TagSettings}(guild_id, enforce_ownership)
        #     SELECT guild_id 
        #     FROM temp_{TagSettings} 
        # """
        # await exec_query(db, query)
        await super().insert_from_temp(db)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        trigger = f"""
        CREATE TRIGGER IF NOT EXISTS {TagSettings}_insert_guild_before_insert
        BEFORE INSERT ON {TagSettings}
        BEGIN
            INSERT OR IGNORE INTO {Guild}(id)
            VALUES (NEW.guild_id);
        END
        """
        await exec_query(db, trigger)

    async def upsert(self, db: aiosqlite.Connection) -> "TagSettings":
        query = f"""
        INSERT INTO {TagSettings} (guild_id, enforce_ownership)
        VALUES (:guild_id, :enforce_ownership)
        ON CONFLICT (guild_id)
        DO UPDATE SET enforce_ownership = :enforce_ownership
        RETURNING *
        """
        db.row_factory = TagSettings.row_factory
        async with exec_query(db, query, self.asdict()) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int) -> "TagSettings":
        query = f"""
        SELECT * FROM {TagSettings}
        WHERE guild_id = ?
        """
        db.row_factory = TagSettings.row_factory
        async with exec_query(db, query, (guild_id,)) as cur:
            result = await cur.fetchone()
        return result

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int) -> "TagSettings":
        query = f"""
        DELETE FROM {TagSettings}
        WHERE guild_id = ?
        """
        db.row_factory = TagSettings.row_factory
        async with exec_query(db, query, (guild_id,)) as cur:
            result = await cur.fetchone()
        return result

    async def delete(self, db: aiosqlite.Connection) -> "TagSettings":
        return await TagSettings.deleteWhere(db, guild_id=self.guild_id)

@dataclass
class Tag(Table, schema_version=1, trigger_version=1, table_group="tags", schema_altered=True):
    guild_id: int
    name: str
    content: str
    embed: str  # json objects separated by commas
    author_id: int
    creation_date: str = None
    modified_date: str = None

    def is_author(self, user: discord.Member):
        return self.author_id == user.id


    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {Tag}(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            content TEXT,
            embed TEXT,
            author_id INTEGER NOT NULL,
            creation_date TEXT NOT NULL ON CONFLICT REPLACE DEFAULT CURRENT_DATE,
            modified_date TEXT NOT NULL ON CONFLICT REPLACE DEFAULT CURRENT_DATE,
            PRIMARY KEY(guild_id, name),
            FOREIGN KEY(guild_id) REFERENCES {Guild}(id)
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY(author_id) REFERENCES {User}(id) 
                ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
        )
        """
        await exec_query(db, query)

    @classmethod
    async def alter_table(cls, db: aiosqlite.Connection):
        query = f"""
        ALTER TABLE {Tag}
        RENAME COLUMN embeds to embed
        """
        await exec_query(db, query)

    @classmethod
    async def create_triggers(cls, db: aiosqlite.Connection):
        triggers = [
            f"""
            CREATE TRIGGER IF NOT EXISTS {Tag}_insert_settings_before_insert
            BEFORE INSERT ON {Tag}
            BEGIN
                INSERT INTO {TagSettings}(guild_id)
                VALUES(NEW.guild_id)
                ON CONFLICT DO NOTHING;
            END
            """,
            f"""
            CREATE TRIGGER IF NOT EXISTS {Tag}_insert_user_before_insert
            BEFORE INSERT ON {Tag}
            BEGIN
                INSERT INTO {User}(id)
                VALUES(NEW.author_id)
                ON CONFLICT DO NOTHING;
            END
            """,
            f"""
            CREATE TRIGGER IF NOT EXISTS {Tag}_set_modified_date_after_update
            AFTER UPDATE ON {Tag}
            BEGIN
                UPDATE {Tag}
                SET modified_date = CURRENT_DATE
                WHERE (guild_id = NEW.guild_id) AND (name = NEW.name);
            END
            """
        ]
        for t in triggers:
            await exec_query(db, t)

    async def insert(self, db: aiosqlite.Connection):
        query = f"""
        INSERT INTO {Tag} (guild_id, name, content, embed, author_id, creation_date, modified_date)
        VALUES (:guild_id, :name, :content, :embed, :author_id, :creation_date, :creation_date)
            ON CONFLICT DO NOTHING
        """
        await exec_query(db, query, self.asdict())

    async def upsert(self, db: aiosqlite.Connection) -> "Tag":
        query = f"""
        INSERT INTO {Tag}(guild_id, name, content, embed, author_id, creation_date)
        VALUES (:guild_id, :name, :content, :embed, :author_id)
            ON CONFLICT (guild_id, name)
            DO UPDATE SET content = :content, embed = :embed
        RETURNING *
        """
        db.row_factory = Tag.row_factory
        async with exec_query(db, query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    async def update(self, db: aiosqlite.Connection) -> "Tag":
        query = f"""
        UPDATE {Tag} SET content = :content, embed = :embed
        WHERE guild_id = :guild_id AND name = :name
        RETURNING *
        """
        db.row_factory = Tag.row_factory
        async with exec_query(db, query, self.asdict()) as cur:
            res = await cur.fetchon()
        return res

    async def edit(self, db: aiosqlite.Connection, new_tag: "Tag"):
        query = f"""
        UPDATE OR REPLACE {Tag} 
        SET name=:name, content = :content, embed = :embed
        WHERE guild_id = :guild_id AND name = :old_name
        RETURNING *
        """
        params = new_tag.asdict()
        params["old_name"] = self.name
        db.row_factory = Tag.row_factory
        async with exec_query(db, query, params) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str, author_id: int=None) -> "Tag":
        if author_id is None:
            query = f"""
            SELECT * FROM {Tag}
            WHERE guild_id = ? AND name = ?
            """
            params = (guild_id, name)
        else:
            query = f"""
            SELECT * FROM {Tag}
            WHERE guild_id = ? AND name = ? AND author_id = ?
            """
            params = (guild_id, name, author_id)

        db.row_factory = Tag.row_factory
        async with exec_query(db, query, params) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def selectAllWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str, author_id: int=None,
                             limit: int=25, offset: int=0) -> list["Tag"]:
        if author_id is None:
            query = f"""
            SELECT * FROM {Tag}
            WHERE guild_id = ? AND name = ?
            limit ? offset ?
            """
            params = (guild_id, name, limit, offset)
        else:
            query = f"""
            SELECT * FROM {Tag}
            WHERE guild_id = ? AND name = ? AND author_id = ?
            limit ? offset ?
            """
            params = (guild_id, name, author_id, limit, offset)
        db.row_factory = Tag.row_factory
        async with exec_query(db, query, params) as cur:
            res = await cur.fetchall()
        return res


    @classmethod
    async def selectLikeGroupIds(cls, db: aiosqlite.Connection, group_id: int, limit: 1) -> list[int]:
        query = f"""
        SELECT guild_id FROM {Tag}
        WHERE CAST (guild_id as TEXT) LIKE ?
        LIMIT ?
        """
        db.row_factory = aiosqlite.Row
        async with exec_query(db, query, (f"%{group_id}%",)) as cur:
            res = await cur.fetchall()
        return [r["guild_id"] for r in res]

    @classmethod
    async def selectGroupExists(cls, db: aiosqlite.Connection, group_id: int) -> bool:
        query = f"""
        SELECT 1 FROM {Tag}
        WHERE guild_id = ?
        """
        db.row_factory = None
        async with exec_query(db, query, (group_id, )) as cur:
            res = await cur.fetchone()
        return bool(res[0])

    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "Tag":
        query = f"""
        DELETE FROM {Tag}
        WHERE guild_id = ? AND name = ?
        RETURNING *
        """
        db.row_factory = Tag.row_factory
        async with exec_query(db, query, (guild_id, name)) as cur:
            res = await cur.fetchone()
        return res

    async def delete(self, db: aiosqlite.Connection) -> "Tag":
        await Tag.deleteWhere(db, self.guild_id, self.name)

    @classmethod
    async def deleteFromUser(cls, db: aiosqlite.Connection, guild_id: int, author_id: int) -> list["Tag"]:
        query = f"""
        DELETE FROM {Tag}
        WHERE guild_id = ? AND author_id = ? 
        RETURNING *
        """
        db.row_factory = Tag.row_factory
        async with exec_query(db, query, (guild_id, author_id,)) as cur:
            res = await cur.fetchall()
        return res

    @classmethod
    async def selectLikeNames(cls, db: aiosqlite.Connection, guild_id: int, name: str, limit: int=1, offset: int=0) -> list[str]:
        query = f"""
        SELECT name FROM Tag
            WHERE (guild_id = ?) AND (name LIKE ?)
            LIMIT ? OFFSET ?
        """
        db.row_factory = Tag.row_factory
        async with exec_query(db, query, (guild_id, f"%{name}%", limit, offset)) as cur:
            res = await cur.fetchall()
        return [n.name for n in res]


class TagsDisabled(errors.CustomCheck):
    MESSAGE = "The tag feature is disabled"

class TagAlreadyExists(errors.CustomCheck):
    MESSAGE = "There is already a tag with that name"

class TagNotFound(errors.CustomCheck):
    MESSAGE = "There is no tag with that name"

class TagOwnerFail(errors.CustomCheck):
    MESSAGE = "You are not the owner of that tag"


class TagGroupTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           value: Union[int, str]) -> list[Choice[str]]:
        bot: Kagami = interaction.client
        groups = {"local": interaction.guild_id,
                  "global": 0}

        choices = []
        if isinstance(value, str):
            choices = [Choice(name=g, value=str(groups[g])) for g in groups.keys() if value.lower() in g.lower()]
            pass
        elif isinstance(value, int):
            async with bot.dbman.conn() as db:
                ids = await Tag.selectLikeGroupIds(db, value, limit=25)
            choices = [Choice(name=str(i), value=str(i)) for i in ids]
        return choices

    async def transform(self, interaction: Interaction, value: str) -> int:
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            exists = await Tag.selectGroupExists(db, int(value))
        return int(value) if exists else None

class LocalTagTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           value: Union[int, float, str], /) -> List[Choice[str]]:
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            names = await Tag.selectLikeNames(db,
                                              guild_id=interaction.guild_id,
                                              name=value,
                                              limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction, value: Any, /) -> Tag:
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            tag = await Tag.selectWhere(db,
                                        guild_id=interaction.guild_id,
                                        name=value)
        return tag


class GlobalTagTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           value: Union[int, float, str], /) -> List[Choice[str]]:
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            names = await Tag.selectLikeNames(db, guild_id=0, name=value, limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction,
                        value: Any, /) -> Tag:
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            tag = await Tag.selectWhere(db, guild_id=0, name=value)
        return tag


class GuildTagTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction,
                           value: Union[int, float, str], /) -> List[Choice[Union[int, float, str]]]:
        guild_id = int(interaction.namespace.guild)
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            names = await Tag.selectLikeNames(db, guild_id=guild_id, name=value, limit=25)
        return [Choice(name=name, value=name) for name in names]

    async def transform(self, interaction: Interaction,
                        value: str, /) -> Tag:
        guild_id = int(interaction.namespace.guild)
        bot: Kagami = interaction.client
        async with bot.dbman.conn() as db:
            tag = await Tag.selectWhere(db, guild_id=guild_id, name=value)
        return tag


class GuildTransformer(Transformer):
    # this exact transformer is also defined in sentinels
    # consider moving to a separate file with other shared non cog specific transformers
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


def is_tag_manager(user: discord.Member):
    return user.guild_permissions.manage_messages



def check_json(json_str: str):
    try:
        json.loads(json_str)
        return True, ""
    except json.JSONDecodeError as e:
        return False, e

def validate_json(json_str: str):
    try: json.loads(json_str)
    except json.JSONDecodeError as e:
        raise errors.CustomCheck(e)

def decode_json(json_str: str):
    return json.loads(json_str)

def json_to_discord_embed(json_str: str):
    embed = discord.Embed.from_dict(json.loads(json_str))
    # embeds = [discord.Embed.from_dict(e) for e in json.loads(json_str)]
    return embed


class Tags(GroupCog, group_name="t"):
    def __init__(self, bot):
        self.bot: Kagami = bot
        self.config = bot.config
        self.ctx_menus = [
            app_commands.ContextMenu(
                name="Create Tag",
                callback=self.ctx_menu_create_tag_handler
            )
        ]
        for ctx_menu in self.ctx_menus:
            self.bot.tree.add_command(ctx_menu)

    def conn(self):
        return self.bot.dbman.conn()

    @commands.is_owner()
    @commands.group(name="tags")
    async def tags(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await asyncio.gather(
                ctx.message.delete(delay=5),
                ctx.send("Please specify a valid tag command", delete_after=5)
            )

    @commands.is_owner()
    @tags.command(name="migrate")
    async def migrateCommand(self, ctx):
        await ctx.send("There is nothing to migrate")
        # await self.migrateData()
        # await ctx.send("migrated tags probably")

    async def cog_unload(self) -> None:
        for ctx_menu in self.ctx_menus:
            self.bot.tree.remove_command(ctx_menu.name, type=ctx_menu.type)

    async def cog_load(self) -> None:
        await self.bot.dbman.setup(table_group="tags",
                                   drop_tables=self.bot.config.drop_tables,
                                   drop_triggers=self.bot.config.drop_triggers,
                                   ignore_schema_updates=self.bot.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.bot.config.ignore_trigger_updates)
        # await self.database.init(drop=self.bot.config.drop_tables)
        # if self.bot.config.migrate_data: await self.migrateData()

    async def interaction_check(self, interaction: discord.Interaction[ClientT], /) -> bool:
        # await self.bot.database.upsertGuild(interaction.guild)
        return True

    get_group = Group(name="get", description="gets a tag")
    set_group = Group(name="set", description="sets a tag")
    delete_group = Group(name="delete", description="deletes a tag")
    edit_group = Group(name="edit", description="edits a tag")
    # list_group = app_commands.Group(name="list", description="lists the tags")
    # search_group = app_commands.Group(name="search", description="searches for tags")

    LocalTag_Transform = Transform[Tag, LocalTagTransformer]
    LocalTag_Transform_Author = Transform[Tag, LocalTagTransformer]
    GlobalTag_Transform = Transform[Tag, GlobalTagTransformer]
    GuildTag_Transform = Transform[Tag, GuildTagTransformer]
    Guild_Transform = Transform[discord.Guild, GuildTransformer]

    @set_group.command(name="global", description="add a new global tag")
    async def set_global(self, interaction: Interaction, tag: GlobalTag_Transform,
                         content: str=None, embed: str=None):
        await respond(interaction, ephemeral=True)
        if tag:
            raise TagAlreadyExists

        if embed:
            validate_json(embed)

        tag = Tag(guild_id=0,
                  name=interaction.namespace.tag,
                  content=content,
                  embed=embed,
                  author_id=interaction.user.id)
        async with self.conn() as db:
            await tag.insert(db)
            await db.commit()
        await respond(interaction, f"Created the global tag `{tag.name}`")

    @set_group.command(name="here", description="add a new local tag")
    async def set_here(self, interaction: Interaction, tag: LocalTag_Transform,
                       content: str=None, embed: str=None):
        await respond(interaction, ephemeral=True)
        if tag:
            raise TagAlreadyExists
        if embed:
            validate_json(embed)
        tag = Tag(guild_id=interaction.guild_id,
                  name=interaction.namespace.tag,
                  content=content,
                  embed=embed,
                  author_id=interaction.user.id)
        async with self.conn() as db:
            await tag.insert(db)
            await db.commit()
        await respond(interaction, f"Created the local tag `{tag.name}`")

    # @set_group.command(name="elsewhere", description="add a new tag to another server")
    async def set_elsewhere(self, interaction: Interaction,
                            guild: Guild_Transform, tag: GuildTag_Transform,
                            content: str=None, embed: str=None):
        await respond(interaction, ephemeral=True)
        if tag:
            raise TagAlreadyExists
        if embed:
            validate_json(embed)
        guild_name = guild.name
        tag = Tag(guild_id=guild.id,
                  name=interaction.namespace.tag,
                  content=content,
                  embed=embed,
                  author_id=interaction.user.id)
        async with self.conn() as db:
            await tag.insert(db)
            await db.commit()
        await respond(interaction, f"Created tag `{tag.name}` for guild `{guild_name}`")


    @get_group.command(name="global", description="fetch a global tag")
    async def get_global(self, interaction: Interaction,
                         tag: GlobalTag_Transform):
        await respond(interaction)
        if not tag:
            raise TagNotFound

        embed = None
        if tag.embed:
            validate_json(tag.embed)
            embed = json_to_discord_embed(tag.embed)
            # embeds = [discord.Embed.from_dict(json.loads(embed_str))
            #           for embed_str in tag.embeds.split(",")]
        # content = tag.content if tag.content and tag.content != '' else "`The tag has no content`"
        content = tag.content
        if not tag.content and not embed:
            content = "This tag is blank"
        elif not tag.content:
            content = ''
        await respond(interaction, content=content, embed=embed)

    @get_group.command(name="here", description="fetch a local tag")
    async def get_here(self, interaction: Interaction,
                       tag: LocalTag_Transform):
        await respond(interaction)
        if not tag:
            raise TagNotFound

        embed = None
        if tag.embed:
            embed = json_to_discord_embed(tag.embed)

        content = tag.content
        if not tag.content and not embed:
            content = "This tag is blank"
        elif not tag.content:
            content = ''
        await respond(interaction, content=content, embed=embed)

    @get_group.command(name="elsewhere", description="fetch a tag from another server")
    async def get_elsewhere(self, interaction: Interaction,
                            guild: Guild_Transform, tag: GuildTag_Transform):
        await respond(interaction)
        if not tag:
            raise TagNotFound

        embed = None
        if tag.embed:
            embed = json_to_discord_embed(tag.embed)

        content = tag.content
        if not tag.content and not embed:
            content = "This tag is blank"
        elif not tag.content:
            content = ''
        await respond(interaction, content=content, embed=embed)

    @delete_group.command(name="global", description="delete a global tag")
    async def delete_global(self, interaction: Interaction,
                            tag: GlobalTag_Transform):
        await respond(interaction, ephemeral=True)
        if not tag:
            raise TagNotFound
        elif not (tag.is_author(interaction.user) or self.bot.is_owner(interaction.user)):
            raise TagOwnerFail

        async with self.conn() as db:
            await tag.delete(db)
            await db.commit()
        await respond(interaction, f"Deleted the global tag `{tag.name}`")

    @delete_group.command(name="here", description="delete a local tag")
    async def delete_here(self, interaction: Interaction,
                          tag: LocalTag_Transform):
        await respond(interaction, ephemeral=True)
        if not tag:
            raise TagNotFound
        elif not (tag.is_author(interaction.user)
                  or is_tag_manager(interaction.user)
                  or self.bot.is_owner(interaction.user)):
            raise TagOwnerFail

        async with self.conn() as db:
            await tag.delete(db)
            await db.commit()
        await respond(interaction, f"Deleted the local tag `{tag.name}`")

    @app_commands.rename(new="name")
    @edit_group.command(name="global", description="edit a global tag")
    async def edit_global(self, interaction: Interaction, tag: GlobalTag_Transform, new: GlobalTag_Transform=None,
                          content: str=None, embed: str=None):
        await respond(interaction, ephemeral=True)
        if not tag:
            raise TagNotFound
        elif not (tag.is_author(interaction.user)
                  or self.bot.is_owner(interaction.user)):
            raise TagOwnerFail
        elif new:
            raise TagAlreadyExists
        if embed:
            validate_json(embed)

        new = Tag(guild_id=0,
                  name=interaction.namespace.name or tag.name,
                  author_id=interaction.user.id,
                  content=content if content != "" else None,
                  embed=embed if embed != "" else None)
        async with self.conn() as db:
            await tag.edit(db, new_tag=new)
            await db.commit()
        response = f"Edited the global tag `{tag.name}`"
        if interaction.namespace.name: response += f", New Name: {new.name}"
        await respond(interaction, response)

    @app_commands.rename(new="name")
    @edit_group.command(name="here", description="edit a local tag")
    async def edit_local(self, interaction: Interaction, tag: LocalTag_Transform, new: LocalTag_Transform = None,
                         content: str = None, embed: str = None):
        await respond(interaction, ephemeral=True)
        if not tag:
            raise TagNotFound
        elif not (tag.is_author(interaction.user)
                  or is_tag_manager(interaction.user)
                  or self.bot.is_owner(interaction.user)):
            raise TagOwnerFail
        if new:
            raise TagAlreadyExists
        if embed:
            validate_json(embed)
        new = Tag(guild_id=interaction.guild_id,
                  name=interaction.namespace.name or tag.name,
                  author_id=interaction.user.id,
                  content=content if content != "" else None,
                  embed=embed if embed != "" else None)
        async with self.conn() as db:
            await tag.edit(db, new_tag=new)
            await db.commit()
        response = f"Edited the local tag `{tag.name}`"
        if interaction.namespace.name: response += f", New Name: {new.name}"
        await respond(interaction, response)

    async def ctx_menu_create_tag_handler(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(TagModal(message=message))


    view = Group(name="view", description="commands that display useful information")

    def get_callback(self, dbman, group_id):
        from common.paginator import ScrollerState, Scroller

        async def callback(interaction_c: Interaction, state: ScrollerState):
            async with self.conn() as db:
                results = await Tag.selectAllWhere(db, group_id, interaction_c.user.id,
                                                   limit=25, offset=state.home_offset + state.relative_offset)
        return callback


    @view.command(name="all")
    @app_commands.rename(group_id="group")
    async def view_all(self, interaction: Interaction, group_id: Transform[int, TagGroupTransformer]):
        message = await respond(interaction)
        if group_id is None:
            raise errors.CustomCheck("That group doesn't exist")

        from common.paginator import ScrollerState, Scroller

        callback = self.get_callback(self.bot.dbman, group_id)
        scroller = Scroller(message, interaction.user, page_callback=callback, home_offset=0)
        await respond(interaction, view=scroller)












class TagModal(discord.ui.Modal, title="Set Tag"):
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

        default_embed_text = ""
        for embed in message.embeds:
            if embed.type == "rich":
                default_embed_text = json.dumps(embed.to_dict(), indent=2)
                break
        self.embed.default = default_embed_text
        # self.embeds.default = ",\n".join([json.dumps(embed.to_dict(), indent=2) for embed in message.embeds])
        self.content.default = message.content
        self.location.default = "local"

    location = discord.ui.TextInput(label="Tag Location", placeholder="global/local")
    name = discord.ui.TextInput(label="Tag Name", placeholder="Enter the name of the tag")
    content = discord.ui.TextInput(label="Tag Content", placeholder="Enter the content for the tag",
                                   style=discord.TextStyle.paragraph, required=False)
    embed = discord.ui.TextInput(label="Tag Embed", placeholder="Embed as a json object\n",
                                 style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: Interaction[Kagami], /) -> None:
        bot: Kagami = interaction.client
        if len(self.embed.value.strip()) > 0:
            validate_json(self.embed.value)
            # for embed_str in self.embeds.value.split(","):
            #     try:
            #         json.loads(embed_str)
            #     except json.JSONDecodeError as e:
            #         response = "**Embed Error:**\n"
            #         response += e.msg
            #         await respond(interaction, ephemeral=True, content=response)
            #         return

        if self.location.value == "local":
            guild_id = interaction.guild_id
        elif self.location.value == "global":
            guild_id = 0
        elif self.location.value.isnumeric():
            value = int(self.location.value)
            if value < 0 and bot.owner_id == interaction.user.id:
                guild_id = int(self.location.value)
            else:
                guild_id = interaction.guild_id
        else:
            await respond(interaction, f"`{self.location.value}` is not a valid location", ephemeral=True)
            return

        tag = Tag(guild_id=guild_id, name=self.name.value, author_id=interaction.user.id,
                  content=self.content.value, embed=self.embed.value)

        async with bot.dbman.conn() as db:
            existing = await Tag.selectWhere(db, guild_id=tag.guild_id, name=tag.name)
            if existing is not None:
                raise TagAlreadyExists
            await tag.insert(db)
            await db.commit()
        await respond(interaction, f"Created `{self.location.value}` tag: {tag.name} ", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tags(bot))
