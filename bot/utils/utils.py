import aiohttp
from io import BytesIO
from dataclasses import dataclass
from difflib import (
    get_close_matches,
    SequenceMatcher
)
from typing import (
    Literal,
    Union
)
import discord
import discord.utils
from discord.ext import commands
from discord import app_commands
from bot.kagami import Kagami



def clamp(num, min_value, max_value):
    num = max(min(num, max_value), min_value)
    return num


def seconds_to_time(seconds: int) -> (int, int, int):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return hours, minutes, seconds


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



def find_closely_matching_dict_keys(search: str, tags: dict, n, cutoff=0.45):
    input_list = tags.items()
    matches = list()
    for key, value in input_list:
        if len(matches) > n:
            break
        if SequenceMatcher(None, search, key).ratio() >= cutoff:
            matches.append([key, value])
    return dict(matches)


# title at top
# page data: 1...10
# page number: #: pg/total

# Pass custom function for handling lines per page
# rest is generic

def createPageInfoText(total_item_count, scope: str, source: Literal['search', 'data'],
                       data_type: Literal['clean_sentinels', 'tags']):
    # if type(scope) is not Enum:
    #     raise TypeError("Parameter scope is not of type Enum")
    # if type(source) is not Enum:
    #     raise TypeError("Parameter source is not of type Enum")

    scope_repr1 = 'Kagami' if scope == 'global' else scope
    scope_repr2 = ' global' if scope == 'global' else ''
    scope_repr3 = f'on {scope}' if scope != 'global' else ''

    if source == 'search':
        info_text = f"Found {total_item_count}{scope_repr2} {data_type} that are similar to your search {scope_repr3}"
    else:
        info_text = f"{scope_repr1} has {total_item_count}{scope_repr2} {data_type} registered"

    return info_text


@dataclass
class CustomRepr:
    alias: str = ""
    delim: str = ":"
    ignored: bool = False


def createPageList(info_text: str, data: [dict, list], total_item_count: int, custom_reprs: dict[str, CustomRepr] = None, max_key_length=20):
    key: str
    values: dict

    pages = [""]
    full_page_count, last_page_item_count = divmod(total_item_count, 10)
    page_count = full_page_count + (1 if last_page_item_count else 0)


    if page_count == 0:
        pages[0] = (
            "```swift\n" +
            info_text +
            "\n```"
        )
        return pages
    else:
        pages *= page_count


    def keyShortener(s: str):
        if len(key) <= max_key_length:
            s = key.ljust(max_key_length)
        else:
            s = (key[:max_key_length-4] + " ...").ljust(max_key_length)
        return s

    item_count = 0
    page_index = 0
    page = ""
    for key, key_value in (items := sorted(data.items())):

        item_count += 1
        line_number_str = f"{item_count})".ljust(4)

        key_short = keyShortener(key)
        line = f"{line_number_str}{key_short} -"

        for sub_key, sub_value in key_value.items():

            if custom_reprs and (custom_repr := custom_reprs[sub_key]):

                alias = custom_repr.alias
                delim = custom_repr.delim
                ignored = custom_repr.ignored
                if ignored:
                    continue

                rep = f"  {alias}{delim} {sub_value}"
            else:
                rep = f"  {sub_key}: {sub_value}"



            line += rep
        line += "\n"
        page += line

        if not item_count % 10 or item_count == total_item_count:
            page_ratio = f"Page #: {page_index + 1} / {page_count}"
            pages[page_index] = f"```swift\n" \
                                f"{info_text}\n" \
                                f"────────────────────────────────────────\n" \
                                f"{page}" \
                                f"{page_ratio}\n" \
                                f"```"
            page_index += 1
            page = ""
    return pages



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



