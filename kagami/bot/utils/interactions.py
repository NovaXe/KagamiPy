import discord
from discord import Interaction


async def respond(interaction: Interaction, content: str=None, ephemeral=False, thinking=False, followup=False, **kwargs):
    kwargs.update({"content": content})
    if content:
        try:
            response=await interaction.response.send_message(ephemeral=ephemeral, **kwargs)
        except discord.InteractionResponded:
            try:
                response=await interaction.edit_original_response(**kwargs)
            except discord.NotFound:
                response = await interaction.followup.send(**kwargs)

    else:
        try:
            response=await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        except discord.InteractionResponded:
            response = None
            pass
    return response

