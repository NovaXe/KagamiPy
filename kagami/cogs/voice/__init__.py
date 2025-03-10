from bot import Kagami
from . import voice
from . import music
from . import db
from .db import TrackList, MusicSettings, FavoriteTrack

async def setup(bot: Kagami):
    await bot.add_cog(music.MusicCog(bot))

