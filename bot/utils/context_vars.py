from contextvars import ContextVar
from typing import TypeVar, Generic

from bot.utils.bot_data import ServerData
from bot.kagami import Kagami
T = TypeVar("T")


class CVar(Generic[T]):
    def __init__(self, name: str, default=...):
        self.var: ContextVar[T] = ContextVar(name, default=default)

    @property
    def value(self)->T:
        return self.var.get()

    @value.setter
    def value(self, value: T):
        self.var.set(value)




server_data = CVar[ServerData]('server_data', default=ServerData())
bot_var = CVar[Kagami]('kagami')

# _server_data = ContextVar('server_data', default=ServerData)
# @property
# def server_data():
#     return _server_data.get()
#
# @server_data.setter
# def server_data(value: ServerData):
#     _server_data.set(value)
