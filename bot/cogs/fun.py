from typing import List
import asyncio

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from io import BytesIO


import discord
import discord.utils
from discord.ext import commands
from discord import app_commands
from bot.utils import ui


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.ctx_menus = [
            app_commands.ContextMenu(
                name="Reply",
                callback=self.msg_reply
            ),
            app_commands.ContextMenu(
                name="Fish",
                callback=self.fish_react
            ),
            app_commands.ContextMenu(
                name="Copy Reactions",
                callback=self.msg_copy_reactions
            )
        ]
        for ctx_menu in self.ctx_menus:
            self.bot.tree.add_command(ctx_menu)
        self.reaction_messages = {}

    async def cog_unload(self) -> None:
        for ctx_menu in self.ctx_menus:
            self.bot.tree.remove_command(ctx_menu.name, type=ctx_menu.type)

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
    async def msg_reply(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(modals.MessageReply(message))

    async def msg_copy_reactions(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True)
        for reaction in message.reactions:
            async for user in reaction.users():
                if user.id == interaction.user.id:
                    await message.add_reaction(reaction)
                    await message.remove_reaction(reaction, interaction.user)

        await interaction.edit_original_response(content="I have copied and removed your reactions")


    async def fish_react(self, interaction: discord.Interaction, message: discord.Message):
        await message.add_reaction("🐟")
        await interaction.response.send_message("Fish Reacted", ephemeral=True, delete_after=3)

    # async def msg_react(self, interaction: discord.Interaction, message: discord.Message):
    #     await interaction.response.defer(ephemeral=True)
    #     user = interaction.user
    #
    #     if message.id in self.reaction_messages.keys():
    #         # print("true")
    #         if user.id == self.reaction_messages[message.id]:
    #             # print("stop")
    #             del self.reaction_messages[message.id]
    #             for reaction in message.reactions:
    #                 await message.remove_reaction(reaction, user)
    #             await interaction.edit_original_response(
    #                 content="Stopped reacting")
    #         else:
    #             # print("not available")
    #             await interaction.edit_original_response(
    #                 content="Another user is currently controlling reactions on this message")
    #     else:
    #         # print("new")
    #         self.reaction_messages[message.id] = user.id
    #
    #         await interaction.edit_original_response(
    #             content="React to the original message to add reactions, use the command again to stop")
    #         await asyncio.sleep(30)
    #         updated_message = await interaction.channel.get_partial_message(message.id).fetch()
    #         del self.reaction_messages[message.id]
    #         await interaction.edit_original_response(content="The time to react has expired")
    #         for reaction in updated_message.reactions:
    #             await updated_message.remove_reaction(reaction, user)

    # @commands.Cog.listener()
    # async def on_reaction_add(self, reaction, user):
    #     # print("reaction add")
    #     if reaction.message.id in self.reaction_messages.keys():
    #         valid_user = self.reaction_messages[reaction.message.id]
    #         if valid_user == user.id or valid_user == self.bot.user.id:
    #             await reaction.message.add_reaction(reaction)
    #
    # @commands.Cog.listener()
    # async def on_reaction_remove(self, reaction, user):
    #     # print("reaction remove")
    #     if reaction.message.id in self.reaction_messages.keys():
    #         valid_user = self.reaction_messages[reaction.message.id]
    #         if valid_user == user.id or valid_user == self.bot.user.id:
    #             await reaction.message.remove_reaction(reaction, self.bot.user)






async def setup(bot):
    await bot.add_cog(Fun(bot))
