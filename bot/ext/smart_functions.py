import discord
from discord import (Interaction, TextChannel, Message, PartialMessage, InteractionResponse, InteractionMessage)



async def respond_old(interaction: Interaction, message: str=None):
    if message:
        try:
            await interaction.response.send_message(content=message)
        except discord.InteractionResponded:
            await interaction.edit_original_response(content=message)
    else:
        try:
            await interaction.response.defer()
        except discord.InteractionResponded:
            pass


async def respond(interaction: Interaction, content: str=None, ephemeral=False, **kwargs):
    kwargs.update({"content": content})
    if content:
        try:
            response=await interaction.response.send_message(ephemeral=ephemeral, **kwargs)
        except discord.InteractionResponded:
            response=await interaction.edit_original_response(**kwargs)
    else:
        try:
            response=await interaction.response.defer(ephemeral=ephemeral)
        except discord.InteractionResponded:
            response = None
            pass
    return response
