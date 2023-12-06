import discord
from discord import Interaction, InteractionResponse, InteractionResponded, InteractionMessage

from bot.utils.context_vars import CVar
from discord import Embed, Attachment, File, Webhook, WebhookMessage
from discord.ui import View
from discord.utils import MISSING

async def respond(target: Interaction | WebhookMessage, content: str=MISSING, *,
                  embeds: Embed=MISSING, attachments: list[Attachment] | list[File]=MISSING, view: View=MISSING,
                  ephemeral: bool=False, thinking: bool=False, send_followup: bool=False, delete_after: float=None,
                  **kwargs) -> InteractionMessage | WebhookMessage:
    """
    :param target: the Interaction or Webhook object to work with
    :param content: the text content of the message
    :param embeds: list of embeds to send
    :param attachments: list of attachments to send
    :param view: the view to be attached to the message
    :param ephemeral: if the message should be client side
    :param thinking: if a message should be sent when deferred
    :param send_followup: if the target is an Interaction send a followup
    :param delete_after: automatically deletes the message after a time
    :param kwargs: anything not in the param list that will be passed to sub functions
    :return:
    """

    if isinstance(target, Interaction):
        interaction = target
        assert isinstance(interaction.followup, Webhook)
        assert isinstance(interaction.response, InteractionResponse)
        if send_followup:
            followup = interaction.followup
            return await webhookRespond(
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
        await webhookRespond(
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
        await message.delete(delay=delete_after)
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

    assert isinstance(interaction.response, InteractionResponse)
    if interaction.response.is_done():
        try:
            message = await interaction.original_response()
            await message.edit(
                content=content,
                embeds=embeds,
                attachments=attachments,
                view=view,
                delete_after=delete_after,
                **kwargs
            )
        except (discord.HTTPException, discord.ClientException, discord.NotFound) as e:
            # Maybe send a followup
            print("Error: Could not find original response to interaction\n"
                  "Consider using followup after send_modal")
            raise e

    else:
        if not (content or embeds or attachments or view):
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
            return interaction.original_response()
        else:
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
            return interaction.original_response()





current_interaction = CVar[Interaction]('current_interaction', default=None)