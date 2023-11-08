from dataclasses import dataclass
from collections import namedtuple
from typing import (Callable)
from enum import Enum, auto

@dataclass
class MessageInfo:
    id: int
    channel_id: int
    # guild_id: int

@dataclass
class StopBehavior:
    disable_items: bool = False
    remove_view: bool = False
    delete_message: bool = False

@dataclass
class PageGenCallbacks:
    genPage: Callable
    getEdgeIndices: Callable

@dataclass
class CustomRepr:
    alias: str = ""
    delim: str = ":"
    ignored: bool = False

class ITL(Enum):
    """
    Info Text Location Enum\n
    Values:
    TOP, MIDDLE, BOTTOM
    """
    TOP = auto()
    MIDDLE = auto()
    BOTTOM = auto()


@dataclass
class PageVariations:
    max_key_length: int = 20
    sort_items: bool = True
    info_text_loc: ITL = ITL.TOP
    start_index: int = 0
    ignored_indices: list[int] = None

@dataclass
class PageBehavior:
    # page_index:int
    # infotext_loc: ITL = ITL.TOP
    elem_count: int=10
    max_key_length: int=20
    ignored_indices: list[int]=None
    index_spacing:int = 6

@dataclass
class PageIndices:
    first: int
    current: int
    last: int

@dataclass
class InfoSeparators:
    top: str=None
    bottom: str=None

@dataclass
class InfoTextElem:
    text: str
    separators: InfoSeparators
    loc: ITL
    mid_index: int=None

EdgeIndices = namedtuple('EdgeIndices', 'left right')
