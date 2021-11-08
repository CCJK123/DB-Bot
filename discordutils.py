from __future__ import annotations

import random
import aiohttp
from replit.database import AsyncDatabase
import asyncio
import operator
import sys
import traceback
import os   # For env variables
from typing import Any, Awaitable, Callable, Generic, Mapping, TypeVar, Union

import discord
from discord.ext import commands, tasks



# Setup what is exported by default
__all__ = ('Config', 'Choices', 'construct_embed', 'gov_check')



# Setup bot
class DBBot(commands.Bot):
    def __init__(self, db_url, on_ready_func: Callable[[], None]):
        super().__init__(command_prefix=os.environ['command_prefix'])
        self.on_ready_func = on_ready_func
        
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

        self.change_status.start()
        self.on_ready_func()
    
    
    def db_set(self, cog_name: str, key: str, val: Any) -> Awaitable[None]:
        return self.db.set(cog_name + '.' + key, val)


    def db_get(self, cog_name: str, key: str) -> Awaitable[Any]:
        return self.db.get(cog_name + '.' + key)



# Setup discord bot configuration variables
class Config:
    token: str = os.environ['bot_token']
    timeout: float = 300
    gov_role_id: int = 595155137274839040



# Setup buttons for user to make choices
class Choice(discord.ui.Button['Choices']):
    def __init__(self, label: str):
        super().__init__()
        self.label = label


    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.set_result(self.label)
        self.style = discord.ButtonStyle.success
        for child in self.view.children:
            # assert isinstance(child, discord.ui.Button)  # just to shut up the linter
            child.disabled = True
        self.view.stop()
        await interaction.response.edit_message(view=self.view)



class Choices(discord.ui.View):
    def __init__(self, *choices: str):
        super().__init__()
        self._fut = asyncio.get_event_loop().create_future()
        for c in choices:
            self.add_item(Choice(c))


    def set_result(self, r: str) -> None:
        self._fut.set_result(r)


    def result(self) -> Awaitable[str]:
        return self._fut
    

    async def on_timeout(self):
        self._fut.set_exception(asyncio.TimeoutError())
    


# Create embed from dictionary of key-value pairs
def construct_embed(fields: Mapping[str, str], /, **kwargs: str) -> discord.Embed:
    embed = discord.Embed(**kwargs)
    for k, v in fields.items():
        embed.add_field(name=k, value=v)
    return embed



# Check if user in DB government
async def gov_check(ctx: commands.Context) -> bool:    
    # Check if command was sent in DB server or in DM
    if isinstance(ctx.author, discord.Member):
        # Sent from DB server - Check server roles
        # Check if server member has id of "The Black Hand" role
        if Config.gov_role_id in map(operator.attrgetter('id'), ctx.author.roles):
            return True
        # Inform non-gov members about their lack of permissions
        await ctx.send("You do not have the necessary permissions to run this command.")

    else:
        # type(ctx.author) == discord.User
        # Sent from DM - Ignore
        await ctx.send("Kindly run this command on the DB server.")
        
    return False



async def default_error_handler(context: commands.Context, exception: commands.CommandError) -> None:
    print(f'Ignoring exception in command {context.command}:', file=sys.stderr)
    traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)


class Storage:
    pass