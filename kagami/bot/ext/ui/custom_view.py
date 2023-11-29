from dataclasses import dataclass

import discord

from bot.kagami_bot import Kagami
from discord.ui import (View, Button, Select, TextInput)


@dataclass
class StopBehavior:
    disable_items: bool = False
    remove_view: bool = False
    delete_message: bool = False


@dataclass
class MessageInfo:
    id: int
    channel_id: int
    # guild_id: int
    @classmethod
    def init_from_message(cls, message: discord.Message):
        return cls(id=message.id, channel_id=message.channel.id)

class CustomView(View):
    def __init__(self, *args, timeout: float | None = 120,
                 bot: Kagami, message_info: MessageInfo,
                 stop_behavior: StopBehavior = StopBehavior(disable_items=True),
                 **kwargs):
        super().__init__(timeout=timeout)
        self.bot: Kagami = bot
        self.m_info: MessageInfo = message_info
        self.stop_behavior = stop_behavior

    def partialMessage(self):
        m_id = self.m_info.id
        ch_id = self.m_info.channel_id
        return self.bot.getPartialMessage(m_id, ch_id)

    def setMessageInfo(self, message_info: MessageInfo):
        self.m_info = message_info

    async def onStop(self):
        if self.stop_behavior.delete_message:
            if p_message := self.partialMessage():
                await p_message.delete()
        elif self.stop_behavior.remove_view:
            if p_message := self.partialMessage():
                await p_message.edit(view=None)
        elif self.stop_behavior.disable_items:
            item: Button | Select | TextInput
            for item in self.children:
                item.disabled = True

    async def refreshButtonState(self, *args):
        pass

    async def stop(self):
        await self.onStop()

    async def on_timeout(self) -> None:
        await self.stop()

    async def deleteMessage(self):
        if p_message := self.partialMessage():
            await p_message.delete()



