import asyncio
import functools
import operator
import sys
import traceback
import os  # For env variables
from typing import (Awaitable, Callable, Generic, Iterable,
                    Mapping, TypeVar, Union, TYPE_CHECKING)

if TYPE_CHECKING:
    import dbbot

import discord
from discord.ext import commands

# Setup what is exported by default
__all__ = ('Config', 'Choices', 'construct_embed', 'gov_check', 'CogBase',
           'SavedProperty', 'WrappedProperty', 'ChannelProperty', 'MappingProperty')


class DBHelpCommand(commands.HelpCommand):
    d_desc = 'No description found'

    async def send_bot_help(self, mapping: Mapping[commands.Cog | None, list[commands.command]]):
        embeds = []
        for k in mapping:
            filtered = await self.filter_commands(mapping[k])
            if filtered:
                embeds.append(self.create_cog_embed(k, filtered))
        
        await self.get_destination().send(embeds=embeds)
    
    def create_cog_embed(self, cog: commands.Cog, cmds: list[commands.command]):
        embed = discord.Embed(title=cog.qualified_name,
                              description=cog.description)
        
        for cmd in cmds:
            embed.add_field(name=cmd.name,
                            value=cmd.description or cmd.short_doc or self.d_desc,
                            inline=False)
        
        return embed

    async def send_cog_help(self, cog: commands.Cog):
        embed = self.create_cog_embed(cog, await self.filter_commands(cog.get_commands()))
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group: commands.Group):
        embed = discord.Embed(
            title=self.get_command_signature(group),
            description=group.description
        )
        for cmd in await self.filter_commands(group.commands):
            embed.add_field(name=cmd.name,
                            value=cmd.description or cmd.short_doc or self.d_desc,
                            inline=False)
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command: commands.command):
        await self.get_destination().send(embed=discord.Embed(
            title=self.get_command_signature(command),
            description=command.description or command.short_doc
        ))


# Setup discord bot configuration variables
class Config:
    token: str = os.environ['bot_token']
    timeout: float = 300
    gov_role_id: int = 595155137274839040


# Setup buttons for user to make choices
class Choice(discord.ui.Button['Choices']):
    def __init__(self, label: str, disabled: bool = False):
        super().__init__(disabled=disabled, label=label)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view.user_id is not None and self.view.user_id != interaction.user.id:
            await interaction.channel.send('You are not the intended recipient of this component, '
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
    def __init__(self, *choices: str, user_id: int | None = None, disabled: set[str] | None = None):
        super().__init__()
        if disabled is None:
            disabled = set()
        self.user_id = user_id
        self._fut = asyncio.get_event_loop().create_future()
        for c in choices:
            self.add_item(Choice(c, c in disabled))

    def set_result(self, r: str) -> None:
        self._fut.set_result(r)

    def result(self) -> Awaitable[str]:
        return self._fut

    async def on_timeout(self):
        self._fut.set_exception(asyncio.TimeoutError())


class LinkButton(discord.ui.Button):
    def __init__(self, label: str, url: str):
        super().__init__(label=label, url=url)


class LinkView(discord.ui.View):
    def __init__(self, label: str, url: str):
        super().__init__()
        self.add_item(LinkButton(label, url))


Callback = Callable[..., Awaitable[None]]


class CallbackPersistentView(discord.ui.View):
    callbacks: dict[str, Callback] = {}

    def __init__(self, *args, key: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.key = key

    @classmethod
    def register_callback(cls, key: str | None = None, cog_name: str | None = None) -> Callable[[Callback], Callback]:
        def register(func: Callback):
            nonlocal key
            if key is None:
                key = func.__name__

            cls.callbacks[key] = functools.partial(func, cog_name) if cog_name else func
            return func

        return register

    @property
    def callback(self) -> Callback:
        if self.key is None:
            raise KeyError('Callback key has not been set!')
        return self.callbacks[self.key]


async def get_member_from_context(ctx: commands.Context) -> discord.Member:
    """Returns replied member, otherwise message author from context's message"""
    if ctx.message.reference is not None:
        msg = ctx.message.reference.cached_message
        if msg is None:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        return msg.author
    return ctx.author


def construct_embed(fields: Mapping[str, str], /, **kwargs: str) -> discord.Embed:
    """Create embed from dictionary of key-value pairs"""
    embed = discord.Embed(**kwargs)
    for k, v in fields.items():
        embed.add_field(name=k, value=v)
    return embed


def get_msg_chk(ctx: commands.Context) -> Callable[[discord.Message], bool]:
    def msg_chk(m: discord.Message) -> bool:
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    return msg_chk


def get_dm_msg_chk(auth_id: int) -> Callable[[discord.Message], bool]:
    def msg_chk(m: discord.Message) -> bool:
        return m.author.id == auth_id and m.guild is None

    return msg_chk


def split_blocks(joiner: str, items: Iterable[str], limit: int) -> Iterable[str]:
    """split a message from a string.join into blocks smaller than limit"""
    s = ''
    join_no_sep = True
    for i in items:
        if len(s) + len(joiner) + len(i) > limit:
            yield s
            s = ''
            join_no_sep = True
        if join_no_sep:
            s += i
            join_no_sep = False
        else:
            s += joiner + i

    if s:
        yield s
    return


gov_check = commands.has_role(Config.gov_role_id)


async def default_error_handler(context: commands.Context, exception: commands.CommandError) -> None:
    print(f'Ignoring exception in command {context.command}:', file=sys.stderr)
    traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)


class CogBase(commands.Cog):
    def __init__(self, bot: "dbbot.DBBot", name: str):
        self.bot = bot
        self.cog_name = name


T = TypeVar('T')
T1 = TypeVar('T1')
DT = TypeVar('DT')

_sentinel = object()


class SavedProperty(Generic[T]):
    __slots__ = ('value', 'key', 'owner')

    def __init__(self, owner: CogBase, key: str):
        self.value: Union[object, T] = _sentinel
        self.key = key
        self.owner = owner

    async def get(self, default: Union[object, DT] = _sentinel) -> Union[T, DT]:
        if self.value is _sentinel:
            try:
                self.value = await self.owner.bot.db_get(self.owner.cog_name, self.key)
            except KeyError:
                if default is _sentinel:
                    raise
                return default
        return self.value

    async def set(self, value: T) -> None:
        self.value = value
        await self.update()
    
    async def update(self) -> None:
        await self.owner.bot.db_set(self.owner.cog_name, self.key, self.value)

    async def transform(self, func: Callable[[T], T]) -> None:
        await self.set(func(await self.get()))


class MappingPropertyItem(Generic[T, T1]):
    __slots__ = ('mapping', 'key')

    def __init__(self, mapping: 'MappingProperty[T, T1]', key: T):
        self.mapping = mapping
        self.key = key

    async def get(self, default: Union[object, DT] = _sentinel) -> Union[T1, DT]:
        try:
            return (await self.mapping.get())[self.key]
        except KeyError:
            if default is _sentinel:
                raise
            return default

    async def set(self, value: T1) -> None:
        m = await self.mapping.get()
        m[self.key] = value
        await self.mapping.set(m)

    async def delete(self) -> None:
        m = await self.mapping.get()
        del m[self.key]
        await self.mapping.set(m)


class MappingProperty(Generic[T, T1], SavedProperty[dict[T, T1]]):
    __slots__ = ()

    def __getitem__(self, key: T) -> MappingPropertyItem[T, T1]:
        return MappingPropertyItem[T, T1](self, str(key))

    async def initialise(self) -> None:
        """
        Makes sure that the property is set to a dict before it is accessed
        Should only actually do anything the first time, when nothing is set to self.key
        """
        if await self.get(None) is None:
            print(f'Initialising key {self.key} from {self.owner.cog_name} to {{}}')
            await self.set({})


class WrappedProperty(Generic[T, T1], SavedProperty[T]):
    __slots__ = ('transform_to', 'transform_from')

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

    async def update(self) -> None:
        await self.owner.bot.db_set(self.owner.cog_name, self.key,
                                    self.transform_from(self.value))


class ChannelProperty(WrappedProperty[discord.TextChannel, int]):
    __slots__ = ()

    def __init__(self, owner: CogBase, key: str):
        super().__init__(owner, key, owner.bot.get_channel, operator.attrgetter('id'))
