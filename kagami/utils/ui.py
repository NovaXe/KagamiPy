import discord.utils
from common.utils import clamp
from typing import Optional

from helpers.depr_music_helpers import *
from common.interactions import respond
from discord.ext import tasks




class CustomUIView(discord.ui.View):
    def __init__(self, *, timeout: Optional[float] = 180.0, **kwargs):
        super().__init__(timeout=timeout)
        self.message = kwargs.get("message", None)
        # self.deletes_message = kwargs.get("deletes_message")


    async def stopHandler(self):
        if self.message:
            await self.message.edit(view=None)

    async def stop(self):
        await self.stopHandler()
        super().stop()



    async def on_timeout(self) -> None:
        await self.stop()

    async def delete_message(self):
        await self.message.delete()





class PlayerControls(CustomUIView):
    def __init__(self, *args, player, message, **kwargs):
        kwargs.update({
            "player": player,
            "message": message,
        })
        super().__init__(**kwargs)
        self.player: OldPlayer = player
        self.message = message

    async def update_player_buttons(self):
        for item in self.children:
            assert isinstance(item, discord.ui.Button)

            if item.custom_id == "PlayerControls:pauseplay":
                if self.player.is_paused():
                    item.emoji = "▶"
                else:
                    item.emoji = "⏸"

        await self.message.edit(view=self)









    @discord.ui.button(emoji="⏮", style=discord.ButtonStyle.green, custom_id="PlayerControls:skipback")
    async def skip_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        if self.player.current_track is None:
            for i in range(self.player.skip_count):
                await self.player.cycle_track(reverse=True)
                print("skipped track\n")
            await self.player.start_current_track()
            return

        self.player.skip_to_prev = True
        await self.player.stop()

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.green, custom_id="PlayerControls:stop")
    async def stop_playback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()

        self.player.is_stopped = True
        if not self.player.is_paused():
            await self.player.pause()

        await self.player.seek(0)

        await self.update_player_buttons()

    @discord.ui.button(emoji="⏯", style=discord.ButtonStyle.green, custom_id="PlayerControls:pauseplay")
    async def pause_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        if self.player.current_track is None:
            await self.player.play_next_track()

        if self.player.is_paused():
            await self.player.resume()
        else:
            await self.player.pause()

        await self.update_player_buttons()

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.green, custom_id="PlayerControls:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        if self.player.current_track is None:
            for i in range(self.player.skip_count):
                await self.player.cycle_track(reverse=False)
                print("skipped track\n")
            await self.player.start_current_track()
            return
        await self.player.stop()


    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.gray, custom_id="PlayerControls:loop")
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        self.player.loop_mode = self.player.loop_mode.next()
        match self.player.loop_mode:
            case LoopMode.NO_LOOP:
                button.emoji = "🔁"
                button.style = discord.ButtonStyle.gray
            case LoopMode.LOOP_QUEUE:
                button.emoji = "🔁"
                button.style = discord.ButtonStyle.blurple
            case LoopMode.LOOP_SONG:
                button.emoji = "🔂"
                button.style = discord.ButtonStyle.blurple
        await self.message.edit(view=self)



class DeleteMessageButton(discord.ui.Button):
    def __init__(self, deletes_message=False):
        super().__init__(style=discord.ButtonStyle.red, emoji="🗑", row=4)
        self._view: Optional[CustomUIView] = None
        self.deletes_message = deletes_message


    @property
    def view(self)->Optional[CustomUIView]:
        return self._view

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        assert isinstance(self.view, CustomUIView)
        await self.view.stop()
        if self.deletes_message:
            await self.view.delete_message()



# class ViewDeleteButton(CustomUIView):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#
#     @discord.ui.button(emoji="🗑", style=discord.ButtonStyle.red, custom_id="Button:deleteview")
#     async def delete_view(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if button.view:
#             await button.view.on_timeout()
#
#         await self.on_timeout()

class MessageScroller(CustomUIView):
    def __init__(self, *args, message: discord.Message, pages: list[str], home_page: int = 0, timeout=300, **kwargs):
        kwargs.update({
            "message": message,
            "pages": pages,
            "home_page": home_page,
            "timeout": timeout
        })
        super().__init__(*args, **kwargs)
        self.message = message
        self.pages = pages
        self.home_page = home_page
        self.page_count = len(pages)
        self.current_page_number = home_page
        self.add_item(DeleteMessageButton(deletes_message=True))



    def update_page_data(self, pages, home_page):
        self.pages = pages
        self.page_count = len(pages)
        self.home_page = home_page


    async def update_message(self):
        self.current_page_number = clamp(self.current_page_number, 0, self.page_count)
        try:
            await self.message.edit(content=self.pages[self.current_page_number])
        except discord.HTTPException as e:
            print(e)


    @discord.ui.button(emoji="⬆", style=discord.ButtonStyle.gray, custom_id="MessageScroller:first", row=0)
    async def page_first(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = 0
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="🔼", style=discord.ButtonStyle.gray, custom_id="MessageScroller:prev", row=0)
    async def page_prev(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = clamp(self.current_page_number-1, 0, self.page_count-1)
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="*️⃣", style=discord.ButtonStyle.gray, custom_id="MessageScroller:home", row=0)
    async def page_home(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = self.home_page
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="🔽", style=discord.ButtonStyle.gray, custom_id="MessageScroller:next", row=0)
    async def page_next(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = clamp(self.current_page_number + 1, 0, self.page_count - 1)
        await interaction.response.edit_message()
        await self.update_message()

    @discord.ui.button(emoji="⬇", style=discord.ButtonStyle.gray, custom_id="MessageScroller:last", row=0)
    async def page_last(self, interaction: discord.Interaction, button: discord.ui.button):
        self.current_page_number = len(self.pages) - 1
        await interaction.response.edit_message()
        await self.update_message()



class QueueController(PlayerControls, MessageScroller):
    def __init__(self, player: OldPlayer, message, pages, home_page):
        super().__init__(player=player, message=message, pages=pages, home_page=home_page, timeout=600)
        # self.add_item(DeleteMessageButton(deletes_message=True))
        self.update_pages_loop.start()

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.data["custom_id"].startswith("PlayerControls"):
            await self.update_pages_loop()
        return True



    @tasks.loop(seconds=5)
    async def update_pages_loop(self):
        pages, home_page = await create_queue_pages(self.player)
        self.update_page_data(pages, home_page)
        await self.update_message()


    async def stopHandler(self):
        try:
            self.update_pages_loop.stop()
        except discord.HTTPException as e:
            print(f"Exception Encountered: {e}")


    async def on_timeout(self) -> None:
        await self.stop()




# class MessageReact(discord.ui.Modal, title="Message React"):
#     def __init__(self, message: discord.Message):
#         super().__init__()
#         self.message = message
#
#     response = discord.ui.TextInput(label="Separate multiple emoji with a ','")
#
#     async def on_submit(self, interaction: discord.Interaction):
#         reactions_to_add = self.response.value.split(",")
#         for reaction in reactions_to_add:
#             await self.message.add_reaction(reaction)
#         await interaction.response.defer(ephemeral=True)


# class ScrollableMessage(discord.ui.Modal, title="Scrollable Message")
#     def __init__(self, message: discord.Message):
#         super().__init__()
#         self.message = message




# class ColorSelector(discord.ui.Modal, title="Color Selector"):
#     def __init__(self, guild: discord.Guild):
#         super().__init__()
#     name = discord.ui.
#
#     async def on_submit(self, interaction: discord.Interaction):
