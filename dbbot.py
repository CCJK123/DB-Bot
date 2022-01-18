import os
import random
import aiohttp
from replit.database import AsyncDatabase
from typing import Any, Awaitable, Callable

import discord
from discord.ext import commands, tasks

from utils import discordutils, financeutils

class DBBot(commands.Bot):
    def __init__(self, db_url, on_ready_func: Callable[[], None]):
        intents = discord.Intents(guilds=True, messages=True, members=True)
        super().__init__(command_prefix=os.environ['command_prefix'],
                         help_command=discordutils.DBHelpCommand(),
                         intents=intents)

        self.on_ready_func = on_ready_func
        self.session = None
        self.database = AsyncDatabase(db_url)
        self.prepped = False
        

    async def prep(self):
        self.session = await aiohttp.ClientSession().__aenter__()
        self.database = await self.database.__aenter__()
        
        
        # dummy persistent views passed to add_view
        self.add_view(financeutils.RequestChoices(None, None))
        self.add_view(financeutils.WithdrawalView(None, 'dummy_link'))

    async def cleanup(self):
        await self.session.__aexit__(None, None, None)
        await self.database.__aexit__(None, None, None)

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

        if not self.change_status.is_running():
            self.change_status.start()

        self.on_ready_func()

    async def on_command_error(self, ctx: commands.Context, exception):
        command = ctx.command
        if command and command.has_error_handler():
            return

        await ctx.send(str(exception))

        p_ignore = (
            commands.CommandNotFound,
            commands.MissingRole,
            commands.MissingRequiredArgument
        )
        if not isinstance(exception, p_ignore):
            await super().on_command_error(ctx, exception)

    def db_set(self, cog_name: str, key: str, val: Any) -> Awaitable[None]:
        return self.database.set(f'{cog_name}.{key}', val)

    def db_get(self, cog_name: str, key: str) -> Awaitable[Any]:
        return self.database.get(f'{cog_name}.{key}')