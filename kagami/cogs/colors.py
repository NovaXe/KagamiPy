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
from utils.depr_db_interface import Database
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
    async def selectPrefixWhere(cls, db: aiosqlite.Connection, guild_id: int, name: str) -> str:
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

    async def upsert(self, db: aiosqlite.Connection) -> "ColorGroup":
        query = f"""
        INSERT INTO {ColorGroup}(guild_id, name, prefix, permitted_role_id)
        VALUES (:guild_id, :name, :prefix, :permitted_role_id)
        ON CONFLICT (guild_id)
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
        else:
            query = f"""
            SELECT * FROM {ColorRole}
            WHERE guild_id = ? AND group_name = ?
            limit ? offset ?
            """
        db.row_factory = ColorRole.row_factory
        async with db.execute(query, (guild_id, group_name, limit, offset)) as cur:
            roles = await cur.fetchall()
        return roles


class GroupTransformer(Transformer):
    async def autocomplete(self, interaction: Interaction[Kagami], value: str) -> List[Choice[str]]:
        async with interaction.client.dbman.conn() as db:
            role_ids = [role.id for role in interaction.user.roles]
            names = await ColorGroup.selectNamesWhere(db, interaction.guild_id, role_ids=role_ids)
        return [Choice(g, g) for g in names if g.lower() in value.lower()]
    
    async def transform(self, interaction: Interaction[Kagami], value: str) -> str:
        async with interaction.client.dbman.conn() as db:
            group = await ColorGroup.selectWhere(db, interaction.guild_id, value)
        if group.permitted_role_id not in [role.id for role in interaction.user.roles]:
            group = None
        return group

Group_Transform = Transform[ColorGroup, GroupTransformer]

@app_commands.default_permissions(manage_roles=True)
class ColorCogAdmin(GroupCog, name="color-admin"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config
        self.dbman = bot.dbman
    
    
    # @app_commands.command(name="register", description="registers a new arbitrary color role")
    # async def register(self, interation: Interaction, role: discord.Role, group: Group_Transform="everyone"):
    #     await respond(interation, ephemeral=True)
    #     async with self.bot.dbman.conn() as db:
    #         raise NotImplementedError
    
@dataclass
class RoleData:
    name: str
    rgb: tuple[int]


def create_preview(colors: list[RoleData]):
    WIDTH = 512
    MARGINAL_HEIGHT = 40
    HEIGHT = MARGINAL_HEIGHT * len(colors)

    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image, "RGB")
    fnt = ImageFont.truetype("Pillow/Tests/fonts/FreeMono.ttf", 40)
    for i, data in enumerate(colors):
        name = data.name
        # draw color
        y = i * MARGINAL_HEIGHT
        draw.rectangle(((0, y), (WIDTH, y + MARGINAL_HEIGHT)), fill=data.rgb)
        r, g, b = data.rgb
        br, bg, bb = int(r*.2 + 0xff*.8), int(g*.2 + 0xff*.8), int(b*.2 + 0xff*.8)

        text = f"{name}- #{r:02X}{g:02X}{b:02X}"
        text_width, text_height = draw.textlength(text), fnt.size
        half_width = (WIDTH - text_width) // 2
        draw.rectangle(((half_width, y), (WIDTH - half_width, y + MARGINAL_HEIGHT)), fill=(br, bg, bb))
        
        draw.text((WIDTH//2 - 1, y + MARGINAL_HEIGHT // 2), text, anchor="mm", fill="black", font=fnt)
    buffer = BytesIO()
    image.save(buffer, "png")
    buffer.seek(0)
    return buffer


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
    
    @app_commands.command(name="preview", description="Generates an image preview of all colors on the server")
    async def preview(self, interaction: Interaction, group: Group_Transform=None): 
        await respond(interaction, ephemeral=True)
        if group is None:
            raise errors.CustomCheck("There is not a group with that name that you can access")
            
        async with self.bot.dbman.conn() as db:
            known_roles = await ColorRole.selectAllWhere(db, interaction.guild_id, group.name)
        roles: list[discord.Role] = [interaction.guild.get_role(kr.id) for kr in known_roles]
        roles += list(reversed([role for role in interaction.guild.roles if role.name.startswith(group.prefix)]))
        data = [RoleData(name=role.name, rgb = role.color.to_rgb()) for role in roles]
        image_buffer = create_preview(data)
        
        await respond(interaction, attachments=[discord.File(fp=image_buffer, filename="color_image.png")])
        
 
    @app_commands.command(name="colorpreview", description="gives an image preview of the colors available")
    async def color_preview(self, interaction: discord.Interaction):
        await respond(interaction)
        color_roles = list(reversed([role for role in interaction.guild.roles if "C:" in role.name]))

        image = Image.new("RGB", (512, len(color_roles) * 40))
        active_draw = ImageDraw.Draw(image, "RGB")
        for i in range(len(color_roles)):
            test_name = color_roles[i].name[2:]
            offset: int = len(test_name) - len(test_name.lstrip(' ')) + 2

            color = "#%02x%02x%02x" % color_roles[i].color.to_rgb()
            name = color_roles[i].name[+offset:]
            active_draw.rectangle(((0, i * 40), (512, i * 40 + 40)), fill=color)

            r, g, b = color_roles[i].color.to_rgb()
            r, g, b = int(r*0.8), int(g*0.8), int(b*0.8)
            ri, gi, bi = int(0xff * 0.2), int(0xff * 0.2), int(0xff * 0.2)
            bounding_color = "#%02x%02x%02x" % ((r+ri, g+gi, b+bi)
                                                if (r+ri <= 0xff and g+gi <= 0xff and b+bi <= 0xff) else (r, g, b))

            # font = ImageFont.truetype("arialbd.ttf", 30)
            font = ImageFont.truetype("bot/fonts/arialbd.ttf", 30)
            text = f"{name}- {color}"
            bb_left, bb_top, bb_right, bb_bottom = active_draw.textbbox((0, 0), text, font=font)
            bb_left, bb_top, bb_right, bb_bottom = active_draw.textbbox((255 - bb_right/2, i * 40 + 20 - (bb_bottom / 2)), text, font=font)
            active_draw.rectangle((bb_left-5, bb_top-5, bb_right+5, bb_bottom+5), fill=bounding_color)

            try:
                active_draw.text((255, i * 40 + 20), text, anchor="mm", fill="black", font=font)
            except Exception as e:
                print(e)
        output_buffer = BytesIO()
        image.save(output_buffer, "png")
        output_buffer.seek(0)

        await respond(interaction, attachments=[discord.File(fp=output_buffer, filename="color_image.png")])
    
    


async def setup(bot: Kagami):
    await bot.add_cog(ColorCog(bot))
    await bot.add_cog(ColorCogAdmin(bot))
