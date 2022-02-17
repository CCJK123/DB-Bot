import enum
import datetime
from dataclasses import dataclass
from typing import Iterable, TypedDict

import discord

from . import constants
from .. import config


__all__ = ('Resources', 'ResourceDict', 'Transaction', 'TransactionType')


class ResourceDict(TypedDict, total=False):
    money: int
    food: int
    coal: int
    oil: int
    uranium: int
    lead: int
    iron: int
    bauxite: int
    gasoline: int
    munitions: int
    steel: int
    aluminum: int


# Setup resource types and relevant methods
@dataclass
class Resources:
    money: int = 0
    food: int = 0
    coal: int = 0
    oil: int = 0
    uranium: int = 0
    lead: int = 0
    iron: int = 0
    bauxite: int = 0
    gasoline: int = 0
    munitions: int = 0
    steel: int = 0
    aluminum: int = 0

    # Output all resources with values associated
    def to_dict(self) -> ResourceDict:
        return {
            res_name: res_amount
            for res_name in constants.all_res
            if (res_amount := self[res_name])
        }

    def create_embed(self, **kwargs: str) -> discord.Embed:
        embed = discord.Embed(**kwargs)
        for name, amt in self:
            embed.add_field(name=name.title(), value=amt)
        if self or kwargs:
            return embed
        raise ValueError('The embed is empty and cannot be sent!')

    def create_balance_embed(self, receiver: str) -> discord.Embed:
        if self:
            return self.create_embed(title=f"{receiver}'s Balance")
        return discord.Embed(title=f"{receiver}'s Balance", description='Hmm... Nothing here')

    def all_positive(self) -> bool:
        return all(a >= 0 for a in self.values())

    def keys_nonzero(self) -> Iterable[str]:
        return (res_name for res_name in constants.all_res if self[res_name])

    def values_nonzero(self) -> Iterable[int]:
        return (amt for res_name in constants.all_res if (amt := self[res_name]))

    def values(self) -> Iterable[int]:
        return (self[res_name] for res_name in constants.all_res)

    def __getitem__(self, key) -> int:
        if key in constants.all_res:
            return getattr(self, key)
        raise KeyError(f'{key} is not a resource!')

    def __setitem__(self, key, value) -> None:
        if key in constants.all_res:
            setattr(self, key, value)
            return
        raise KeyError(f'{key} is not a resource!')

    def __str__(self) -> str:
        return '\n'.join(f'{config.resource_emojis[res_name]} {res_amt}' for res_name, res_amt in self)

    def __bool__(self) -> bool:
        return bool(self.to_dict())

    def __iter__(self):
        return iter(self.to_dict().items())

    def __add__(self, other):
        if isinstance(other, Resources):
            r = Resources()
            for name in constants.all_res:
                r[name] = self[name] + other[name]
            return r
        return NotImplemented

    def __iadd__(self, other):
        if isinstance(other, Resources):
            for name in constants.all_res:
                self[name] += other[name]
            return self
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Resources):
            r = Resources()
            for name in constants.all_res:
                r[name] = self[name] - other[name]
            return r
        return NotImplemented

    def __isub__(self, other):
        if isinstance(other, Resources):
            for name in constants.all_res:
                self[name] -= other[name]
            return self
        return NotImplemented


class TransactionType(enum.Enum):
    dep = 0
    rec = 1
    a_dep = 2
    a_rec = 3


@dataclass(slots=True)
class Transaction:
    resources: Resources
    time: datetime.datetime
    kind: TransactionType
    entity_id: str

    @classmethod
    def from_api_dict(cls, data: dict) -> 'Transaction':
        res = Resources(**{k: data[k] for k in data.keys() if k in constants.all_res})
        t = datetime.datetime.fromisoformat(data['date'])

        if data['stype'] == 2 and data['sid'] == config.alliance_id:
            # sender is our alliance
            kind = TransactionType.rec if data['rtype'] == 1 else TransactionType.a_rec
            entity_id = data['rid']
        else:
            # receiver is our alliance
            kind = TransactionType.dep if data['stype'] == 1 else TransactionType.a_dep
            entity_id = data['sid']

        return cls(res, t, kind, entity_id)
