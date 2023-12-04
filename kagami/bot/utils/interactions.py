import discord
from discord import Interaction

from bot.utils.context_vars import CVar


async def respond(interaction: Interaction=None, content: str=None, ephemeral=False, thinking=False, followup=False, **kwargs):
    if not interaction: interaction = current_interaction.value
    kwargs.update({"content": content})
    if content:
        try:
            if followup:
                response = await interaction.followup.send(ephemeral=ephemeral, **kwargs)
            else:
                response = await interaction.response.send_message(ephemeral=ephemeral, **kwargs)
        except discord.InteractionResponded:
            try:
                response = await interaction.edit_original_response(**kwargs)
            except discord.NotFound:
                response = await interaction.followup.send(ephemeral=ephemeral, **kwargs)
    else:
        try:
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
            response = await interaction.original_response()
        except discord.InteractionResponded as e:
            if followup:
                response = await interaction.followup.send("...", ephemeral=ephemeral)
            else:
                response = await interaction.original_response()
        except discord.NotFound:
            return None
    return response

current_interaction = CVar[Interaction]('current_interaction', default=None)