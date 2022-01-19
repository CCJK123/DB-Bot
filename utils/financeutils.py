from __future__ import annotations

import asyncio
import datetime
import enum
from typing import Any, Callable, Awaitable, Iterable, Optional, TypedDict
from dataclasses import dataclass, field

import discord

from . import discordutils, pnwutils

__all__ = ('RequestData', 'LoanData', 'RequestStatus', 'RequestChoices', 'ResourceSelectView', 'WithdrawalView')


@dataclass(slots=True)
class RequestData:
    requester: discord.abc.User
    nation_id: str
    nation_name: str
    kind: str = ''
    reason: str = ''
    resources: pnwutils.Resources = field(default_factory=pnwutils.Resources)
    note: str = ''
    additional_info: dict[str, str] = field(default_factory=dict)

    @property
    def nation_link(self):
        return pnwutils.Link.nation(self.nation_id)

    def create_embed(self, **kwargs: str) -> discord.Embed:
        embed = discord.Embed(**kwargs)
        embed.add_field(name='Nation', value=f'[{self.nation_name}]({self.nation_link})')
        embed.add_field(name='Request Type', value=self.kind)
        embed.add_field(name='Reason', value=self.reason)
        embed.add_field(name='Requested Resources', value=self.resources)
        for n, v in self.additional_info.items():
            embed.add_field(name=n, value=v)
        return embed

    def create_link(self) -> str:
        return pnwutils.Link.bank("w", self.resources, self.nation_name, self.note if self.note else self.reason)

    def create_withdrawal_embed(self) -> discord.Embed:
        return withdrawal_embed(self.nation_name, self.nation_id, self.reason, self.resources)

    def to_dict(self) -> dict[str, Any]:
        return {
            'requester': self.requester,
            'nation_id': self.nation_id,
            'nation_name': self.nation_name,
            'kind': self.kind,
            'reason': self.reason,
            'resources': self.resources.to_dict(),
            'note': self.note,
            'additional_info': self.additional_info
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'RequestData':
        d['resources'] = pnwutils.Resources(**d['resources']) 
        return cls(**d)


class LoanDataDict(TypedDict):
    due_date: str
    resources: pnwutils.ResourceDict


class LoanData:
    __slots__ = ('due_date', 'resources')

    def __init__(self, due_date: str | datetime.datetime, resources: pnwutils.Resources | pnwutils.ResourceDict):
        if isinstance(due_date, str):
            self.due_date = datetime.datetime.fromisoformat(due_date)
        else:
            self.due_date = due_date

        if isinstance(resources, pnwutils.Resources):
            self.resources = resources
        else:
            self.resources = pnwutils.Resources(**resources)

    @property
    def display_date(self):
        return self.due_date.strftime('%d %b, %Y')

    def to_dict(self) -> dict[str, str]:
        return {'due_date': self.due_date.isoformat(), 'resources': self.resources.to_dict()}

    def to_embed(self, **kwargs: str) -> discord.Embed:
        embed = self.resources.create_embed(**kwargs)
        embed.insert_field_at(0, name='Due Date', value=self.display_date)
        return embed


class RequestStatus(enum.Enum):
    ACCEPTED = 'Accepted'
    REJECTED = 'Rejected'


RequestChosenCallback = Callable[[RequestStatus, discord.Interaction, RequestData],
                                 Awaitable[None]]


class RequestChoice(discord.ui.Button['RequestChoices']):
    def __init__(self, label: RequestStatus):
        super().__init__(row=0, label=label.value, custom_id=label.value)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.style = discord.ButtonStyle.success
        for child in self.view.children:
            child.disabled = True
        self.view.stop()
        await self.view.remove()
        await interaction.response.edit_message(view=self.view)
        await self.view.callback(RequestStatus(self.label), interaction, self.view.data)


class RequestChoices(discordutils.CallbackPersistentView):
    def __init__(self, callback_key: str, data: RequestData):
        # Callback would be called with 'Accepted', 'Rejected', or 'Sent'
        super().__init__(timeout=None, key=callback_key)
        self.data = data
        for c in RequestStatus:
            self.add_item(RequestChoice(c))

    def get_state(self) -> tuple:
        return self.data,


def withdrawal_embed(name: str, nation_id: str, reason: str, resources: pnwutils.Resources) -> discord.Embed:
    embed = discord.Embed()
    embed.add_field(name='Nation', value=f'[{name}]({pnwutils.Link.nation(nation_id)})')
    embed.add_field(name='Reason', value=reason)
    embed.add_field(name='Requested Resources', value=resources)
    return embed


class WithdrawalButton(discord.ui.Button['WithdrawalView']):
    def __init__(self):
        super().__init__(row=0, custom_id='Withdrawal Button', label='Sent')

    async def callback(self, interaction: discord.Interaction):
        self.style = discord.ButtonStyle.success
        self.disabled = True
        self.view.stop()
        await self.view.remove()
        await interaction.response.edit_message(view=self.view)
        await self.view.callback(*self.view.args)


class WithdrawalView(discordutils.CallbackPersistentView):
    def __init__(self, callback_key: str, link: str, *args):
        super().__init__(timeout=None, key=callback_key)
        self.args = args
        self.add_item(discordutils.LinkButton('Withdrawal Link', link))
        self.add_item(WithdrawalButton())

    def get_state(self) -> tuple:
        return self.children[0].url, *self.args  # type: ignore


class ResourceSelector(discord.ui.Select['ResourceSelectView']):
    def __init__(self, res: Iterable[str]):
        options = [discord.SelectOption(label=s) for s in res]
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
    def __init__(self, user_id: Optional[int] = None, res: Iterable[str] | None = None,
                 timeout: float = discordutils.Config.timeout):
        super().__init__(timeout=timeout)
        
        if res:
            res = set(res)
            assert res <= pnwutils.Constants.all_res
        else:
            res = pnwutils.Constants.all_res
        self._fut = asyncio.get_event_loop().create_future()
        self.user_id = user_id
        self.add_item(ResourceSelector(res))

    def set_result(self, r: list[str]) -> None:
        self._fut.set_result(r)

    def result(self) -> Awaitable[list[str]]:
        return self._fut

    async def on_timeout(self):
        if not self._fut.done():
            self._fut.set_exception(asyncio.TimeoutError())
