from math import ceil
from discord import(Interaction)
from bot.ext.types import InfoTextElem, InfoSeparators, ITL, MessageInfo, EdgeIndices, CustomRepr, PageGenCallbacks, \
    PageBehavior
from bot.ext.ui.views import PageScroller
from bot.ext.smart_functions import respond
from bot.kagami import  Kagami
from bot.utils.music_utils import trackListData, WavelinkTrack
from bot.utils.utils import secondsToTime, createPages, secondsDivMod


async def respondWithTracks(bot:Kagami, interaction: Interaction, tracks: list[WavelinkTrack, ], followup=False, timeout=60):
    data, duration = trackListData(tracks)
    track_count = len(tracks)
    # Message information
    if followup:
        og_response = await interaction.followup.send(content="...")
    else:
        og_response = await interaction.original_response()
    if track_count > 1:
        info_text = InfoTextElem(text=f"{track_count} tracks with a duration of {secondsToTime(duration // 1000)} were added to the queue",
                                 separators=InfoSeparators(bottom="────────────────────────────────────────"),
                                 loc=ITL.TOP)

        message_info = MessageInfo(og_response.id,
                                   og_response.channel.id)

        # New Shit
        def pageGen(interaction: Interaction, page_index: int) -> str:
            return "No Content"

        page_count = ceil(track_count / 10)

        left_edge = 0
        home_index = 0

        def edgeIndices(interaction: Interaction) -> EdgeIndices:
            return EdgeIndices(left=left_edge,
                               right=page_count-1)


        pages = createPages(data=data,
                            info_text=info_text,
                            max_pages=page_count,
                            sort_items=False,
                            custom_reprs={
                                "duration": CustomRepr("", "")
                            },
                            zero_index=home_index,
                            page_behavior=PageBehavior(max_key_length=50))

        page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)

        view = PageScroller(bot=bot,
                            message_info=message_info,
                            page_callbacks=page_callbacks,
                            pages=pages,
                            timeout=timeout)

        home_text = pages[abs(left_edge) + home_index]
        # Let it have arbitary home pages that aren't just the first page

        await og_response.edit(content=home_text, view=view)
    else:
        hours, minutes, seconds = secondsDivMod(tracks[0].duration//1000)
        await og_response.edit(
            content=f"`{tracks[0].title}  -  {f'{hours}:02' + ':' if hours > 0 else ''}{minutes:02}:{seconds:02} was added to the queue`")

