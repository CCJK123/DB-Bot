from flask import Flask
from threading import Thread
import asyncio
import logging
import os   # For env variables
from replit import db
import atexit

from utils import discordutils
import dbbot



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
    cogs = (file.split('.')[0] for file in os.listdir('cogs') if file.endswith('.py') and not file.startswith('_'))
    for ext in cogs:
        bot.load_extension(f'cogs.{ext}')

    bot.help_command.cog = bot.get_cog('UtilCog')   


    def on_stop():
        # When bot stops
        print('cleaning up')
        asyncio.run(bot.cleanup())


    atexit.register(on_stop) 

    bot.run(discordutils.Config.token)
