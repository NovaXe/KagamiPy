import asyncio

import discord
from discord import Interaction, InteractionResponse, InteractionResponded, InteractionMessage

from bot.utils.context_vars import CVar
from discord import Embed, Attachment, File, Webhook, WebhookMessage
from discord.ui import View
from discord.utils import MISSING

async def respond(target: Interaction | WebhookMessage, content: str=MISSING, *,
                  embeds: Embed=MISSING, attachments: list[Attachment] | list[File]=MISSING, view: View=MISSING,
                  ephemeral: bool=False, force_defer: bool=False, thinking: bool=False, send_followup: bool=False, delete_after: float=None,
                  **kwargs) -> InteractionMessage | WebhookMessage:
    """
    :param target: the Interaction or Webhook object to work with
    :param content: the text content of the message
    :param embeds: list of embeds to send
    :param attachments: list of attachments to send
    :param view: the view to be attached to the message
    :param ephemeral: if the message should be client side
    :param force_defer: attempts to defer and throws an error if it cant
    :param thinking: whether a message should be sent when deferred
    :param send_followup: if the target is an Interaction send a followup
    :param delete_after: automatically deletes the message after a time
    :param kwargs: anything not in the param list that will be passed to sub functions
    :return:
    """
    # print(f"----------------------\nreceived response target: {target}")
    # await asyncio.sleep(1.0)
    # print(f"----------------------\nFinished sleeping")
    if isinstance(target, Interaction):
        # print("is interaction")
        interaction = target
        if force_defer:
            await interaction.response.defer()
            return await interaction.original_response()
        # assert isinstance(interaction.followup, Webhook)
        # assert isinstance(interaction.response, InteractionResponse)

        if send_followup:
            followup = interaction.followup
            return await followupRespond(
                followup,
                content=content,
                embeds=embeds,
                attachments=attachments,
                view=view,
                ephemeral=ephemeral,
                thinking=thinking,
                delete_after=delete_after,
                **kwargs
            )
        else:
            # print("before interaction respond")
            return await interactionRespond(
                interaction,
                content=content,
                embeds=embeds,
                attachments=attachments,
                view=view,
                ephemeral=ephemeral,
                thinking=thinking,
                delete_after=delete_after,
                **kwargs
            )
    elif isinstance(target, WebhookMessage):
        await followupRespond(
            WebhookMessage,
            embeds=embeds,
            attachments=attachments,
            view=view,
            ephemeral=ephemeral,
            thinking=thinking,
            delete_after=delete_after,
            **kwargs
        )
    else:
        raise TypeError("parameter: 'target' must be of type Interaction or WebhookMessage")



async def followupRespond(followup: Webhook | WebhookMessage, content: str=None, *,
                          embeds: Embed=MISSING, attachments: list[Attachment] | list[File]=MISSING, view: View=MISSING,
                          ephemeral: bool=False, thinking: bool=False, delete_after: float=None,
                          **kwargs) -> WebhookMessage:
    # do the same checks for this as with the interaction
    # Check is it has already been sent and if so edit it

    if isinstance(followup, Webhook):
        if attachments is not MISSING and isinstance(attachments[0], Attachment):
            attachments = [await attachment.to_file() for attachment in attachments]

        if not (content or embeds or attachments or view):
            content = "No Content"
            # raise ValueError("Missing at least 1 of the following arguments: 'content, embeds, attachments, view'")
        message = await followup.send(
            content=content,
            embeds=embeds,
            files=attachments,
            view=view,
            ephemeral=ephemeral,
            **kwargs
        )
        if delete_after: await message.delete(delay=delete_after)
        return message
    elif isinstance(followup, WebhookMessage):
        message = await followup.edit(
            content=content,
            embeds=embeds,
            attachments=attachments,
            view=view,
            **kwargs
        )
        await message.delete(delay=delete_after)
        return message
    else:
        raise TypeError("parameter: 'followup' must be of type Webhook or WebhookMessage")



async def interactionRespond(interaction: Interaction, content: str=MISSING, *,
                             embeds: Embed=MISSING, attachments: list[Attachment] | list[File]=MISSING, view=MISSING,
                             ephemeral=False, thinking=False, delete_after=None,
                             **kwargs) -> InteractionMessage:
    # required_send_edit_params = ["content", "embeds", "attachments", "view"]MISSING
    # optional_send_params = ["ephemeral", "delete_after"]
    # edit_parameters = ["content", "embeds", "attachments", "view"]
    # optional_edit_params = ["delete_after"]
    # defer_parameters = ["ephemeral", "thinking"]
    # can_send = content or embeds or attachments or view
    # can_edit = True
    # print("inside interaction respond")
    # print(f"interaction type: {interaction.type}")
    # print(f"interaction command: {interaction.command.name}")
    # print(f"interaction response: {interaction.command}")
    # assert isinstance(interaction.response, InteractionResponse)
    if interaction.response.is_done():
        # print("interaction is done")
        try:
            message = await interaction.original_response()
        except (discord.HTTPException, discord.ClientException, discord.NotFound) as e:
            message = None
            # Maybe send a followup
            # print("Error: Could not find original response to interaction\n"
            #       "Consider using followup after send_modal")
            raise e

        if content or embeds or attachments or view:
            await message.edit(
                content=content,
                embeds=embeds,
                attachments=attachments,
                view=view,
                delete_after=delete_after,
                **kwargs
            )
        return message
    else:
        # print("interaction not done")
        if not (content or embeds or attachments or view):
            # print("no content")
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
            # print("deferred")
            return await interaction.original_response()
        else:
            # print("content")
            if attachments is not MISSING and isinstance(attachments[0], Attachment):
                attachments = [await attachment.to_file() for attachment in attachments]
            await interaction.response.send_message(
                content=content,
                embeds=embeds,
                files=attachments,
                view=view,
                delete_after=delete_after,
                **kwargs
            )
            # print("sent response")
            return await interaction.original_response()




current_interaction = CVar[Interaction]('current_interaction', default=None)
