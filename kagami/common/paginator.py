import collections
import dataclasses
import traceback
from aiosqlite import Connection
from typing import Any, Callable 
from collections.abc import Awaitable, Generator
from abc import ABC, abstractmethod
import sys

import discord
from discord import ButtonStyle, Interaction
import discord.ui as ui
from discord.ui import Item

from bot import Kagami
from common.logging import setup_logging
from common.interactions import respond

logger = setup_logging(__name__)

@dataclasses.dataclass
class ScrollerState:
    user: discord.User | discord.Member
    message: discord.Message
    initial_offset: int
    relative_offset: int
    @property
    def offset(self):
        return self.initial_offset + self.relative_offset

type Interaction = discord.Interaction[Kagami]
T_Callback = Callable[[Interaction, ScrollerState], list[str]]
type PageCallback = Callable[[Interaction, ScrollerState], Awaitable[tuple[str, int, int]]]

Button = ui.Button["Scroller"]

class Scroller(ui.View):
    def __init__(self, message: discord.Message, user: discord.User | discord.Member,
                 page_callback: PageCallback,
                #  count_callback: Callable[[Interaction, ScrollerState], list[str]],
                #  margin_callback: Callable[[Interaction, ScrollerState], list[str]],
                 initial_offset=0,
                 timeout: float | None=300, timeout_delete_delay: float=3):
        """
        page_callback: Returns a string representing the page, and a boolean dictating whether the current page is the last
        initial_offset: What page index the scroller starts on
        timeout: How long until the view enters recovery
        recovery_time: If not 0, specifies how long you have to click on the message before it's deleted
        """
        super().__init__(timeout=timeout)
        self.message: discord.Message = message
        self.timeout_delete_delay = timeout_delete_delay
        self.user: discord.User | discord.Member = user
        self.initial_offset: int = initial_offset
        self.relative_offset: int = 0
        self.page_callback: PageCallback = page_callback

    def __copy__(self):
        scroller = Scroller(
            message=self.message, 
            user=self.user, 
            page_callback=self.page_callback, 
            initial_offset=self.initial_offset, 
            timeout=self.timeout
        )
        scroller.relative_offset = self.relative_offset
        return scroller

    @property
    def state(self):
        return ScrollerState(
            message=self.message,
            user=self.user,
            initial_offset=self.initial_offset,
            relative_offset=self.relative_offset
        )
    
    @property
    def offset(self):
        return self.initial_offset + self.relative_offset

    @property
    def buttons(self) -> Generator[Button, None, None]:
        return (item for item in self.children if isinstance(item, Button))
    
    def add_button(self, callback: Callable[[Interaction, ScrollerState], Awaitable[tuple[str, int]]], 
                   style: ButtonStyle=ButtonStyle.secondary, 
                   label: str | None=None, 
                   emoji: discord.PartialEmoji | discord.Emoji | str | None=None, 
                   row: int | None=None,
                   ephemeral: bool=False):

        class CustomButtom(Button):
            def __init__(self): # All variables are from the wrapper method so proper initialization isn't needed, kinda hacky but really no different than bind
                super().__init__(self, style=style, label=label, emoji=emoji, row=row)
            
            async def callback(self, interaction: Interaction) -> Any:
                await respond(interaction, ephemeral=ephemeral)
                assert isinstance(self.view, Scroller) # Works under the assumption of the view having a state property
                await callback(interaction, self.view.state)
                await self.view.update() 
        self.add_button(CustomButtom())

    async def getPage(self, interaction: Interaction) -> tuple[str, int, int]:
        content, first_index, last_index = await self.page_callback(interaction, self.state)
        return content, first_index, last_index

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        assert interaction.channel is not None
        assert isinstance(interaction.user, discord.Member)
        if interaction.user == self.user or interaction.channel.permissions_for(interaction.user).manage_messages:
            return True
        await respond(interaction, f"Only {self.user.mention} can use this view", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(view=self)
                await self.message.delete(delay=self.timeout_delete_delay)
            except discord.NotFound:
                pass

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any], /) -> None:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        message = f"An error occurred while processing the interaction for {str(item)}:\n```py\n{tb}\n```"
        logger.error(message)
        await interaction.response.send_message(message)

    async def update(self, interaction: Interaction):
        content, first_index, last_index = await self.getPage(interaction)
        is_first = self.offset <= first_index
        is_last = self.offset >= last_index
        # print(f"{is_first=}, {is_last=}, {self.offset=}")

        self.first.disabled = is_first
        self.prev.disabled = is_first
        # TODO add an is_first return value that the callbacks must handle
        # this will allow for a queue with history to work properly as well
        self.next.disabled = is_last 
        self.last.disabled = is_last
        if is_last:
            self.relative_offset = last_index - self.initial_offset
        if is_first:
            self.relative_offset = first_index - self.initial_offset
        self.home.style = ButtonStyle.blurple 

        await self.message.edit(content=content, view=self) 

    @ui.button(emoji="⬆", custom_id="Scroller:first", row=0)
    async def first(self, interaction: Interaction, button: Button):
        await respond(interaction)
        self.relative_offset = -sys.maxsize
        await self.update(interaction)

    @ui.button(emoji="🔼", custom_id="Scroller:prev", row=0)
    async def prev(self, interaction: Interaction, button: Button):
        await respond(interaction)
        self.relative_offset -= 1
        await self.update(interaction)

    @ui.button(emoji="*️⃣", custom_id="Scroller:home", style=ButtonStyle.blurple, row=0)
    async def home(self, interaction: Interaction, button: Button):
        await respond(interaction)
        self.relative_offset = 0
        await self.update(interaction)

    @ui.button(emoji="🔽", custom_id="Scroller:next", row=0)
    async def next(self, interaction: Interaction, button: Button):
        await respond(interaction)
        self.relative_offset += 1
        await self.update(interaction)
    
    @ui.button(emoji="⬇", custom_id="Scroller:last", row=0)
    async def last(self, interaction: Interaction, button: Button):
        await respond(interaction)
        self.relative_offset = sys.maxsize
        await self.update(interaction)

    @ui.button(emoji="🗑", custom_id="Scroller:delete", row=4, style=ButtonStyle.red)
    async def delete(self, interaction: Interaction, button: Button):
        await self.message.delete()
        self.stop()


class SimpleCallback[T](ABC):
    """
    Exists to quickly throw together callbacks without needing to remember the boilerplate required to do so 

    The callback method execution order is as follows
    get_total_item_count > get_items > item_formatter > header_formatter
    Anything returned by a method further ahead than the current one is at a default value and not yet accesable
    """
    PAGE_ITEM_COUNT: int = 10
    # FIRST_PAGE_INDEX: int = 0
    # LAST_PAGE_INDEX: int = 0
    INDEX_DISPLAY_OFFSET: int = 1
    CODEBLOCK_LANGUAGE: str = "swift"
    CONTENT_SEPERATOR: str = "───"

    async def __call__(self, interaction: Interaction, state: ScrollerState) -> tuple[str, int, int]:
        return await self._callback(interaction, state)


    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Creates a callable object that functions like a callback
        Initializes internal defaults and stores the bound args and kwargs
        Bound arguments are accessable from any overwritten method
        """
        self._bound_arguments: tuple[tuple[Any], dict[str, Any]] = (args, kwargs) # tuple, args and kwargs still need to be individually unpacked
        self._total_item_count: int = 0  # total number of items returned by get_total_item_count
        self._items: list[T] = []        # items returned by call to get_items
        self._offset: int = 0            # ScrollerState offset clamped by the total item count

    @abstractmethod
    async def get_total_item_count(self, db: Connection, interaction: Interaction, state: ScrollerState, *args: Any, **kwargs: Any) -> int:
        """
        Abstract method for getting the total items across all pages
        """
        ...

    @abstractmethod
    async def get_items(self, db: Connection, interaction: Interaction, state: ScrollerState, *args: Any, **kwargs: Any) -> list[T]:
        """
        Abstract method for getting the items for the current page
        """
        ...

    @abstractmethod
    async def item_formatter(self, db: Connection, interaction: Interaction, state: ScrollerState, index: int, item: T, *args: Any, **kwargs: Any) -> str:
        """
        Abstract method that formats an individual item
        """
        ...
        return str(item)

    @abstractmethod
    async def header_formatter(self, db: Connection, interaction: Interaction, state: ScrollerState, *args: Any, **kwargs: Any) -> str:
        """
        Abstract method that formats the header which displays at the top of the message
        """
        ...
        return ""

    #@abstractmethod
    async def no_results(self, db: Connection, interaction: Interaction, state: ScrollerState, *args: Any, **kwargs: Any) -> str:
        DEFAULT = "No Results"
        f"""
        Called when there are no items within a page of the view
        Defaults to \"{DEFAULT}\"
        """
        # By default displays \"No <ItemTypeName>\"
        return DEFAULT

    @property 
    def bound_arguments(self) -> tuple[tuple[Any], dict[str, Any]]:
        return self._bound_arguments

    @property
    def total_item_count(self) -> int:
        return self._total_item_count

    @property
    def items(self) -> list[T]:
        return self._items

    @property
    def item_offset(self) -> int:
        return self._offset * self.PAGE_ITEM_COUNT

    def _clamp_offset(self):
        """
        Clamps the offset from the state 
        """
        if self._offset * self.PAGE_ITEM_COUNT > self._total_item_count:
            self._offset = self._total_item_count // self.PAGE_ITEM_COUNT

    def get_display_index(self, index: int) -> int:
        return self._offset * self.PAGE_ITEM_COUNT + index + self.INDEX_DISPLAY_OFFSET

    async def _callback(self, interaction: Interaction, state: ScrollerState) -> tuple[str, int, int]:
        self._offset = state.offset
        args, kwargs = self.bound_arguments
        async with interaction.client.dbman.conn() as db:
            self._total_item_count = await self.get_total_item_count(db, interaction, state, *args, **kwargs)
            self._clamp_offset()
            self._items = await self.get_items(db, interaction, state, *args, **kwargs)

            reps: list[str] = []
            if self._total_item_count > 0:
                for i, item in enumerate(self._items):
                    formatted_item = await self.item_formatter(db, interaction, state, i, item, *args, **kwargs)
                    reps.append(formatted_item)
            else:
                reps.append(await self.no_results(db, interaction, state, *args, **kwargs))

            header = await self.header_formatter(db, interaction, state, *args, **kwargs)

        body = "\n".join(reps)
        content = f"```{self.CODEBLOCK_LANGUAGE}\n" + \
                  f"{header}\n" + \
                  f"{self.CONTENT_SEPERATOR}\n" + \
                  f"{body}\n" + \
                  f"{self.CONTENT_SEPERATOR}\n" + \
                  f"```"
        return content, 0, (self._total_item_count - 1) // 10

# class OldSimpleCallbackBuilder[ITEM_TYPE]:
#     """
#     Exists to quickly throw together callbacks without needing to remember the boilerplate required to do so 
# 
#     The callback method execution order is as follows
#     get_total_item_count > get_items > item_formatter > header_formatter
#     Anything returned by a method further ahead than the current one is at a default value and not yet accesable
#     """
#     PAGE_ITEM_COUNT: int = 10
#     # FIRST_PAGE_INDEX: int = 0
#     # LAST_PAGE_INDEX: int = 0
#     INDEX_DISPLAY_OFFSET: int = 1
#     CODEBLOCK_LANGUAGE: str = "swift"
#     CONTENT_SEPERATOR: str = "───"
#     total_item_count: int = 0 # total number of items returned by get_total_item_count
#     items: list[ITEM_TYPE] = [] # items returned by call to get_items
#     offset: int = 0 # ScrollerState offset clamped by the total item count
# 
#     @classmethod
#     def __new__(cls, *args: Any, **kwargs: Any) -> PageCallback:
#         return cls.get_callback(*args, **kwargs)
# 
#     @classmethod
#     async def get_total_item_count(cls, db: Connection, interaction: Interaction, state: ScrollerState, *args: Any, **kwargs: Any) -> int:
#         ...
# 
#     @classmethod
#     async def get_items(cls, db: Connection, interaction: Interaction, state: ScrollerState, *args: Any, **kwargs: Any) -> list[ITEM_TYPE]:
#         ...
# 
#     @classmethod
#     async def item_formatter(cls, db: Connection, interaction: Interaction, state: ScrollerState, index: int, item: ITEM_TYPE, *args: Any, **kwargs: Any) -> str:
#         ...
# 
#     @classmethod
#     async def header_formatter(cls, db: Connection, interaction: Interaction, state: ScrollerState, *args: Any, **kwargs: Any) -> str:
#         ...
# 
#     @classmethod
#     def get_display_index(cls, index: int) -> int:
#         return cls.offset * cls.PAGE_ITEM_COUNT + index + cls.INDEX_DISPLAY_OFFSET
# 
#     @classmethod
#     def get_callback(cls, *args: Any, **kwargs: Any) -> PageCallback:
#         async def callback(interaction: Interaction, state: ScrollerState) -> tuple[str, int, int]:
#             cls.offset = state.offset
#             async with interaction.client.dbman.conn() as db:
#                 cls.total_item_count = await cls.get_total_item_count(db, interaction, state, *args, **kwargs)
#                 if cls.offset * cls.PAGE_ITEM_COUNT > cls.total_item_count:
#                     cls.offset = cls.total_item_count // 10
#                 cls.items = await cls.get_items(db, interaction, state, *args, **kwargs)
# 
#                 reps: list[str] = []
#                 for i, item in enumerate(cls.items):
#                     formatted_item = await cls.item_formatter(db, interaction, state, i, item, *args, **kwargs)
#                     reps.append(formatted_item)
# 
#                 header = await cls.header_formatter(db, interaction, state, *args, **kwargs)
# 
#             body = "\n".join(reps)
#             content = f"```{cls.CODEBLOCK_LANGUAGE}\n" + \
#                       f"{header}\n" + \
#                       f"{cls.CONTENT_SEPERATOR}\n" + \
#                       f"{body}\n" + \
#                       f"{cls.CONTENT_SEPERATOR}\n" + \
#                       f"```"
#             return content, 0, (cls.total_item_count - 1) // 10
#         return callback


