from typing import List

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from io import BytesIO

import discord
import discord.utils
from discord.ext import commands
from discord import app_commands
from bot.utils import modals


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.ctx_menu = app_commands.ContextMenu(
            name="Reply",
            callback=self.msg_reply,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    @app_commands.command(name="echo", description="repeats the sender's message")
    async def msg_echo(self, interaction: discord.Interaction, string: str) -> None:
        channel: discord.channel = interaction.channel
        await channel.send(string)
        await interaction.response.send_message(content="echoed", ephemeral=True, delete_after=1)

    @app_commands.command(name="status", description="sets the custom status of the bot")
    async def set_status(self, interaction: discord.Interaction, status: str = None):
        await self.bot.change_presence(activity=discord.Game(name=status))
        await interaction.response.send_message("status changed", ephemeral=True, delete_after=1)

    @app_commands.command(name="color", description="lets you select any color from the server")
    async def color_role(self, interaction: discord.Interaction, color: str):
        role = discord.utils.get(interaction.guild.roles, name=color)
        user_roles = [role for role in interaction.user.roles if "C:" not in role.name]
        user_roles.append(role)
        await interaction.user.edit(roles=user_roles)
        await interaction.response.send_message(content="added role", ephemeral=True, delete_after=1)

    @color_role.autocomplete("color")
    async def color_role_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        colors = [role for role in interaction.guild.roles if "C:" in role.name]

        return [
            app_commands.Choice(name=color.name[2:], value=color.name)
            for color in colors if current.lower() in color.name.lower()
        ][:25]

    @app_commands.command(name="colorpreview", description="gives an image preview of the colors available")
    async def color_preview(self, interaction: discord.Interaction):
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

            font = ImageFont.truetype("arialbd.ttf", 30)
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

        await interaction.response.send_message(file=discord.File(fp=output_buffer, filename="color_image.png"))

    # context menu commands
    async def msg_reply(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.send_modal(modals.MessageReply(message))


async def setup(bot):
    await bot.add_cog(Fun(bot))
