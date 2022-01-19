import os
import random
import aiohttp
from replit.database import AsyncDatabase
from typing import Callable

import discord
from discord.ext import commands, tasks

from utils import discordutils


class DBBot(commands.Bot):
    def __init__(self, db_url, on_ready_func: Callable[[], None]):
        intents = discord.Intents(guilds=True, messages=True, members=True)
        super().__init__(command_prefix=os.environ['command_prefix'],
                         help_command=discordutils.DBHelpCommand(),
                         intents=intents)

        self.on_ready_func = on_ready_func
        self.session = None
        self.database = AsyncDatabase(db_url)
        self.views = discordutils.ViewStorage[discordutils.CallbackPersistentView](self, 'views')
        if await self.views.get(None) is None:
            await self.views.set([])
        self.prepped = False

    async def prep(self):
        self.session = await aiohttp.ClientSession().__aenter__()
        self.database = await self.database.__aenter__()

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

    def add_view(self, view: discordutils.CallbackPersistentView, *, message_id: int | None = None) -> None:
        super().add_view(view, message_id=message_id)
        await self.views.append(view)

    async def on_ready(self):
        if not self.prepped:
            self.prepped = True
            await self.prep()

        if not self.change_status.is_running():
            self.change_status.start()

        # add views
        for view in await self.views.get():
            self.add_view(view)

        self.on_ready_func()

    async def on_command_error(self, ctx: commands.Context, exception):
        command = ctx.command
        if command and command.has_error_handler():
            return

        await ctx.send(str(exception))

        ignored = (
            commands.CommandNotFound,
            commands.MissingRole,
            commands.MissingRequiredArgument
        )
        if not isinstance(exception, ignored):
            await super().on_command_error(ctx, exception)
