# Import external python modules
from flask import Flask
from threading import Thread
import random
import aiohttp
import asyncio
import logging
import os   # For env variables
from replit import db
from replit.database import AsyncDatabase
from typing import Any

# Import discord.py and related modules
import discord
from discord.ext import commands, tasks

# Import own modules
import discordutils
import cogs.finance

cog_logger = logging.getLogger('cogs')
cog_logger.addHandler(logging.FileHandler('logs.txt'))

# Setup bot
class DBBot(commands.Bot):
    def __init__(self, db_url):
        super().__init__(command_prefix=os.environ['command_prefix'])
        
        self.db = AsyncDatabase(db_url)
        self.prepped = False

    async def prep(self):
        self.session = await aiohttp.ClientSession().__aenter__()
        self.db = await self.db.__aenter__()

    async def cleanup(self):
        await self.session.__aexit__()
        await self.db.__aexit__()
    
    # Change bot status (background task for 24/7 functionality)
    status = (
        *map(discord.Game, ("with Python", "with repl.it", "with the P&W API")),
        discord.Activity(type=discord.ActivityType.listening, name="Spotify"),
        discord.Activity(type=discord.ActivityType.watching, name="YouTube")
    )

    @tasks.loop(seconds=20)
    async def change_status(self):
        await self.change_presence(activity=random.choice(self.status))
    
    async def on_ready(self):
        if not self.prepped:
            self.prepped = True
            await self.prep()
        
        keep_alive()

        self.add_view(cogs.finance.RequestChoices(None, None))
        self.change_status.start()
        print('Ready!')
    
    async def db_set(self, cog_name: str, key: str, val: Any) -> None:
        await self.db.set(cog_name, {
            **await self.db.get(cog_name),
            key: val
        })
    
    async def db_get(self, cog_name: str, key: str) -> Any:
        return (await self.db.get(cog_name))[key]

if __name__ == '__main__':
    bot = DBBot(db.db_url)

    # Load cogs
    for ext in ('finance', 'util', 'war'):
        bot.load_extension(f'cogs.{ext}')

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