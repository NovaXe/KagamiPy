from bot import Kagami
from . import voice
from . import music
from . import db

async def setup(bot: Kagami):
    await music.setup(bot)

