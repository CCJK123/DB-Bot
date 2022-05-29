from __future__ import annotations

import asyncio
import datetime
import pickle
from typing import Awaitable, Iterable, TypedDict
from dataclasses import dataclass, field

import discord

from . import pnwutils, config

__all__ = ('RequestData', 'LoanData', 'withdrawal_embed', 'ResourceSelectView')


@dataclass()
class RequestData:
    requester: discord.abc.User | None = None
    nation_id: int = 0
    nation_name: str = ''
    kind: str = ''
    reason: str = ''
    resources: pnwutils.Resources = field(default_factory=pnwutils.Resources)
    note: str = ''
    additional_info: dict[str, str] = field(default_factory=dict)
    _requester_id: int | None = None

    @property
    def nation_link(self):
        return pnwutils.link.nation(self.nation_id)

    @property
    def requester_id(self):
        if self._requester_id is None:
            self._requester_id = self.requester.id
        return self._requester_id

    def create_embed(self, **kwargs) -> discord.Embed:
        embed = discord.Embed(**kwargs)
        embed.add_field(name='Nation', value=f'[{self.nation_name}]({self.nation_link})')
        embed.add_field(name='Request Type', value=self.kind)
        embed.add_field(name='Reason', value=self.reason)
        embed.add_field(name='Requested Resources', value=str(self.resources))
        for n, v in self.additional_info.items():
            embed.add_field(name=n, value=v)
        return embed

    def create_link(self) -> str:
        return pnwutils.link.bank("w", self.resources, self.nation_name,
                                  self.note if self.note else self.reason if self.kind != 'War Aid' else 'War Aid')

    def create_withdrawal_embed(self, **kwargs) -> discord.Embed:
        return withdrawal_embed(self.nation_name, self.nation_id, self.reason, self.resources, **kwargs)

    def create_withdrawal(self) -> pnwutils.Withdrawal:
        return pnwutils.Withdrawal(self.resources, self.nation_id, pnwutils.EntityType.NATION, self.note)

    def __getstate__(self) -> tuple:
        return (0, self.requester_id, self.nation_id, self.nation_name, self.kind, self.reason,
                self.resources.to_dict(), self.note, self.additional_info)

    def __setstate__(self, state):
        if state[0] == 0:
            (_, self._requester_id, self.nation_id, self.nation_name, self.kind,
             self.reason, res_dict, self.note, self.additional_info) = state
            self.resources = pnwutils.Resources(**res_dict)
            self.requester = None
        else:
            raise pickle.UnpicklingError(f'Unrecognised state version {state[0]} for RequestData')

    def set_requester(self, client: discord.Client) -> discord.abc.User:
        """Used to set the requester attribute using the client, after unpickling, as the requester is not saved."""
        self.requester = client.get_user(self.requester_id)
        return self.requester


class LoanDataDict(TypedDict):
    due_date: str
    loaned: pnwutils.ResourceDict


class LoanData:
    __slots__ = ('due_date', 'loaned')

    def __init__(self, due_date: str | datetime.datetime, loaned: pnwutils.Resources | pnwutils.ResourceDict):
        if isinstance(due_date, str):
            self.due_date = datetime.datetime.fromisoformat(due_date)
        else:
            self.due_date = due_date

        if isinstance(loaned, pnwutils.Resources):
            self.loaned = loaned
        else:
            self.loaned = pnwutils.Resources(**loaned)

    @property
    def display_date(self) -> str:
        return discord.utils.format_dt(self.due_date, 'f')

    def to_dict(self) -> LoanDataDict:
        return {'due_date': self.due_date.isoformat(), 'loaned': self.loaned.to_dict()}

    def to_embed(self, **kwargs: str) -> discord.Embed:
        embed = self.loaned.create_embed(**kwargs)
        embed.insert_field_at(0, name='Due Date', value=self.display_date)
        return embed


def withdrawal_embed(name: str, nation_id: str | int, reason: str, resources: pnwutils.Resources,
                     **kwargs) -> discord.Embed:
    embed = discord.Embed(colour=discord.Colour.blue(), **kwargs)
    embed.add_field(name='Nation', value=f'[{name}]({pnwutils.link.nation(nation_id)})')
    embed.add_field(name='Reason', value=reason)
    embed.add_field(name='Requested Resources', value=str(resources))
    return embed


# noinspection PyAttributeOutsideInit
class ResourceSelector(discord.ui.Select['ResourceSelectView']):
    def __init__(self, res: Iterable[str]):
        options = [discord.SelectOption(label=s, emoji=config.resource_emojis[s]) for s in res]
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
    def __init__(self, user_id: int | None = None, res: Iterable[str] | None = None,
                 timeout: float = config.timeout):
        super().__init__(timeout=timeout)

        if res:
            res = set(res)
            assert res <= set(pnwutils.Resources.all_res)
        else:
            res = pnwutils.Resources.all_res
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
