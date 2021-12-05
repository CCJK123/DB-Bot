from __future__ import annotations

import datetime
import enum
from typing import Any, Final, Iterable, Literal, Optional, Union
import aiohttp
from dataclasses import dataclass
from itertools import chain
import os  # For env variables

import discord

# Setup what is exported by default
__all__ = ('Config', 'Constants', 'Resources', 'Link')


# Setup API configuration variables
class Config:
    api_key: str = '6b6a6ab065a851' or os.environ['api_key']
    aa_id: str = '4221'
    aa_name: str = 'Dark Brotherhood'


# Setup API & P&W constants
class Constants:
    base_url: Final[str] = 'https://politicsandwar.com/'
    base_api_url: Final[str] = 'https://api.politicsandwar.com/graphql?api_key='
    api_url: Final[str] = base_api_url + Config.api_key
    all_res: Final[tuple[str, ...]] = ('money', 'food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite',
                                       'gasoline', 'munitions', 'steel', 'aluminum')


class APIError(Exception):
    """Error raised when an exception occurs when trying to call the API."""


# Setup API
class API:
    __slots__ = ()

    # Combine query string & variables into a query json
    @staticmethod
    def construct_query(q: str, var: dict[str, Any]) -> dict[str, Union[str, dict[str, Any]]]:
        return {'query': q, 'variables': var}

    # Send query to P&W servers and return response
    @classmethod
    async def post_query(cls,
                         sess: aiohttp.ClientSession,
                         query_string: str,
                         query_variables: dict[str, Any],
                         query_type: str,
                         check_more: bool = False
                         ) -> Union[Iterable[dict[str, Any]], dict[str, Any]]:

        # "alex put a limit of 500 entries returned per call, check_more decides if i should try check if i should be
        # getting the next 500 entries" - chez
        # Set page to first page if more entries than possible in 1 call wanted
        if check_more and query_variables.get('page') is None:
            query_variables['page'] = 1

        # Create query and get data
        query = cls.construct_query(query_string, query_variables)
        async with sess.post(Constants.api_url, json=query) as response:
            data = await response.json()
        if 'data' not in data.keys():
            raise APIError(f'Error in fetching data: {data["errors"]}')
        data = data['data'][query_type]
        # Get data from other pages, if they exist
        if check_more and data['paginatorInfo']['hasMorePages']:
            query_variables = query_variables.copy()
            query_variables['page'] += 1

            # linter does not realise that in this case, the post_query call will always return Iterable[dict[str, Any]]
            return chain(data, await cls.post_query(sess, query_string, query_variables, query_type, True))

        return data


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

    def to_dict(self) -> dict[str, int]:
        return {
            res_name: self[res_name]
            for res_name in Constants.all_res
        }

    # Output all resources with values associated
    def nonzero_resources(self) -> dict[str, int]:
        return {
            res_name: res_amount
            for res_name in Constants.all_res
            if (res_amount := self[res_name])
        }

    def create_embed(self, **kwargs: str) -> discord.Embed:
        embed = discord.Embed(**kwargs)
        for n, a in self.nonzero_resources().items():
            embed.add_field(name=n, value=a)
        return embed

    def __getitem__(self, key):
        if key in Constants.all_res:
            return getattr(self, key)
        raise KeyError(f'{key} is not a resource!')

    def __setitem__(self, key, value):
        if key in Constants.all_res:
            setattr(self, key, value)
        raise KeyError(f'{key} is not a resource!')

    def __str__(self) -> str:
        return '\n'.join(f'{res_name.title()}: {res_amt}' for res_name, res_amt in self.nonzero_resources().items())

    def __bool__(self) -> bool:
        try:
            next(self.nonzero_resources())
        except StopIteration:
            return False
        return True

    def __add__(self, other):
        if isinstance(other, Resources):
            r = Resources()
            for name in Constants.all_res:
                r[name] = self[name] + other[name]
            return r
        return NotImplemented

    def __iadd__(self, other):
        if isinstance(other, Resources):
            for name in Constants.all_res:
                self[name] = self[name] + other[name]
            return self
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Resources):
            r = Resources()
            for name in Constants.all_res:
                r[name] = self[name] - other[name]
            return r
        return NotImplemented

    def __isub__(self, other):
        if isinstance(other, Resources):
            for name in Constants.all_res:
                self[name] = self[name] - other[name]
            return self
        return NotImplemented


class TransactionType(enum.Enum):
    dep = 0
    rec = 1
    a_dep = 2
    a_rec = 3


@dataclass
class Transaction:
    contents: Resources
    time: datetime.datetime
    kind: TransactionType
    entity_id: str

    @classmethod
    def from_api_dict(cls, data: dict) -> Transaction:
        res = Resources(**{k: data[k] for k in data.keys() if k in Constants.all_res})
        time = datetime.datetime.fromisoformat(data['date'])

        if data['stype'] == 2 and data['sid'] == Config.aa_id:
            # sender is our alliance
            kind = TransactionType.rec if data['rtype'] == 1 else TransactionType.a_rec
            entity_id = data['rid']
        else:
            # receiver is our alliance
            kind = TransactionType.dep if data['stype'] == 1 else TransactionType.a_dep
            entity_id = data['sid']

        return cls(res, time, kind, entity_id)


class Link:
    __slots__ = ()

    @staticmethod
    def nation(nation_id: str) -> str:
        return f'{Constants.base_url}nation/id={nation_id}'

    @staticmethod
    def alliance(alliance_id: Optional[str] = None) -> str:
        if alliance_id is None:
            alliance_id = Config.aa_id
        return f'{Constants.base_url}alliance/id={alliance_id}'

    @classmethod
    def bank(cls, kind: Literal['w', 'd', 'wa'], res: Optional[Resources] = None,
             recipient: Optional[str] = None, note: Optional[str] = None) -> str:
        if kind == 'd' and recipient is not None:
            raise ValueError('Do not provide recipient for deposits!')

        # Check if withdrawing to alliance
        with_aa = False
        if kind == 'wa':
            with_aa = True
            kind = 'w'

        # Add parameters to withdrawal / deposit url
        link = f'{Link.alliance()}&display=bank'
        if res is not None:
            for res_name, res_amt in res.nonzero_resources().items():
                link += f'&{kind}_{res_name}={res_amt}'
        if note is not None:
            link += f'&{kind}_note={note.replace(" ", "%20")}'
        if with_aa:
            link += '&w_type=alliance'
        if recipient is not None:
            # Replace spaces with url encoding for spaces
            link += f'&w_recipient={recipient.replace(" ", "%20")}'
        return link

    @staticmethod
    def war(war_id: str) -> str:
        return f'{Constants.base_url}nation/war/timeline/war={war_id}'


def war_range(score: Union[str, float]) -> tuple[float, float]:
    if isinstance(score, str):
        score = float(score)
    return score * 0.75, score * 1.75
