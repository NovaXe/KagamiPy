import aiohttp
from io import BytesIO
from dataclasses import dataclass
from difflib import (
    get_close_matches,
    SequenceMatcher
)
from typing import (
    Literal,
    Union,
    NamedTuple
)
from collections import namedtuple
from enum import (Enum, auto)
import discord
from discord import (Interaction)
import discord.utils
from discord.ext import commands
from discord import app_commands

async def respond(interaction: Interaction, message: str=None):
    if message:
        try:
            await interaction.response.send_message(content=message)
        except discord.InteractionResponded:
            await interaction.edit_original_response(content=message)
    else:
        try:
            await interaction.response.defer()
        except discord.InteractionResponded:
            pass



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


class Position(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

    TOP = auto()
    MIDDLE = auto()
    BOTTOM = auto()

    START = auto()
    END = auto()


# Info Text Location
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
class InfoSeperators:
    top: str=None
    bottom: str=None

@dataclass
class InfoTextElem:
    text: str
    seperators: InfoSeperators
    loc: ITL
    mid_index: int=None


PageIndexBounds = namedtuple("IndexBounds", "start end")



page_behavior: dict[int, PageBehavior]


def keyShortener(k: str, max_key_length):
    if len(k) > max_key_length:
        cutoff = " ..."
        k = k[:max_key_length - len(cutoff)] + cutoff
    return k.ljust(max_key_length)

def getPageProgress(start_index, current_index, last_index):
    """example
    Page #: 7/11
    [ -4 ] • • • ○ • ( 2 ) • • • [ 6 ]
    """
    page_count = abs(last_index) + abs(start_index) + 1
    page_index = current_index-start_index
    markers = []


    s = f"Page #: {current_index - start_index+1} / {page_count}\n"
    markers += ["•"] * (abs(start_index))
    markers += ['○']
    markers += ["•"] * (abs(last_index))
    markers[0] = f"[ {start_index} ]"
    markers[-1] = f"[ {last_index} ]"
    markers[page_index] = f"( {current_index} )"
    s += ' '.join(markers)

    return s



def createSinglePage(data: [dict, list],
                     behavior: PageBehavior = PageBehavior,
                     infotext: InfoTextElem=None,
                     custom_reprs: dict[str, CustomRepr]=None,
                     first_item_index=1,
                     page_position: PageIndices=None):
    # Local Variables for ease of use
    max_elems = behavior.elem_count
    # if max_elems is None:
    #     max_elems = len(data)

    max_key_length = behavior.max_key_length
    index_label_spacing = behavior.index_spacing
    ignored_indices = behavior.ignored_indices

    lines = []
    index_offset = 0
    for index, (key, key_value) in enumerate(data.items()):
        line: str = ""
        absolute_index = index + first_item_index

        if index == max_elems:
            break

        if ignored_indices and index in ignored_indices:
            index_offset +=1
        #     This shit does not behave as expected
        # Should offset all values but all other values don't care about it and it only affeacts the page in question
        # Only useful for skipping over the stupid 0 index that I can't get rid of on the first page
        # May have been a better idea to just allow custom handlers than make some perfectly generic shit cause this sucks



        line_number_str = f"{abs(absolute_index+index_offset)})".ljust(index_label_spacing)
        key_short = keyShortener(key, max_key_length)
        line = f"{line_number_str}{key_short} -"


        # Sub key iteraction
        for subkey_index, (subkey, sub_value) in enumerate(key_value.items()):
            if custom_reprs and subkey in custom_reprs:
                custom_repr = custom_reprs[subkey]
                alias = custom_repr.alias
                delim = custom_repr.delim
                ignored = custom_repr.ignored
                if ignored:
                    continue
                rep = f"  {alias}{delim} {sub_value}"
            else:
                rep = f"  {subkey}: {sub_value}"
            # Adds seperators between subkey values
            if subkey_index != 0:
                line += ";" + rep
            else:
                line += rep
            # Places line into list of lines
            lines.append(line)

    if page_position:
        page_progress = getPageProgress(page_position.first,
                                        page_position.current,
                                        page_position.last)
    else:
        page_progress = f"Page #: ?/?\n" \
                        f"[ -? ] ••• ( ? ) ••• [ ? ]"

    page = "No Page Here"
    # ────────────────────────────────────────
    # Yes infotext element
    if infotext:
        loc = infotext.loc
        if loc == ITL.TOP:
            page_text = "\n".join(lines)
            page = f"```swift\n" \
                   f"{infotext.text}\n" \
                   f"{infotext.seperators.bottom}\n" \
                   f"{page_text}\n" \
                   f"{page_progress}\n" \
                   f"```"
        elif loc == ITL.MIDDLE:
            middle = infotext.mid_index
            first_half = '\n'.join(lines[:middle])
            second_half = '\n'.join(lines[middle:])
            if len(second_half):
                second_half += "\n"
            if len(first_half):
                first_half += "\n"
            if infotext.seperators.top:
                sep_top = f"{infotext.seperators.top}\n"
            else:
                sep_top = ""

            if infotext.seperators.bottom:
                sep_bottom = f"{infotext.seperators.bottom}\n"
            else:
                sep_bottom = ""



            page = f"```swift\n" \
                   f"{first_half}" \
                   f"{sep_top}" \
                   f"{infotext.text}\n" \
                   f"{sep_bottom}" \
                   f"{second_half}" \
                   f"{page_progress}" \
                   f"```"
        elif loc == ITL.BOTTOM:
            page_text = "\n".join(lines)
            page = f"```swift\n" \
                   f"{page_text}\n" \
                   f"{infotext.seperators.top}\n" \
                   f"{infotext.text}\n" \
                   f"{page_progress}\n" \
                   f"```"
        else:
            raise ValueError("Incorrect enum value for ITL")
    # No infotext Passed
    else:
        page_text = "\n".join(lines)
        page = f"```swift" \
               f"{page_text}\n" \
               f"{page_progress}" \
               f"```"



    return page








def createPages(data: [dict, list],
                info_text: InfoTextElem=None,
                max_pages: int=None,
                max_elems: int=None,
                sort_items: bool=True,
                custom_reprs: dict[str, CustomRepr]=None,
                zero_index: int=None,
                zero_offset: int=0,
                page_behavior: dict[int, PageBehavior]=None,
                starting_index: int=0):

    if sort_items:
        data = sorted(data)


    ending_index = starting_index + (max_pages-1)
    pages = [""] * max_pages
    page_interator = enumerate(zip(pages, range(starting_index, ending_index)))
    page_first_elem = 0
    for loop_index, (page, page_index) in page_interator:
        pb = page_behavior[page_index]
        page_max_elems = pb.elem_count

        page_data = data[page_first_elem: page_first_elem + page_max_elems]
        page = createSinglePage(page_data,
                                behavior=pb,
                                infotext=info_text,
                                custom_reprs=custom_reprs,
                                first_item_index=page_first_elem,
                                page_position=PageIndices(starting_index, page_index, ending_index))
        page_first_elem += page_max_elems
    return pages









def createPageList(info_text: str,
                   data: [dict, list],
                   total_item_count: int,
                   custom_reprs: dict[str, CustomRepr] = None,
                   max_key_length:int=20,
                   leftside_spacing:int=6,
                   sort_items=True):
    key: str
    values: dict

    # TODO Info text location top/bottom
    # TODO Numbering position, start numbering at arbitrarying index
    # TODO IE starting at index 4 would result in 4 3 2 1 0 1 2 3 4 5 cascading down
    # TODO Hide index in custom repr
    # TODO custom item count
    # TODO ignore elem entirely in custom repr


    pages = [""]
    full_page_count, last_page_item_count = divmod(total_item_count, 10)
    page_count = full_page_count + (1 if last_page_item_count else 0)
    leftside_spacing = 6

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

    page = ""

    if sort_items:
        items = sorted(data.items())
    else:
        items = data.items()

    lines = []
    page_index = 0
    item_count = 0
    for key, key_value in items:

        item_count += 1
        line_number_str = f"{item_count})".ljust(leftside_spacing)

        key_short = keyShortener(key)
        line = f"{line_number_str}{key_short} -"

        # Sub key iteration
        for index, (sub_key, sub_value) in enumerate(key_value.items()):

            if custom_reprs and sub_key in custom_reprs:
                custom_repr = custom_reprs[sub_key]

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
        lines.append(line)
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



