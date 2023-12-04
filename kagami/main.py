import logging
from bot.kagami_bot import Kagami
import logging
import logging.handlers

from bot.kagami_bot import Kagami

log_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

logger = logging.getLogger("discord")
logger.setLevel(logging.DEBUG)
logging.getLogger()

def main():
    kagami = Kagami()
    kagami.run(kagami.config["token"], log_handler=log_handler, log_level=logging.DEBUG)


if __name__ == '__main__':
    main()

