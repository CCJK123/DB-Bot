from __future__ import annotations

import asyncio
from typing import Callable, Awaitable, Literal, Optional
from dataclasses import dataclass, field

import discord

import pnwutils

__all__ = ('RequestData', 'RequestChoices', 'ResourceSelectView')


@dataclass
class RequestData:
    requester: discord.abc.User
    kind: str
    reason: str
    nation_name: str
    nation_link: str
    resources: pnwutils.Resources
    note: str
    additional_info: Optional[dict[str, str]] = field(default_factory=dict)


class RequestChoice(discord.ui.Button['RequestChoices']):
    def __init__(self, label: Literal['Accepted', 'Rejected', 'Sent']):
        super().__init__(row=0, custom_id=label)
        self.label = label

    async def callback(self, interaction: discord.Interaction) -> None:
        self.style = discord.ButtonStyle.success
        for child in self.view.children:
            assert isinstance(child, RequestChoice)
            if self.label != 'Accepted' or child.label != 'Sent':
                # If self.label == Accepted and child.label == Sent, don't disable
                child.disabled = True
        if self.label != 'Accepted':
            self.view.stop()
        await interaction.response.edit_message(view=self.view)
        # type checker does not realise self.label is one of [Accepted, Rejected, Sent]
        await self.view.callback(self.label, interaction.user, interaction.message, *self.view.args)  # type: ignore


class RequestChoices(discord.ui.View):
    def __init__(self, callback: Callable[[Literal['Accepted', 'Rejected', 'Sent'], discord.abc.User,
                                           discord.Message, ...], Awaitable[None]], *args):
        # Callback would be called with 'Accepted', 'Rejected', or 'Sent'
        super().__init__(timeout=None)
        self.args = args
        self.callback = callback
        c: Literal['Accepted', 'Rejected', 'Sent']
        for c in ('Accepted', 'Rejected', 'Sent'):
            self.add_item(RequestChoice(c))


class ResourceSelector(discord.ui.Select['ResourceSelectView']):
    def __init__(self):
        options = [
            discord.SelectOption(label=s) for s in pnwutils.Constants.all_res
        ]
        super().__init__(placeholder='Choose the resources you want',
                         min_values=1,
                         max_values=len(options),
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.view.user_id is not None and interaction.user.id != self.view.user_id:
            await interaction.channel.send('You are not the intended recipient of this component, '
                                           f'{interaction.user.mention}',
                                           allowed_mentions=discord.AllowedMentions.none())
            return
        self.view.set_result(self.values)
        self.disabled = True
        await interaction.response.edit_message(view=self.view)


class ResourceSelectView(discord.ui.View):
    def __init__(self, timeout: float, user_id: Optional[int] = None):
        super().__init__(timeout=timeout)
        self._fut = asyncio.get_event_loop().create_future()
        self.user_id = user_id
        self.add_item(ResourceSelector())

    def set_result(self, r: list[str]) -> None:
        self._fut.set_result(r)

    def result(self) -> Awaitable[list[str]]:
        return self._fut

    async def on_timeout(self):
        self._fut.set_exception(asyncio.TimeoutError())
