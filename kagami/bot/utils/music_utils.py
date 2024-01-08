from math import(ceil)

from discord import (Interaction, InteractionType, app_commands, VoiceChannel)

import wavelink
from enum import (Enum, auto)

from bot.ext import errors

from bot.ext.ui.custom_view import MessageInfo
from bot.ext.ui.page_scroller import ITL, PageGenCallbacks, PageScroller
from bot.kagami_bot import Kagami
from bot.utils.player import Player
from bot.utils.wavelink_utils import WavelinkTrack, searchForTracks
from bot.utils.utils import (secondsToTime, secondsDivMod)
from bot.utils.pages import createSinglePage, CustomRepr, PageBehavior, PageIndices, InfoSeparators, InfoTextElem, \
    EdgeIndices, createPages, getQueueEdgeIndices
# from bot.ext.ui import (PageScroller)
from bot.utils.interactions import respond
from bot.utils.wavelink_utils import createNowPlayingMessage, trackListData, getPageTracks
from bot.utils.bot_data import *

class TrackType(Enum):
    YOUTUBE = auto()
    SPOTIFY = auto()
    SOUNDCLOUD = auto()


async def attemptHaltResume(interaction: Interaction, send_response=False, before_queue_length=0):
    """
    :param interaction: the discord command interaction
    :param send_response: whether to respond to the interaction or not
    :param before_queue_length: only input if you have put new track
    :return:
    """

    voice_client: Player = interaction.guild.voice_client
    # before_queue_length = voice_client.queue.count

    response = "default response"
    if voice_client.halted:
        if voice_client.queue.history.count:
            if voice_client.halted_queue_count==0 and voice_client.queue.count > 0:
                await voice_client.cyclePlayNext()
            else:
                await voice_client.beginPlayback()
        else:
            await voice_client.cyclePlayNext()
        await voice_client.resume()
        response = "Let the playa be playin"
    else:
        response = "The playa be playin"
    if send_response: await respond(interaction, f"`{response}`", delete_after=3)


async def buildTracks(tracks: list[str]):
    _data = {}
    _duration = 0
    for _track_id in tracks:
        _full_track = await wavelink.NodePool.get_node().build_track(cls=wavelink.GenericTrack, encoded=_track_id)
        track_duration = int(_full_track.duration // 1000)
        _duration += track_duration
        _data.update({_full_track.title: {"duration": secondsToTime(track_duration)}})
    return _data, _duration


def createNowPlayingWithDescriptor(voice_client: Player, formatting=True, position: int=False):
    track, pos = voice_client.currentlyPlaying()
    descriptor_text = ""

    if voice_client.halted:
        descriptor_text = "HALTED"
        if track is None:
            if voice_client.queue.history.count:
                track = voice_client.queue.history[-1]
    else:
        descriptor_text = "NOW PLAYING"
    if voice_client.is_paused():
        descriptor_text = "PAUSED"

    if not position:
        pos = None

    message = createNowPlayingMessage(track, position=pos, formatting=formatting, descriptor_text=descriptor_text)
    return message


def createQueuePage(voice_client: Player, page_index: int) -> str:
    """
    :param voice_client:
    :param page_index: history < 0 < upnext
    :return:
    """



    """
    page indices
    pg -1 : queue.history[6:16]
    offset = 6
    queue.history[offset:offset+10]
    
    
    central: 
    history: queue.history[1:6]
    selected: queue.history[0]
    upnext: queue[0:5]
    
    pg 1
    """

    queue: wavelink.Queue = voice_client.queue


    tracks = getPageTracks(queue, page_index)
    track_count = len(tracks)

    h_len = max(len(queue.history) - 1, 0)
    mid_index = min(5, h_len)
    # if page_index == 0:
    #     mid_index = h_len - 1

    data = {}
    for track in tracks:
        data.update({
            track.title: {
                "duration": secondsToTime(track.duration//1000)

            }
        })

    """
          🡅Previous🡅
──────────────────────────
    """
    i_spacing = 6

    """
    first_index
    10 tracks per page
    5 tracks on page 0
    
    
    """
    iloc: ITL
    first_index: int
    if page_index < 0:
        iloc = ITL.BOTTOM
        # end = abs(page_index)*10 + 6
        # first_index = (page_index * 10) - 5 + (10 - track_count) + 1
        first_index = (page_index*10) - 5 + (10 - track_count)
    elif page_index == 0:
        iloc = ITL.MIDDLE

        first_index = -mid_index
    else:
        iloc = ITL.TOP
        first_index = ((page_index-1) * 10) + 6

    left, right = getQueueEdgeIndices(queue)

    top_text = f"{' '*i_spacing}{'🡅Previous🡅'}\n" \
               f"──────────────────────────"

    bottom_text = f"──────────────────────────\n" \
                  f"{' '*i_spacing}{'🡇Up Next🡇'.ljust(i_spacing)}"

    ignored_indices = None
    if page_index ==0:
        ignored_indices=[mid_index]
        if h_len == 0:
            top_text = None
        if len(queue) == 0:
            bottom_text = None


    track, pos = voice_client.currentlyPlaying()



    now_playing_message = createNowPlayingWithDescriptor(voice_client, False, False)




    info_text = InfoTextElem(text=now_playing_message,
                             separators=InfoSeparators(
                                 top=top_text,
                                 bottom=bottom_text),
                             loc=iloc,
                             mid_index=mid_index)

    page_behavior = PageBehavior(elem_count=track_count,
                                 max_key_length=45,
                                 ignored_indices=ignored_indices,
                                 index_spacing=i_spacing)

    page = createSinglePage(data,
                            behavior=page_behavior,
                            infotext=info_text,
                            custom_reprs={"duration": CustomRepr("", "")},
                            first_item_index=first_index,
                            page_position=PageIndices(left, page_index, right))

    return page
    #
    # if tracks is None:
    #     page = "Nothing Here"
    # else:
    #     page = '\n'.join([track.title for track in tracks])
    # return f"{page}\n page {page_index}"




"""
queue controller
attributes:
message id
channel id

generate page on button click
cache generated pages
mark page for regen if something has changed
list[page, need_regen]
list[str, bool]

upgrade old message scroller and player controls to utilize new dynamic shit

"""

def addedToQueueMessage(track_count: int, duration: int):
    return f"{track_count} tracks with a duration of {secondsToTime(duration // 1000)} were added to the queue"

async def respondWithTracks(bot: Kagami, interaction: Interaction,
                            tracks: list[Track] | list[WavelinkTrack],
                            info_text: str=None, send_followup=False, timeout=60):
    send_followup = (interaction.type is not InteractionType.application_command) or send_followup
    track_count = len(tracks)
    data, duration = trackListData(tracks)

    if track_count > 1:
        if info_text is None: info_text = f"{track_count} tracks with a duration of {secondsToTime(duration // 1000)}"

        info_text_elem = InfoTextElem(text=info_text,
                                      separators=InfoSeparators(bottom="────────────────────────────────────────"),
                                      loc=ITL.TOP)




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
                            info_text=info_text_elem,
                            max_pages=page_count,
                            sort_items=False,
                            custom_reprs={
                                "duration": CustomRepr("", "")
                            },
                            first_item_index=1,
                            page_behavior=PageBehavior(max_key_length=50))

        page_callbacks = PageGenCallbacks(genPage=pageGen, getEdgeIndices=edgeIndices)

        view = PageScroller(bot=bot,
                            message_info=MessageInfo(),
                            page_callbacks=page_callbacks,
                            pages=pages,
                            timeout=timeout)

        home_text = pages[abs(left_edge) + home_index]
        # Let it have arbitary home pages that aren't just the first page

        message = await respond(interaction, content=home_text, view=view, send_followup=send_followup)
        view.setMessageInfo(MessageInfo.init_from_message(message))

    else:
        hours, minutes, seconds = secondsDivMod(tracks[0].duration//1000)
        message = await respond(
            interaction,
            content=f"`{tracks[0].title}  -  {f'{hours}:02' + ':' if hours > 0 else ''}"
                    f"{minutes:02}:{seconds:02} was added to the queue`",
            send_followup=send_followup,
            delete_after=5
        )


def requireVoiceclient(begin_session=False, defer_response=True, ephemeral=False):
    async def predicate(interaction: Interaction):
        if defer_response: await respond(interaction, ephemeral=ephemeral)
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            if begin_session:
                await attemptToJoin(interaction, send_response=False, ephemeral=ephemeral)
                return True
            else:
                raise errors.NoVoiceClient
        else:
            return True

    return app_commands.check(predicate)


async def attemptToJoin(interaction: Interaction, voice_channel: VoiceChannel = None, send_response=True, ephemeral=False):
    voice_client: Player = interaction.guild.voice_client
    user_vc = user_voice.channel if (user_voice := interaction.user.voice) else None
    voice_channel = voice_channel or user_vc
    if not voice_channel: raise errors.NoVoiceChannel

    if voice_client and voice_client.channel == voice_channel:
        raise errors.AlreadyInVC("I'm already in the voice channel")

    if voice_client:
        pass
    # raise errors.AlreadyInVC

    else:
        if send_response: await respond(interaction, "Joining...", ephemeral=ephemeral, delete_after=0.5)
        voice_client = await joinVoice(interaction, voice_channel)
    return voice_client


async def joinVoice(interaction: Interaction, voice_channel: VoiceChannel):
    voice_client: Player = interaction.guild.voice_client
    if voice_client:
        await voice_client.move_to(voice_channel)
        voice_client = interaction.guild.voice_client
    else:
        voice_client = await voice_channel.connect(cls=Player())
    return voice_client


async def searchAndQueue(voice_client: Player, search):
    tracks, source = await searchForTracks(search, 1)
    await voice_client.waitAddToQueue(tracks)
    return tracks, source
