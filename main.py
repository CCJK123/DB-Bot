from flask import Flask
from threading import Thread
import asyncio
import logging
import os   # For env variables
from replit import db

from discord.ext import commands

import discordutils



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
    
    
    bot = discordutils.DBBot(db.db_url, keep_alive)


    # Load cogs
    cogs = (file.split('.')[0] for file in os.listdir('cogs') if file.endswith('.py') and file != '__init__.py')
    for ext in cogs:
        bot.load_extension(f'cogs.{ext}')

    bot.help_command.cog = bot.get_cog('UtilCog')

    # Reload cogs
    @commands.guild_only()
    @commands.check(discordutils.gov_check)
    @bot.command(aliases=('reload',))
    async def reload_ext(ctx: commands.Context, extension: str) -> None:
        try:
            bot.reload_extension(f'cogs.{extension}')
        except commands.ExtensionNotLoaded:
            await ctx.send(f'The extension {extension} was not previously loaded!')
            return
        await ctx.send(f'Extension {extension} reloaded!')

    bot.run(discordutils.Config.token)


    # When bot stops
    asyncio.run(bot.cleanup())