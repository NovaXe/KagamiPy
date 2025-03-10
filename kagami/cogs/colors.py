from dataclasses import dataclass
from enum import IntEnum
from typing import (
    Literal, List, Callable, Any
)
import PIL as pillow
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import aiosqlite
import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from discord.ext.commands import GroupCog
from discord.app_commands import Transform, Transformer, Group, Choice, Range

from bot import Kagami
from common import errors
from common.logging import setup_logging
from common.interactions import respond
from common.database import Table, DatabaseManager, ConnectionContext
from common.tables import Guild, GuildSettings, PersistentSettings
from common.paginator import Scroller, ScrollerState
from common.utils import acstr


@dataclass
class ColorGroup(Table, schema_version=1, trigger_version=1):
    guild_id: int
    name: str
    prefix: str
    permitted_role_id: int
    
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {ColorGroup}(
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            prefix TEXT,
            permitted_role_id INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, name),
            FOREIGN KEY (guild_id) REFERENCES {Guild}(id)
        )
        """
        await db.execute(query)
        
    @classmethod
    async def selectPrefixMatch(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> str:
        query = f"""
        SELECT prefix FROM {ColorGroup}
        WHERE guild_id = ?
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (guild_id,)) as cur:
            res = await cur.fetchone()
        return res["prefix"] if res else None 
    
    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "ColorGroup":
        query = f"""
        SELECT * FROM {ColorGroup}
        WHERE guild_id = ? AND name = ?
        """
        db.row_factory = ColorGroup.row_factory
        async with db.execute(query, (guild_id, name)) as cur:
            res = await cur.fetchone()
        return res
    
    @classmethod
    async def selectPrefixMatch(cls, db: aiosqlite.Connection, guild_id: int, role_name):
        query = f"""
        SELECT * FROM {ColorGroup}
        WHERE guild_id = ? AND ? LIKE prefix || '%'
        """
        db.row_factory = ColorGroup.row_factory
        async with db.execute(query, (guild_id, role_name)) as cur:
            res = await cur.fetchone()
        return res
    
    @classmethod
    async def selectNamesWhere(cls, db: aiosqlite.Connection, guild_id: int, role_ids: list[int], limit: int=25, offset: int=0) -> list[str]:
        if not role_ids:
            query = f"""
            SELECT name FROM {ColorGroup} WHERE guild_id = ?
            LIMIT ? OFFSET ?
            """
            params = (guild_id, limit, offset)
        else:
            placeholders = ",".join(["?" for _ in role_ids])
            query = f"""
            SELECT name FROM {ColorGroup} 
            WHERE 
                guild_id = ? AND permitted_role_id IN ({placeholders})
            LIMIT ? OFFSET ?
            """
            params = (guild_id, *role_ids, limit, offset)
            
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            res = await cur.fetchall()
        return [row["name"] for row in res]
    
    @classmethod
    async def deleteWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> "ColorGroup":
        query = f"""
        DELETE FROM {ColorGroup}
        WHERE guild_id = ? AND name = ?
        RETURNING *
        """
        db.row_factory = ColorGroup.row_factory
        async with db.execute(query, (guild_id, name)) as cur:
            res = await cur.fetchone()
        return res
    
    async def delete(self, db: aiosqlite.Connection) -> "ColorGroup":
        query = f"""
        DELETE FROM {ColorGroup}
        WHERE guild_id = :guild_id AND name = :name
        RETURNING *
        """
        db.row_factory = ColorGroup.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    @classmethod
    async def selectCountWhere(cls, db: aiosqlite.Connection, guild_id: int) -> int:
        query = f"""
        SELECT COUNT(*) as count FROM {ColorGroup} WHERE guild_id = ?
        """
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (guild_id,)) as cur:
            res = await cur.fetchone()
        return res["count"] if res else 0

    async def upsert(self, db: aiosqlite.Connection) -> "ColorGroup":
        query = f"""
        INSERT INTO {ColorGroup}(guild_id, name, prefix, permitted_role_id)
        VALUES (:guild_id, :name, :prefix, :permitted_role_id)
        ON CONFLICT (guild_id, name)
        DO UPDATE SET
            prefix = :prefix,
            permitted_role_id = :permitted_role_id
        RETURNING *
        """
        db.row_factory = ColorGroup.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res


@dataclass
class ColorRole(Table, schema_version=1, trigger_version=1):
    guild_id: int
    group_name: int
    role_id: int
    
    @classmethod
    async def create_table(cls, db: aiosqlite.Connection):
        query = f"""
        CREATE TABLE IF NOT EXISTS {ColorRole}(
            guild_id INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, group_name, role_id),
            FOREIGN KEY (guild_id, group_name) REFERENCES {ColorGroup}(guild_id, group_name)
        )
        """
        await db.execute(query)
    
    @classmethod
    async def selectAllWhere(cls, db: aiosqlite.Connection, guild_id: int, group_name: str, limit: int=10, offset: int=0) -> "ColorRole":
        if limit == 0:
            query = f"""
            SELECT * FROM {ColorRole}
            WHERE guild_id = ? AND group_name = ?
            """
            params = (guild_id, group_name)
        else:
            query = f"""
            SELECT * FROM {ColorRole}
            WHERE guild_id = ? AND group_name = ?
            limit ? offset ?
            """
            params = (guild_id, group_name, limit, offset)
        db.row_factory = ColorRole.row_factory
        async with db.execute(query, params) as cur:
            roles = await cur.fetchall()
        return roles
    
    @classmethod
    async def selectWhere(cls, db: aiosqlite.Connection, guild_id: int, group_name: str, role_id: int) -> "ColorRole":
        query = f"""
        SELECT * FROM {ColorRole}
        WHERE guild_id = ? AND group_name = ? AND role_id = ?
        """
        db.row_factory = ColorRole.row_factory
        async with db.execute(query, (guild_id, group_name, role_id)) as cur:
            res = await cur.fetchone()
        return res


    @classmethod
    async def selectExists(cls, db: aiosqlite.Connection, guild_id: int, role_id: int) -> bool:
        query = f"""
        SELECT EXISTS(
            SELECT 1 FROM {ColorRole}
            WHERE guild_id = ? AND role_id = ?
        )
        """
        db.row_factory = None
        async with db.execute(query, (guild_id, role_id)) as cur:
            res = await cur.fetchone()
        return bool(res[0])
        
    async def upsert(self, db: aiosqlite.Connection) -> "ColorRole":
        query = f"""
        INSERT INTO {ColorRole}(guild_id, group_name, role_id)
        VALUES (:guild_id, :group_name, :role_id)
        ON CONFLICT (guild_id, group_name, role_id)
        DO NOTHING
        """
        db.row_factory = ColorRole.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

    async def delete(self, db: aiosqlite.Connection):
        query = f"""
        DELETE FROM {ColorRole}
        WHERE guild_id = :guild_id AND group_name = :group_name AND role_id = :role_id
        RETURNING *
        """
        db.row_factory = ColorRole.row_factory
        async with db.execute(query, self.asdict()) as cur:
            res = await cur.fetchone()
        return res

class GroupTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction[Kagami], value: str) -> list[Choice[str]]:
        async with interaction.client.dbman.conn() as db:
            role_ids = [role.id for role in interaction.user.roles]
            role_ids += [0]
            names = await ColorGroup.selectNamesWhere(db, interaction.guild_id, role_ids=role_ids)
        groups = [Choice(name=g, value=g) for g in names if value.lower() in g.lower()]
        return groups
    
    async def transform(self, interaction: Interaction[Kagami], value: str) -> ColorGroup:
        async with interaction.client.dbman.conn() as db:
            group = await ColorGroup.selectWhere(db, interaction.guild_id, value)
        role_ids = [role.id for role in interaction.user.roles] + [0]
        if group is not None and group.permitted_role_id not in role_ids:
            group = None
        return group
    
class ColorTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction[Kagami], value: str) -> list[Choice[str]]:
        async with interaction.client.dbman.conn() as db:
            group_name: str = interaction.namespace.group
            group = None
            colors = []
            if group_name is not None:
                colors: list[ColorRole] = await ColorRole.selectAllWhere(db, interaction.guild_id, group_name)
                group = await ColorGroup.selectWhere(db, interaction.guild_id, group_name)
            else:
                return [] # ensures that the group is valid
        roles = [interaction.guild.get_role(color.role_id) for color in colors]
        if group is not None and group.prefix is not None:
            roles += [role for role in interaction.guild.roles if role.name.startswith(group.prefix)]
        if group.prefix is None: 
            group.prefix = ''
        choices = [Choice(name=role.name.removeprefix(group.prefix).lstrip(), value=str(role.id)) for role in roles if value.lower() in role.name.lower()][:25]
        return choices

    async def transform(self, interaction: Interaction[Kagami], value: str) -> ColorRole:
        if not value.isdigit():
            value = discord.utils.get(interaction.guild.roles, name=value).id
        group_name = interaction.namespace.group
        color = None
        if group_name is not None:
            async with interaction.client.dbman.conn() as db:
                group = await ColorGroup.selectWhere(db, interaction.guild_id, group_name)
                color = await ColorRole.selectWhere(db, interaction.guild_id, group.name, int(value))
            if color is None and group.prefix is not None:
                role: discord.Role = discord.utils.find(lambda r: r.name.startswith(group.prefix) and r.id == int(value), interaction.guild.roles)
                color = ColorRole(interaction.guild_id, group_name, role.id)
        return color

Group_Transform = Transform[ColorGroup, GroupTransformer]
Color_Transform = Transform[ColorRole, ColorTransformer]

def color_setup_check():
    async def predicate(interaction: Interaction[Kagami]):
        async with interaction.client.dbman.conn() as db:
            count = await ColorGroup.selectCountWhere(db, interaction.guild_id)
        if count == 0:
            raise app_commands.CheckFailure("An administrator must register a color group before you can use these commands")
            return False
        else:
            return True
    return app_commands.check(predicate)

async def remove_roles(db: aiosqlite.Connection, user: discord.Member):
    existing_roles = []
    for role in user.roles:
        if await ColorRole.selectExists(db, user.guild.id, role.id):
            existing_roles.append(role)
        elif await ColorGroup.selectPrefixMatch(db, user.guild.id, role.name):
            existing_roles.append(role)
    await user.remove_roles(*existing_roles, reason="Switched color role")


@dataclass
class RoleData:
    name: str
    rgb: tuple[int]


def create_preview(colors: list[RoleData], group: ColorGroup):
    WIDTH = 64 * 10
    MARGINAL_HEIGHT = 64
    LEFT_MARGIN = 16
    HEIGHT = MARGINAL_HEIGHT * len(colors)

    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image, "RGB")
    fnt = ImageFont.load_default(size=40)
    for i, data in enumerate(colors):
        name = data.name.removeprefix(group.prefix if group.prefix is not None else '').lstrip()
        # draw color
        y = i * MARGINAL_HEIGHT
        draw.rectangle(((0, y), (WIDTH, y + MARGINAL_HEIGHT)), fill=data.rgb)
        r, g, b = data.rgb
        br, bg, bb = int(r*.8 + 0xff*.2), int(g*.8 + 0xff*.2), int(b*.8 + 0xff*.2)
        
        text = f"{name}- #{r:02X}{g:02X}{b:02X}"
        text_width, text_height = draw.textlength(text, font=fnt, font_size=fnt.size), fnt.size
        offest = (MARGINAL_HEIGHT - text_height) // 2
        draw.rectangle(((LEFT_MARGIN, y+offest), (LEFT_MARGIN + text_width, y + text_height + offest)), fill=(br, bg, bb))
        
        draw.text((LEFT_MARGIN, y + MARGINAL_HEIGHT//2), text, anchor="lm", fill="black", font=fnt)
    buffer = BytesIO()
    image.save(buffer, "png")
    buffer.seek(0)
    return buffer

class NoGroup(errors.CustomCheck):
    MESSAGE = "There is not a group with that name that can be accessed"

class ExistingGroup(errors.CustomCheck):
    MESSAGE = "There is already a group with that name"

class NoColor(errors.CustomCheck):
    MESSAGE = "That color is not registered in that group"

@app_commands.default_permissions(manage_roles=True)
class ColorCogAdmin(GroupCog, name="admin-color"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman
    
    @app_commands.command(name="add-group", description="Registeres a color group with the bot")
    async def add_group(self, interaction: Interaction, group: Group_Transform, prefix: str=None, required_role: discord.Role=None):
        await respond(interaction, ephemeral=True)
        if group:
            raise ExistingGroup
        role_id = required_role.id if required_role is not None else 0
        new_group = ColorGroup(guild_id=interaction.guild_id, name=interaction.namespace.group, prefix=prefix, permitted_role_id=role_id)
        async with self.bot.dbman.conn() as db:
            await new_group.upsert(db)
            await db.commit()
        await respond(interaction, "Registered new color group", delete_after=5)
    
    @app_commands.command(name="edit-group", description="Edit the details of a color group")
    async def edit_group(self, interaction: Interaction, group: Group_Transform, prefix: str=None, required_role: discord.Role=None):
        await respond(interaction, ephemeral=True)
        if group is None:
            raise NoGroup
        role_id = required_role.id if required_role is not None else 0
        group.prefix = prefix
        group.permitted_role_id = role_id
        async with self.bot.dbman.conn() as db:
            await group.upsert(db)
            await db.commit()
        await respond(interaction, f"Updated the details of the group: {group.name}")
    
    # @app_commands.command(name="rename-group", description="Renames an existing color group")
    # TODO Think about a way to allow this since currently the name is a primary key and changing the name is not a good idea
    # I may be able to introduce an integer primary key and then just bind the name and guild columns to be unique and switch around how the references work for that
    # This would be annoying to have to rewrite but would allow for renaming of groups if that is important

    @app_commands.command(name="remove-group", description="Registeres a color group with the bot")
    async def remove_group(self, interaction: Interaction, group: Group_Transform):
        await respond(interaction, ephemeral=True)
        if group is None:
            raise NoGroup
        async with self.bot.dbman.conn() as db:
            await ColorGroup.deleteWhere(db, interaction.guild_id, group.name)
            await db.commit()
        await respond(interaction, f"Deleted the group: {group.name}", delete_after=5)
    
    @app_commands.command(name="add-color", description="Register an arbitrary color role to a group")
    async def add_color(self, interaction: Interaction, group: Group_Transform, role: discord.Role):
        await respond(interaction, ephemeral=True)
        if group is None:
            raise NoGroup
        role_id = role.id
        new_color = ColorRole(interaction.guild_id, group_name=group.name, role_id=role_id)
        async with self.bot.dbman.conn() as db:
            await new_color.upsert(db)
            await db.commit()
        await respond(interaction, f"Added the role: {role.name} to the group: {group.name}", delete_after=5)
        
    @app_commands.command(name="remove-color", description="Removes an arbitrary color from a group")
    async def remove_color(self, interaction: Interaction, group: Group_Transform, color: Color_Transform):
        await respond(interaction, ephemeral=True)
        if group is None:
            raise NoGroup
        if color is None:
            raise NoColor
        
        async with self.bot.dbman.conn() as db:
            await color.delete(db)
            await db.commit()
        await respond(interaction, f"Deregistered the color role: {interaction.guild.get_role(color.role_id).name}", delete_after=5)
        

class ColorCog(GroupCog, name="color"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman
    
    
    async def cog_load(self):
        await self.bot.dbman.setup(table_group=__name__,
                                   drop_tables=self.bot.config.drop_tables,
                                   drop_triggers=self.bot.config.drop_triggers,
                                   ignore_schema_updates=self.bot.config.ignore_schema_updates,
                                   ignore_trigger_updates=self.bot.config.ignore_trigger_updates)

        pass
    
    async def on_ready(self):
        pass
    
    @app_commands.command(name="list", description="Generates an image preview of all colors on the server")
    @color_setup_check()
    async def preview(self, interaction: Interaction, group: Group_Transform): 
        await respond(interaction, ephemeral=False)
        if group is None:
            raise NoGroup            
        async with self.bot.dbman.conn() as db:
            known_roles = await ColorRole.selectAllWhere(db, interaction.guild_id, group.name)
        roles: list[discord.Role] = [interaction.guild.get_role(kr.id) for kr in known_roles]
        if group.prefix is None:
            group.prefix = ''
        roles += list(reversed([role for role in interaction.guild.roles if role.name.startswith(group.prefix)]))
        data = [RoleData(name=role.name, rgb = role.color.to_rgb()) for role in roles]
        image_buffer = create_preview(data, group)
        
        await respond(interaction, attachments=[discord.File(fp=image_buffer, filename="color_image.png")])
    
    @app_commands.command(name="get", description="Changes your color to the selected color")
    @color_setup_check()
    async def get(self, interaction: Interaction, group: Group_Transform, color: Color_Transform):
        await respond(interaction, ephemeral=True)
        if group is None:
            raise NoGroup
        if color is None:
            raise NoColor
        async with self.bot.dbman.conn() as db:
            await remove_roles(db, interaction.user)
            role = interaction.guild.get_role(color.role_id)
            await interaction.user.add_roles(role)
            await respond(interaction, f"Switched your color to {role.name}", delete_after=5)
 

async def setup(bot: Kagami):
    await bot.add_cog(ColorCog(bot))
    await bot.add_cog(ColorCogAdmin(bot))
