from typing import Any, Literal
import aiohttp
from io import BytesIO
from difflib import (
    SequenceMatcher
)
import discord
from discord import (Interaction)
import discord.utils



def acstr(string: str | Any, length: int, just: Literal["l", "r", "m"]="l", edges: tuple[str, str]=('','')):
    """String alignment and cropping
    string: The string in questions
    length: The max length of the string
    just: The justification, [l]eft, [r]ight, [m]iddle
    """
    if not isinstance(string, str):
        string = str(string)

    # if len(edges[0]):
    #     length -= 1
    # if len(edges[1]):
    #     length -= 1
        
    cont = "..."
    match just:
        case "l":
            string = edges[0] + string + edges[1]
            string = string.ljust(length)
        case "r":
            string = edges[0] + string + edges[1]
            string = string.rjust(length)
        case "m":
            string = edges[0] + string + edges[1]
            string = string.center(length)
    if len(string) > length:
        right = length - len(cont)
        if len(edges[1]):
            right -= 1
        string = string[:right] + cont + edges[1]
    return string

def clamp(num, min_value, max_value):
    num = max(min(num, max_value), min_value)
    return num


def secondsDivMod(seconds: int) -> (int, int, int):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return hours, minutes, seconds


def secondsToTime(t):
    hours, minutes, seconds = secondsDivMod(t)
    value = f"{f'{hours:02}' + ':' if hours > 0 else ''}{minutes:02}:{seconds:02}"
    return value


async def link_to_bytes(link: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as r:
            data = await r.read()
    return data


async def link_to_attachment(link: str, file_name: str) -> discord.File:
    file_extension = '.'.join(link.split('?')[0].split('/')[-1].split(".")[1:])
    file = discord.File(
        fp=BytesIO(await link_to_bytes(link)),
        filename=f"{file_name}.{file_extension}")
    return file



def find_closely_matching_dict_keys(search: str, data: dict, n, cutoff=0.45):
    input_list = data.items()
    matches = list()
    for key, value in input_list:
        if len(matches) > n:
            break
        if SequenceMatcher(None, search, key).ratio() >= cutoff:
            matches.append([key, value])
    return dict(matches)

def find_closely_matching_list_elems(search: str, data: list[str], n, cutoff=0.45) -> list[str]:
    matches = []
    for item in data:
        if len(matches) > n:
            break
        if SequenceMatcher(None, search, item).ratio() >= cutoff:
            matches.append(item)
    return matches

def similaritySort(data: list, key):
    ratio_data = [
        (SequenceMatcher(None, key.lower(), item.lower()).ratio(), item)
        for item in data
    ]
    ratio_data.sort(reverse=True)
    ratios, values = list(zip(*ratio_data))
    return values




# title at top
# page data: 1...10
# page number: #: pg/total

# Pass custom function for handling lines per page
# rest is generic


class ClampedValue:
    def __init__(self, value: int | float, min_value, max_value):
        self._value = value
        # self.type = type(value)
        self.min_value = min_value
        self.max_value = max_value

    def __get__(self, obj, obj_type=None):
        self._value = max(min(self._value, self.max_value), self.min_value)
        print(self._value)
        return self._value

    def __set__(self, obj, value: int | float):
        self._value = max(min(value, self.max_value), self.min_value)
        print(self._value)

    def __add__(self, value: int | float):
        self._value = self._value + value

    def __sub__(self, value: int | float):
        self._value = self._value - value

    def __mul__(self, multiplier: int | float):
        self._value = self._value * multiplier

    def __truediv__(self, dividend: int | float):
        self._value = self._value / dividend

    def __floordiv__(self, dividend: int | float):
        self._value = self._value // dividend

    def __int__(self):
        return int(self._value)

    def __float__(self):
        return float(self._value)



