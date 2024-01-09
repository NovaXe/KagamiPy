from typing import Union, List, Any

import discord
from discord.app_commands import Transformer, Choice, Group
from discord.ext import commands
from discord import app_commands, Interaction
from discord.ext.commands import GroupCog, Cog

from bot.kagami_bot import Kagami
from bot.utils.bot_data import Sentinel
from bot.utils.interactions import respond


class SentinelTransformer(Transformer):
    def __init__(self):
        pass

    async def autocomplete(self, interaction: Interaction, value: Union[int, float, str], /) \
            -> list[Choice[str]]:
        pass

    async def transform(self, interaction: Interaction, value: Any, /) -> Sentinel:
        pass



"""
sentinel behavior
list of phrases that can trigger the sentinel
list of responses
responses include:
- messages
- replies
-- views and attachments allowed
- reactions
responses can be associated directly with each trigger phrase or randomly picked

a sentinel will trigger only once even if multiple of its phrases are triggered
spam protection and slight randomness in responding to make sentinels more spontaneous
channels can be blacklisted, either for specific sentinels or the whole system


"""

"""
sentinel data association
globals
- sentinels

servers
- server_id
-- sentinels
-- global_sentinels
--- uses
--- users
---- uses
--- is_enabled

servers: {
    server_id: {
        name: str
        sentinels: {
            sentinel_name: {
                uses: int,
                enabled: bool,
                users: {
                    user_id: int
                },
                triggers: [
                    {
                        object: "phrase" / "emoji",
                        whole_word: bool
                        is_reaction: bool,
                    },
                ],
                responses: [
                    {
                        message: {
                            content: "",
                            view: None,
                        },
                        reactions: [
                            "",
                        ],
                        
                    },
                ]
            },
        },
    },
}

"""


"""
transformer template

"sentence phrase or word segment"
Word
::emoji::


"""


class SentinelCog(GroupCog, group_name="sentinel"):
    def __init__(self, bot: Kagami):
        self.bot = bot
        self.config = bot.config

    add = Group(name="add", description="adding triggers and responses to sentinels")
    update = Group(name="update", description="update a sentinel's behavior")
    remove = Group(name="remove", description="remove triggers and responses to sentinels")
    info = Group(name="info", description="tells you stuff about a sentinel")
    list = Group(name="list", description="lists all sentinels")

    async def sentinel_create(self, interaction: Interaction, sentinel_name: SentinelTransformer):
        pass

    async def sentinel_delete(self, interaction: Interaction, sentinel_name: SentinelTransformer):
        pass

    @add.command(name="trigger")
    async def sentinel_add_trigger(self, interaction: Interaction, sentinel_name: str, phrase: str, reaction: str, whole_word: bool=True):
        pass


    async def sentinel_update_global(self, interaction: Interaction, sentinel_name: str,
                                     trigger_phrase: str, trigger_reaction: str, ):
        pass

    @add.command(
        name="pair",
        description="add a phrase response pair to the sentinel")
    async def sentinel_add_pair(self, interaction: Interaction, sentinel_name: str, trigger: str=None, reply: str=None, reaction: str=None):
        await respond(interaction)
        await respond(interaction, "I just harvested your data and did nothing with it")
        pass

async def setup(bot):
    await bot.add_cog(SentinelCog(bot))
