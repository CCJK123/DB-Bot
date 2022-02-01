import asyncio
import atexit
import logging
import os  # For env variables
from threading import Thread

from flask import Flask
from replit import db

import dbbot
from utils import config

cog_logger = logging.getLogger('cogs')
cog_logger.addHandler(logging.FileHandler('logs.txt'))

if __name__ == '__main__':
    # Flask server setup (for 24/7 functionality)
    app = Flask(__name__)


    @app.route("/")
    def main():
        return os.environ['online_msg']


    def run():
        app.run(host="0.0.0.0")


    def keep_alive():
        server = Thread(target=run)
        server.start()


    bot = dbbot.DBBot(db.db_url, keep_alive)

    # Load cogs
    bot.load_cogs('cogs')

    # bot.help_command.cog = bot.get_cog('UtilCog')
    # the new bot doesnt seem to have a help command, the help command has not been ported over to slash yet i believe


    def on_stop():
        # When bot stops
        print('cleaning up')
        asyncio.run(bot.cleanup())


    atexit.register(on_stop)

    bot.run(config.token)
