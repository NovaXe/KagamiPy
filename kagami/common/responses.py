import asyncio
from dataclasses import dataclass
from typing import(Callable)
import discord
from discord import (PartialMessage, Attachment, File, Embed)
from discord.ext import (commands, tasks)
from discord.utils import MISSING

from ui.custom_view import MessageInfo, CustomView

@dataclass
class MessageElements:
    content: str="No Content"
    view: CustomView=MISSING
    attachments: list[Attachment]=MISSING
    files: list[File]=MISSING
    embeds: list[Embed] = MISSING


# TODO Persistent Message Tracking
# Keep track per server of all the persistent messages accessible by their channel id or something of the like
# If a channel already has a persistent message throw an error on the command run
# potential ephemeral only mode so that it doesn't fuck with everyone else's shit

class PersistentMessage:
    def __init__(self, bot: commands.Bot, guild_id, message_info: MessageInfo, message_elems: MessageElements=MessageElements,
                 refresh_callback: Callable=None, seperator:bool=False, refresh_delay: int = 0, persist_interval=60):
        self.bot = bot
        self.guild_id = guild_id
        self.channel_id = message_info.channel_id
        self.message_id = message_info.id
        self.message_elems: MessageElements = message_elems
        self.message_content = self.message_elems.content
        self.refresh_delay_counter = 0
        self.refresh_callback: Callable[[int, int, MessageElements], str] = refresh_callback
        self.seperator=seperator
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


    def get_message_content(self):
        if self.refresh_callback:
            return self.refresh_callback(self.guild_id, self.channel_id, self.message_elems.content)
        else:
            return "No Content"

    def getMessageElems(self):
        if self.refresh_callback:
            return self.refresh_callback(self.guild_id, self.channel_id, self.message_elems)
        else:
            return MessageElements

    def messageContent(self):
        content = self.message_elems.content
        if self.seperator:
            new_content = f"**`{'═'*max(len(content), 47)}`\n`{content}`**"
        else:
            new_content = f"**`{content}`**"
        return new_content


    def get_partial_message(self) -> PartialMessage:
        channel = self.bot.get_channel(self.channel_id)
        if channel is not None:
            message = channel.get_partial_message(self.message_id)
        else:
            message = None
        return message

    async def send_message(self):
        channel = self.bot.get_channel(self.channel_id)
        # message = await channel.send(content=self.message_elems.content)
        elems = self.message_elems
        text = self.messageContent()
        message = await channel.send(content=text,
                                     view=elems.view,
                                     files=elems.files,
                                     embeds=elems.embeds)

        message_info = MessageInfo.init_from_message(message)
        elems.view.setMessageInfo(message_info=message_info)
        self.message_id = message.id
        self.channel_id = message.channel.id

    # TODO allowing editing messages with views and attachments
    async def attempt_message_edit(self, message: PartialMessage):
        try:
            # await message.edit(content=self.message_elems.content, )
            elems = self.message_elems
            text = self.messageContent()
            await message.edit(content=text,
                               view=elems.view,
                               attachments=elems.attachments,
                               embeds=elems.embeds)
        except (discord.HTTPException, discord.NotFound):
            await self.send_message()

    async def attempt_message_delete(self, message: PartialMessage):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    async def refresh(self):
        if self.refresh_callback:
            # self.message_elems.content = self.get_messsage_content()
            self.message_elems = self.getMessageElems()
            if self.message_elems.view:
                await self.message_elems.view.refreshButtonState()




    @tasks.loop()
    async def persist(self):
        message = self.get_partial_message()

        if self.refresh_delay == 0:
            await self.refresh()
        else:
            if self.refresh_delay_counter >= self.refresh_delay:
                self.refresh_delay_counter = 0
                await self.refresh()
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


