import logging

discord_log_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
bot_log_handler = logging.FileHandler(filename="bot.log", encoding="utf-8", mode='w')

def setup_logging(name: str):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(bot_log_handler)
    return logger
