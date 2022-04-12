import asyncio
import logging
import os
from threading import Thread

from flask import Flask

from utils import config, dbbot

cog_logger = logging.getLogger('cogs')
cog_logger.addHandler(logging.FileHandler('logs.txt'))

if __name__ == '__main__':
    app = Flask(__name__)


    @app.route("/")
    def main():
        return os.environ['MYSQLCONNSTR_ONLINE_MSG']


    def run():
        app.run()


    def keep_alive():
        server = Thread(target=run)
        server.start()

    bot = dbbot.DBBot('data.db', keep_alive)

    # Load cogs
    bot.load_cogs('cogs')

    # bot.help_command.cog = bot.get_cog('UtilCog')
    # the new bot does not seem to have a help command, the help command has not been ported over to slash yet I believe

    try:
        bot.run(config.token)
    finally:
        # When bot stops
        print('cleaning up')
        asyncio.run(bot.cleanup())
