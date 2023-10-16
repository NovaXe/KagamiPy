from dataclasses import dataclass
from collections import namedtuple
from typing import (Callable)

@dataclass()
class MessageInfo:
    id: int
    channel_id: int
    # guild_id: int

@dataclass()
class StopBehavior:
    disable_items: bool = False
    remove_view: bool = False

@dataclass()
class PageGenCallbacks:
    genPage: Callable
    getEdgeIndices: Callable


EdgeIndices = namedtuple('EdgeIndices', 'left right')
