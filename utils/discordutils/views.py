from __future__ import annotations

import abc
import asyncio
import functools
import pickle
from typing import Awaitable, Callable, Mapping, TypeVar, Type

import discord

__all__ = ('Choices', 'LinkButton', 'LinkView', 'MultiLinkView', 'PersistentView', 'PersistentButton',
           'persistent_button', 'single_modal', 'disable_all', 'enable_all')


# Setup buttons for user to make choices
# noinspection PyAttributeOutsideInit
class Choice(discord.ui.Button['Choices']):
    def __init__(self, label: str, disabled: bool = False):
        super().__init__(label=label, disabled=disabled)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.future.set_result(self.label)
        self.style = discord.ButtonStyle.success
        disable_all(self.view)
        self.view.stop()
        await interaction.response.edit_message(view=self.view)


class Choices(discord.ui.View):
    def __init__(self, *choices: str, disabled: set[str] | None = None):
        super().__init__()
        if disabled is None:
            disabled = set()
        self.future = asyncio.get_event_loop().create_future()
        for c in choices:
            self.add_item(Choice(c, c in disabled))

    def result(self) -> Awaitable[str]:
        return self.future

    async def on_timeout(self):
        self.future.set_exception(asyncio.TimeoutError())


class LinkButton(discord.ui.Button):
    def __init__(self, label: str, url: str):
        super().__init__(label=label, url=url)


class LinkView(discord.ui.View):
    def __init__(self, label: str, url: str):
        super().__init__()
        self.add_item(LinkButton(label, url))


class MultiLinkView(discord.ui.View):
    def __init__(self, links: Mapping[str, str]):
        super().__init__()
        for label, url in links.items():
            self.add_item(LinkButton(label, url))


class PersistentView(discord.ui.View, abc.ABC):
    __persistent_children__ = None
    bot: 'DBBot | None' = None

    def __init__(self, *args, custom_id: int, **kwargs):
        super().__init__(*args, timeout=None, **kwargs)
        self.custom_id = custom_id

        for func in self.__persistent_children__:
            item = func.__persistent_class__(f'{func.__name__} {self.custom_id}', **func.__persistent_kwargs__)
            item.callback = functools.partial(func, self, item)
            self.add_item(item)

    @abc.abstractmethod
    def get_state(self) -> tuple:
        ...

    @classmethod
    def _new_uninitialised(cls) -> 'PersistentView':
        return cls.__new__(cls)

    def __setstate__(self, state: tuple) -> None:
        try:
            if state[0] == 0:
                self.__init__(*state[2:], custom_id=state[1])
            elif state[0] == 1:
                self.__init__(*state[3:], custom_id=state[1], **state[2])
            else:
                raise pickle.UnpicklingError(f'Unsupported state tuple version {state[0]} for PersistentView')
        except Exception:
            print(state)
            raise

    def __reduce_ex__(self, protocol: int):
        return self._new_uninitialised, (), (1, self.custom_id, *self.get_state())

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        cls.__persistent_children__ = []
        for base in reversed(cls.__mro__):
            for member in base.__dict__.values():
                if hasattr(member, '__persistent_class__'):
                    cls.__persistent_children__.append(member)


V = TypeVar('V', bound=PersistentView)


class PersistentButton(discord.ui.Button[V], abc.ABC):
    def __init__(self, custom_id: str, **kwargs):
        super().__init__(custom_id=custom_id, **kwargs)


WrappedCallback = Callable[[PersistentButton, discord.Interaction], Awaitable[None]]


def persistent_button(**kwargs) -> Callable[[WrappedCallback], WrappedCallback]:
    def deco(func: WrappedCallback) -> WrappedCallback:
        func.__persistent_class__ = PersistentButton
        func.__persistent_kwargs__ = kwargs
        return func

    return deco


class SingleModal(discord.ui.Modal):
    def __init__(self, title: str):
        super().__init__(title=title)
        self.future = asyncio.get_event_loop().create_future()
        self.interaction: discord.Interaction | None = None

    def result(self) -> Awaitable[str]:
        return self.future

    async def on_timeout(self) -> None:
        self.future.set_result(asyncio.TimeoutError())


@functools.cache
def _single_modal_create(label: str, style: discord.TextStyle) -> Type[SingleModal]:
    class _Modal(SingleModal):
        input_box = discord.ui.TextInput(
            label=label,
            style=style
        )

        async def on_submit(self, interaction: discord.Interaction) -> None:
            self.future.set_result(self.input_box.value)
            self.interaction = interaction

    return _Modal


def single_modal(title: str, label: str, style: discord.TextStyle = discord.TextStyle.short) -> SingleModal:
    return _single_modal_create(label, style)(title)


def disable_all(view: discord.ui.View):
    for c in view.children:
        if isinstance(c, discord.ui.Button):
            c.disabled = True


def enable_all(view: discord.ui.View):
    for c in view.children:
        if isinstance(c, discord.ui.Button):
            c.disabled = False
