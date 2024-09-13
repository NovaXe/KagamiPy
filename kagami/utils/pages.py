import itertools
from collections import namedtuple
from dataclasses import dataclass
from math import ceil
from typing import Literal

import wavelink

from discord import Interaction

from ui.custom_view import MessageInfo
from ui.page_scroller import ITL, PageScroller, PageGenCallbacks
from bot import Kagami

PageIndexBounds = namedtuple("IndexBounds", "start end")


@dataclass
class InfoSeparators:
    top: str=None
    bottom: str=None


@dataclass
class PageBehavior:
    # page_index:int
    # infotext_loc: ITL = ITL.TOP
    elem_count: int=10
    max_key_length: int=20
    ignored_indices: list[int]=None
    index_spacing:int = 6


@dataclass
class InfoTextElem:
    text: str
    separators: InfoSeparators
    loc: ITL
    mid_index: int=None


@dataclass
class PageVariations:
    max_key_length: int = 20
    sort_items: bool = True
    info_text_loc: ITL = ITL.TOP
    start_index: int = 0
    ignored_indices: list[int] = None


@dataclass
class PageIndices:
    first: int
    current: int
    last: int

EdgeIndices = namedtuple('EdgeIndices', 'left right')


@dataclass
class CustomRepr:
    alias: str = ""
    delim: str = ":"
    ignored: bool = False


def simplePageScroller(bot: Kagami, data: dict, info_text: str, message_info: MessageInfo, custom_reprs=None):
    element_count = len(data)
    page_count = ceil(element_count / 10)

    def pageGen(interaction: Interaction, page_index: int) -> str:
        return "No Content"

    def edgeIndices(interaction: Interaction) -> EdgeIndices:
        return EdgeIndices(left=0,
                           right=page_count - 1)

    pages = createPages(data=data,
                        info_text=InfoTextElem(
                            text=info_text,
                            separators=InfoSeparators(bottom="────────────────────────────────────────"),
                            loc=ITL.TOP),
                        max_pages=page_count,
                        custom_reprs=custom_reprs,
                        first_item_index=1,
                        page_behavior=PageBehavior(max_key_length=50))

    page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)

    view = PageScroller(bot=bot,
                        message_info=message_info,
                        page_callbacks=page_callbacks,
                        pages=pages,
                        timeout=120)
    home_text = pages[0]

    return home_text, view






def createPageList(info_text: str,
                   data: dict | list,
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

    item_count = 0
    page_index = 0
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



def createPages(data: dict | list,
                info_text: InfoTextElem=None,
                max_pages: int=1,
                max_elems: int=None,
                sort_items: bool=True,
                custom_reprs: dict[str, CustomRepr]=None,
                first_item_index: int=0,
                page_behavior: dict[int, PageBehavior] | PageBehavior=PageBehavior,
                starting_index: int=0):

    if isinstance(data, list) and sort_items:
        data = sorted(data)

    ending_index = starting_index + max_pages - 1
    pages = [""] * max_pages
    page_interator = enumerate(range(starting_index, ending_index+1))
    slice_start = 0
    for loop_index, page_index in page_interator:
        if isinstance(page_behavior, dict) and page_index in page_behavior:
            pb = page_behavior[page_index]
        else:
            pb = page_behavior

        page_max_elems = pb.elem_count


        # page_data = data[page_first_elem: page_first_elem + page_max_elems]
        # page_data = dict(data.items()[page_first_elem: page_first_elem + page_max_elems])
        page_data = dict(itertools.islice(data.items(), slice_start, slice_start + page_max_elems))
        # page_data = {{} for index, (key, value) in enumerate(data.items()) if index < page_max_elems}

        pages[page_index] = createSinglePage(page_data,
                                             behavior=pb,
                                             infotext=info_text,
                                             custom_reprs=custom_reprs,
                                             first_item_index=first_item_index+slice_start,
                                             page_position=PageIndices(starting_index, page_index, ending_index))
        slice_start += page_max_elems
    return pages


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
                line += "," + rep
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
                   f"{infotext.separators.bottom}\n" \
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
            if infotext.separators.top:
                sep_top = f"{infotext.separators.top}\n"
            else:
                sep_top = ""

            if infotext.separators.bottom:
                sep_bottom = f"{infotext.separators.bottom}\n"
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
                   f"{infotext.separators.top}\n" \
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


def keyShortener(k: str, max_key_length):
    if len(k) > max_key_length:
        cutoff = " ..."
        k = k[:max_key_length - len(cutoff)] + cutoff
    return k.ljust(max_key_length)


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


def getQueueEdgeIndices(queue: wavelink.Queue):
    history_page_count = 0
    upnext_page_count = 0
    if (h_len := len(queue.history) - 6) > 0:
        history_page_count = ceil(h_len / 10)
    if (u_len := len(queue) - 5) > 0:
        upnext_page_count = ceil(u_len / 10)

    return EdgeIndices(-1*history_page_count, upnext_page_count)
