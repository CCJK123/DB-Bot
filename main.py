import asyncio
import logging

from utils import config, dbbot

cog_logger = logging.getLogger('cogs')
cog_logger.addHandler(logging.FileHandler('logs.txt'))

if __name__ == '__main__':
    bot = dbbot.DBBot(config.database_url)

    # Load cogs
    bot.load_cogs('cogs')

    # bot.help_command.cog = bot.get_cog('UtilCog')
    # the new bot does not seem to have a help command, the help command has not been ported over to slash yet, I think

    print('running bot...')

    try:
        bot.run(config.token)
    finally:
        # When bot stops
        print('cleaning up')
        asyncio.run(bot.cleanup())
        print('cleanup complete!')
