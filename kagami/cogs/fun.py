import enum
from typing import (
    List,
    Literal
)
import asyncio

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from io import BytesIO


import discord
import discord.utils
from discord.ext import commands
from discord import app_commands

from utils.ui import MessageReply
from common.interactions import respond


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
                name="Mirror Reactions",
                callback=self.msg_mirror_reactions
            )
        ]

        for ctx_menu in self.ctx_menus:
            self.bot.tree.add_command(ctx_menu)
        self.reaction_messages = {}

    react_group = app_commands.Group(name="react", description="Commands regarding to automatic message reactions")


    async def cog_unload(self) -> None:
        for ctx_menu in self.ctx_menus:
            self.bot.tree.remove_command(ctx_menu.name, type=ctx_menu.type)

    @app_commands.command(name="echo", description="repeats the sender's message")
    async def msg_echo(self, interaction: discord.Interaction, string: str) -> None:
        await respond(interaction, ephemeral=True)
        channel: discord.channel = interaction.channel
        await channel.send(string)
        await respond(interaction, content="echoed", ephemeral=True, delete_after=1)


    # activities = [discord.Game, discord.Streaming, discord.CustomActivity]
    class ActivityChoices(enum.Enum):
        Game = discord.Game
        Custom = discord.CustomActivity

    @app_commands.command(name="setstatus", description="sets the custom status of the bot")
    async def set_status(self, interaction: discord.Interaction,
                         status: str=None, activity_type: ActivityChoices=ActivityChoices.Custom):
        await respond(interaction)
        new_activity = activity_type.value(name=status)
        await self.bot.change_presence(activity=new_activity)
        await respond(interaction, f"Changed status to: `{new_activity}`", ephemeral=True, delete_after=3)


    @app_commands.command(name="color", description="lets you select any color from the server")
    async def color_role(self, interaction: discord.Interaction, color: str):
        await respond(interaction)
        role = discord.utils.get(interaction.guild.roles, name=color)
        user_roles = [role for role in interaction.user.roles if "C:" not in role.name]
        user_roles.append(role)
        await interaction.user.edit(roles=user_roles)
        await respond(interaction, content="added role", ephemeral=True, delete_after=1)

    @color_role.autocomplete("color")
    async def color_role_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        colors = [role for role in interaction.guild.roles if "C:" in role.name]

        return [
            app_commands.Choice(name=color.name[2:], value=color.name)
            for color in colors if current.lower() in color.name.lower()
        ][:25]

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


    @app_commands.command(name="fish", description="fish reacts all")
    async def fish_all(self, interaction: discord.Interaction):
        await respond(interaction)
        assert ("enabled" in self.fish_all.__dict__)
        new_state = not self.fish_all.enabled.get(interaction.guild_id, False)
        self.fish_all.enabled[interaction.guild_id] = new_state
        await respond(interaction, f"Fish Mode: {'On' if new_state else 'Off'}")
    fish_all.enabled = {}

    @app_commands.command(name='timeout', description='sever mutes someone in vc')
    async def timeout_user(self, interaction: discord.Interaction, member: discord.Member):
        await respond(interaction)
        is_muted = member.voice.mute
        await member.edit(mute=not is_muted)
        if is_muted:
            response = f"`{member.name}` can speak again"
        else:
            response = f"`{member.name}` can no longer speak"
        await respond(interaction, response)

    @app_commands.command(name='spam', description='spam ping them lol')
    async def spam_ping(self, interaction: discord.Interaction, mode: Literal["Ping", "Direct Message"], user: discord.Member, msg: str, count: int=5):
        await respond(interaction, ephemeral=True, content=f"Spamming {user.mention}")
        count = 20 if count > 20 else count
        for i in range(count):
            # if i % 5 == 0:
            #     await asyncio.sleep(delay=5)
            if mode == 'Ping':
                await interaction.channel.send(content=f"{user.mention} {msg}")
            else:
                await user.send(content=f'{msg}')
            await asyncio.sleep(delay=1)



    @app_commands.command(name="galactic", description="converts text to the galactic alphabet")
    async def galactic_text(self, interaction: discord.Interaction, text: str, to_alpha:bool=False):
        await respond(interaction)
        alpha_g = "ᔑ ʖ ᓵ ↸ ᒷ ⎓ ⊣ ⍑ ╎ ⋮ ꖌ ꖎ ᒲ リ 𝙹 !¡ ᑑ ∷ ᓭ ℸ ⚍ ⍊ ∴ ̇/ || ⨅".split(' ')
        alphabet_str = "a b c d e f g h i j k l m n o p q r s t u v w x y z"
        alpha = alphabet_str.split(' ')
        # upper = alphabet_str.upper().split(' ')
        alphabet_swap = {a: g for a, g in zip(alpha, alpha_g)}

        if to_alpha:
            for a,g in alphabet_swap.items():
                text = text.replace(g,a)
            await respond(interaction, text)
        else:
            text = text.lower()
            for a,g in alphabet_swap.items():
                text = text.replace(a,g)
            await respond(interaction, text)



    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        d: dict
        if d := self.fish_all.__dict__.get("enabled", False):
            if d.get(message.guild.id, False):
                await message.add_reaction("🐟")

    # context menu commands
    async def msg_reply(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(MessageReply(message))

    async def msg_mirror_reactions(self, interaction: discord.Interaction, message: discord.Message):
        await respond(interaction, ephemeral=True)
        for reaction in message.reactions:
            if interaction.user.id in (u.id for u in reaction.users()):
                await message.add_reaction(reaction)
        await respond(interaction, content="I have mirrored your reactions on the message")


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
