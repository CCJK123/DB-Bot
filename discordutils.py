from __future__ import annotations

import random
import aiohttp
from replit.database import AsyncDatabase
import asyncio
import operator
import sys
import traceback
import os   # For env variables
from typing import Any, Awaitable, Callable, Generic, Mapping, Optional, TypeVar, Union

import discord
from discord.ext import commands, tasks

from financeutils import RequestChoices



# Setup what is exported by default
__all__ = ('Config', 'Choices', 'construct_embed', 'gov_check', 'CogBase', 'SavedProperty', 'WrappedProperty')



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
    def __init__(self, label: str, user_id: Optional[int]):
        super().__init__()
        self.label = label


    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view.user_id is not None and self.view.user_id != interaction.user.id:
            await interaction.send('You are not the intended recipent of this component, '
                                   f'{interaction.user.mention}',
                                   allowed_mentions=discord.AllowedMentions.none())
            return
        self.view.set_result(self.label)
        self.style = discord.ButtonStyle.success
        for child in self.view.children:
            # assert isinstance(child, discord.ui.Button)  # just to shut up the linter
            child.disabled = True
        self.view.stop()
        await interaction.response.edit_message(view=self.view)



class Choices(discord.ui.View):
    def __init__(self, *choices: str, user_id: Optional[int]):
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



class CogBase(commands.Cog):
    def __init__(self, bot: DBBot, name: str):
        self.bot = bot
        self.cog_name = name



T = TypeVar('T')
T1 = TypeVar('T1')
DT = TypeVar('DT')



_sentinel = object()
class SavedProperty(Generic[T]):
    def __init__(self, owner: CogBase, key: str):
        self.value: Union[object, T] = _sentinel
        self.key = key
        self.owner = owner


    async def get(self, default: Union[object, DT] = _sentinel) -> Union[T, DT]:
        try:
            if self.value is _sentinel:
                self.value = await self.owner.bot.db_get(self.owner.cog_name, self.key)
        except KeyError:
            if default is _sentinel:
                raise
            return default
        return self.value


    async def set(self, value: T) -> None:
        self.value = value
        await self.owner.bot.db_set(self.owner.cog_name, self.key, value)
    

    async def transform(self, func: Callable[[T], T]) -> None:
        await self.set(func(await self.get()))



class MappingPropertyItem(Generic[T, T1]):
        def __init__(self, mapping: MappingProperty[T, T1], key: T):
            self.mapping = mapping
            self.key = key


        async def get(self, default: Union[object, DT] = _sentinel) -> Union[T, DT]:
            try:
                return (await self.mapping.get())[self.key]
            except KeyError:
                if default is _sentinel:
                    raise
                return default


        @staticmethod
        def get_set_func(key: T, value: T1) -> Callable[[dict[T, T1]], dict[T, T1]]:
                def func(m: dict[T, T1]) -> dict[T, T1]:
                    m[key] = value
                    return m
                return func


        async def set(self, value: T):
            self.mapping.transform(self.get_set_func(self.key, value))



class MappingProperty(Generic[T, T1], SavedProperty[dict[T, T1]]):
    def __getitem__(self, key: T) -> MappingPropertyItem[T, T1]:
        return MappingPropertyItem[T, T1](self, key)



class WrappedProperty(SavedProperty[T], Generic[T, T1]):
    def __init__(self, owner: CogBase, key: str,
                 transform_to: Callable[[T1], T] = lambda x: x,
                 transform_from: Callable[[T], T1] = lambda x: x):
        super().__init__(owner, key)
        self.value: Union[object, T1]
        self.transform_to = transform_to
        self.transform_from = transform_from
    

    async def get(self, default: Union[object, DT] = _sentinel) -> Union[T, DT]:
        if self.value is _sentinel:
            try:
                self.value = self.transform_to(await self.owner.bot.db_get(
                    self.owner.cog_name, self.key))
            except KeyError:
                if default is _sentinel:
                    raise 
                return default
        return self.value
    

    async def set(self, value: T) -> None:
        self.value = value
        await self.owner.bot.db_set(self.owner.cog_name, self.key,
            self.transform_from(value))



class ChannelProperty(WrappedProperty[discord.TextChannel, int]):
    def __init__(elf, owner: CogBase, key: str):
        super().__init__(owner, key, owner.bot.get_channel, operator.attrgetter('id'))