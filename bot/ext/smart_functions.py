import asyncio
from typing import(Callable)
import discord
from discord import (Interaction, TextChannel, Message, PartialMessage, InteractionResponse, InteractionMessage)
from discord.ext import (commands, tasks)


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


class PersistentMessage:
    def __init__(self, bot: commands.Bot, guild_id, channel_id, default_content: str, message_id=None,
                 refresh_callback=None, refresh_delay: int=0, persist_interval=60):
        self.bot = bot
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.message_content = default_content
        self.refresh_delay_counter = 0
        self.refresh_callback: Callable[[int, int, str], str] = refresh_callback
        """
        guild_id, channel_id, current_content\n
        callback(guild_id: int, channel_id: int, current_content: str) -> message_content:...
        """
        # may modify the refresh sysem to be one and the same with persist and just have a "refresh after n times check"
        self.refresh_delay = max(refresh_delay, 0)
        self.persist.change_interval(seconds=persist_interval)

    #     may be possible that this gets desynced and the persistant message has text from the previous refresh
    #     The content would be behind by an interval and it would be visibly wonky

    def begin(self):
        self.persist.start()

    async def halt(self):
        self.persist.cancel()
        if message:=self.get_partial_message():
            await self.attempt_message_delete(message)


    def get_messsage_content(self):
        if self.refresh_callback:
            return self.refresh_callback(self.guild_id, self.channel_id, self.message_content)
        else:
            return "No Content"

    def get_partial_message(self) -> PartialMessage:
        channel = self.bot.get_channel(self.channel_id)
        message = channel.get_partial_message(self.message_id)
        return message

    async def send_message(self):
        channel = self.bot.get_channel(self.channel_id)
        messsage = await channel.send(content=self.message_content)
        self.message_id = messsage.id

    async def attempt_message_edit(self, message: PartialMessage):
        try:
            await message.edit(content=self.message_content)
        except discord.HTTPException:
            await self.send_message()

    async def attempt_message_delete(self, message: PartialMessage):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    def refresh(self):
        if self.refresh_callback:
            self.message_content = self.get_messsage_content()

    @tasks.loop()
    async def persist(self):
        message = self.get_partial_message()

        if self.refresh_delay == 0:
            self.refresh()
        else:
            if self.refresh_delay_counter >= self.refresh_delay:
                self.refresh_delay_counter = 0
                self.refresh()
            else:
                self.refresh_delay_counter += 1


        if message:
            if message.id != message.channel.last_message_id:
                await asyncio.gather(
                    self.attempt_message_delete(message),
                    self.send_message()
                )
            else:
                await self.attempt_message_edit(message)
        else:
            await self.send_message()