import abc
import operator
import pickle
from typing import Any, Callable, Generic, TypeVar, TYPE_CHECKING

import discord

from .views import PersistentView

if TYPE_CHECKING:
    from ... import dbbot

__all__ = ('CogBase', 'BotProperty', 'ViewStorage', 'CogProperty',
           'WrappedProperty', 'ChannelProperty', 'MappingProperty')


class CogBase(discord.Cog):
    def __init__(self, bot: "dbbot.DBBot", name: str):
        self.bot = bot
        self.cog_name = name


T = TypeVar('T')
T0 = TypeVar('T0')
T1 = TypeVar('T1')
DT = TypeVar('DT')

_sentinel = object()


class SavedProperty(Generic[T], metaclass=abc.ABCMeta):
    __slots__ = ('value', 'key')

    def __init__(self, key: str):
        self.value: object | T = _sentinel
        self.key = key

    async def get(self, default: object | DT = _sentinel) -> T | DT:
        if self.value is _sentinel:
            try:
                self.value = await self.get_()
            except KeyError:
                if default is _sentinel:
                    raise
                return default
        return self.value

    async def set(self, value: T) -> None:
        self.value = value
        await self.set_(value)

    async def transform(self, func: Callable[[T], T]) -> None:
        await self.set(func(await self.get()))

    @abc.abstractmethod
    async def get_(self) -> T:
        ...

    @abc.abstractmethod
    async def set_(self, value: T) -> None:
        ...


class BotProperty(SavedProperty[T]):
    __slots__ = ('bot',)

    def __init__(self, bot: 'dbbot.DBBot', key: str):
        super().__init__(key)
        self.bot = bot

    async def get_(self) -> T:
        return await self.bot.database.get(self.key)

    async def set_(self, value: T) -> None:
        await self.bot.database.set(self.key, value)


V = TypeVar('V', bound=PersistentView)


class ViewStorage(BotProperty[dict[V, str]]):
    """Stores persistent views for reloading upon bot restart"""
    __slots__ = ()

    async def get_(self) -> dict[V, str]:
        return {pickle.loads(bytes.fromhex(p_view)): p_view for p_view in await super().get_()}

    async def set_(self, value: dict[V, str]) -> None:
        await super().set_(list(value.values()))

    async def get_views(self) -> tuple[V]:
        return tuple((await self.get()).keys())

    async def add(self, v: V) -> None:
        if v in self.value:
            return
        self.value[v] = pickle.dumps(v, 5).hex()
        await self.set_(self.value)

    async def pop(self, v: V) -> None:
        self.value.pop(v)
        await self.set_(self.value)


class CogProperty(SavedProperty[T]):
    """A generic property to be used in cogs"""
    __slots__ = ('owner',)

    def __init__(self, owner: CogBase, key: str):
        super().__init__(key)
        self.owner = owner

    @property
    def full_key(self) -> str:
        return f'{self.owner.cog_name}.{self.key}'

    async def get_(self) -> T:
        return await self.owner.bot.database.get(self.full_key)

    async def set_(self, value: T) -> None:
        await self.owner.bot.database.set(self.full_key, value)


class MappingPropertyItem(Generic[T, T1]):
    __slots__ = ('mapping', 'key')

    def __init__(self, mapping: 'MappingProperty[T, T1]', key: T):
        self.mapping = mapping
        self.key = key

    async def get(self, default: object | DT = _sentinel) -> T1 | DT:
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

    async def transform(self, func: Callable[[T1], T1]):
        await self.set(func(self.get()))


class MappingProperty(Generic[T0, T1], CogProperty[dict[T0, T1]]):
    """A property to access a mapping"""
    __slots__ = ()

    def __getitem__(self, key: T0) -> MappingPropertyItem[T0, T1]:
        return MappingPropertyItem[T0, T1](self, str(key))

    async def contains_key(self, item: T0) -> bool:
        return str(item) in await self.get()

    async def contains_value(self, item: T1) -> bool:
        return item in (await self.get()).values()

    async def initialise(self) -> None:
        """
        Makes sure that the property is set to a dict before it is accessed
        Should only actually do anything the first time, when nothing is set at self.key
        """
        if await self.get(None) is None:
            print(f'Initialising key {self.key} from {self.owner.cog_name} to {{}}')
            await self.set({})


class WrappedProperty(Generic[T, T1], CogProperty[T]):
    """Property where the stored value is wrapped with functions to get the actual value"""
    __slots__ = ('transform_to', 'transform_from')

    def __init__(self, owner: CogBase, key: str,
                 transform_to: Callable[[T1], T] = lambda x: x,
                 transform_from: Callable[[T], T1] = lambda x: x):
        super().__init__(owner, key)
        self.value: object | T1
        self.transform_to = transform_to
        self.transform_from = transform_from

    async def get_(self):
        return self.transform_to(await super().get_())

    async def set_(self, value: T) -> None:
        await super().set_(self.transform_from(value))


class ChannelProperty(WrappedProperty[discord.TextChannel, int]):
    """Property to store a discord.TextChannel across bot restarts"""
    __slots__ = ()

    def __init__(self, owner: CogBase, key: str):
        super().__init__(owner, key, owner.bot.get_channel, operator.attrgetter('id'))
