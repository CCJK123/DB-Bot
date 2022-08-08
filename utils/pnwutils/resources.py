from __future__ import annotations

import math
from collections.abc import Iterable, ItemsView
from dataclasses import dataclass
from typing import ClassVar, TypedDict

import discord

from utils import config, discordutils

__all__ = ('ResourceDict', 'Resources')


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
    all_res: ClassVar[tuple[str, ...]] = (
        'money', 'food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite',
        'gasoline', 'munitions', 'steel', 'aluminum')

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

    @classmethod
    def from_dict(cls, d):
        """Makes an instance of this class from a dictionary, ignoring other keys"""
        return cls(**{k: d[k] for k in d.keys() if k in cls.all_res})

    # Output all resources with values associated
    def to_dict(self) -> ResourceDict:
        """
        Write a dictionary with equivalent values.
        You can convert this dict back into `pnwutils.Resources` by passing it as `pnwutils.Resources(**resource_dict)`.
        """
        return {
            res_name: res_amount
            for res_name in self.all_res
            if (res_amount := self[res_name])
        }

    def to_row(self) -> str:
        return f'ROW({",".join(map(str, self.values()))})'

    def create_embed(self, **kwargs: object) -> discord.Embed:
        embed = discordutils.create_embed(**kwargs)
        for name, amt in self:
            embed.add_field(name=name.title(), value=f'{config.resource_emojis[name]} {round(amt, 2):,}')
        if self or kwargs:
            return embed
        raise ValueError('The embed is empty and cannot be sent!')

    def create_balance_embed(self, user: discord.Member | discord.User) -> discord.Embed:
        if self:
            return self.create_embed(user=user, description=f"{user.mention}'s Balance")
        return discordutils.create_embed(user=user, description=f"{user.mention}'s Balance").add_field(
            name='Hmm...', value='Nothing Here')

    def all_positive(self) -> bool:
        return all(a >= 0 for a in self.values())

    def keys_nonzero(self) -> Iterable[str]:
        """Returns an iterable of all the resource keys for which the value is not zero."""
        return (res_name for res_name in self.all_res if self[res_name])

    def values_nonzero(self) -> Iterable[int]:
        """Returns an iterable of all the resource values for which the value is not zero."""
        return (amt for res_name in self.all_res if (amt := self[res_name]))

    def items_nonzero(self) -> ItemsView[str, int]:
        return self.to_dict().items()

    @classmethod
    def keys(cls) -> Iterable[str]:
        """Returns an iterable of all the resource keys. Equal to `constants.all_res`"""
        return cls.all_res

    def values(self) -> Iterable[int]:
        """Returns an iterable of all the resource values."""
        return (self[res_name] for res_name in self.all_res)

    def __getitem__(self, key) -> int:
        if key in self.all_res:
            return getattr(self, key)
        raise KeyError(f'{key} is not a resource!')

    def __setitem__(self, key, value) -> None:
        if key in self.all_res:
            setattr(self, key, value)
            return
        raise KeyError(f'{key} is not a resource!')

    def to_string(self, connector: str):
        return connector.join(f'{config.resource_emojis[res_name]} {res_amt:,}' for res_name, res_amt in self)

    def __str__(self) -> str:
        return self.to_string('\n')

    def __bool__(self) -> bool:
        return bool(self.to_dict())

    def __iter__(self):
        return iter(self.items_nonzero())

    def __add__(self, other):
        if isinstance(other, Resources):
            r = Resources()
            for name in self.all_res:
                r[name] = self[name] + other[name]
            return r
        return NotImplemented

    def __iadd__(self, other):
        if isinstance(other, Resources):
            for name in self.all_res:
                self[name] += other[name]
            return self
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Resources):
            r = Resources()
            for name in self.all_res:
                r[name] = self[name] - other[name]
            return r
        return NotImplemented

    def __isub__(self, other):
        if isinstance(other, Resources):
            for name in self.all_res:
                self[name] -= other[name]
            return self
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            r = Resources()
            for name in self.all_res:
                r[name] = int(self[name] * other)
            return r
        return NotImplemented

    def __imul__(self, other):
        if isinstance(other, (int, float)):
            for name in self.all_res:
                self[name] = int(self[name] * other)
            return self
        return NotImplemented

    def floor_values(self) -> 'Resources':
        """Replace every amount with a floored version, and returns self."""
        for k in self.all_res:
            self[k] = math.floor(self[k])
        return self
