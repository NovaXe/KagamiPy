from contextvars import ContextVar
from typing import TypeVar, Generic

from bot.utils.bot_data import ServerData

T = TypeVar("T")


class CVar(Generic[T]):
    def __init__(self, name: str, default=...):
        self.var: ContextVar[T] = ContextVar(name, default=default)

    def __get__(self)->T:
        return self.var.get()

    def __set__(self, value: T):
        self.var.set(value)


server_data: ServerData = CVar[ServerData]('server_data', default=ServerData)

