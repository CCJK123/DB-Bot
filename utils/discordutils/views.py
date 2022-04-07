from __future__ import annotations

import abc
import asyncio
import functools
import pickle
from typing import Awaitable, Callable, Mapping

import discord

__all__ = ('Choices', 'LinkButton', 'LinkView', 'MultiLinkView', 'PersistentView', 'CallbackPersistentView')


# Setup buttons for user to make choices
# noinspection PyAttributeOutsideInit
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


class MultiLinkView(discord.ui.View):
    def __init__(self, links: Mapping[str, str]):
        super().__init__()
        for label, url in links.items():
            self.add_item(LinkButton(label, url))


class PersistentView(discord.ui.View, metaclass=abc.ABCMeta):
    last_id = -1
    bot: 'dbbot.DBBot | None' = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_id = None

    @abc.abstractmethod
    def get_state(self) -> tuple:
        ...

    @classmethod
    def _new_uninitialised(cls) -> 'PersistentView':
        return cls.__new__(cls)

    def __setstate__(self, state: tuple) -> None:
        if state[0] == 0:
            self.__init__(*state[2:], custom_id=state[1])
        elif state[0] == 1:
            self.__init__(*state[3:], custom_id=state[1], **state[2])
        else:
            raise pickle.UnpicklingError(f'Unsupported state tuple version {state[0]} for CallbackPersistentView')

    def __reduce_ex__(self, protocol: int):
        return self._new_uninitialised, (), (1, self.custom_id, *self.get_state())

    async def remove(self) -> None:
        await self.bot.views.pop(self)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        cls.last_id = -1

    @classmethod
    def get_id(cls):
        cls.last_id += 1
        return cls.last_id


Callback = Callable[..., Awaitable[None]]


class CallbackPersistentView(PersistentView, metaclass=abc.ABCMeta):
    callbacks: dict[str, Callback] = {}

    def __init__(self, *args, key: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if key in self.callbacks:
            self.key = key
        else:
            raise ValueError(f'Key {key} has not been registered!')

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

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.callbacks = {}
