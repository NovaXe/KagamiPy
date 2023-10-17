from dataclasses import dataclass
from collections import namedtuple
from typing import (Callable)

@dataclass
class MessageInfo:
    id: int
    channel_id: int
    # guild_id: int

@dataclass
class StopBehavior:
    disable_items: bool = False
    remove_view: bool = False

@dataclass
class PageGenCallbacks:
    genPage: Callable
    getEdgeIndices: Callable

@dataclass
class CustomRepr:
    alias: str = ""
    delim: str = ":"
    ignored: bool = False

@dataclass
class PagePayload:
    interaction = None
    voice_client = None



EdgeIndices = namedtuple('EdgeIndices', 'left right')
