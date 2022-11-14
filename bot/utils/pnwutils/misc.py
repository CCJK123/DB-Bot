from __future__ import annotations

import datetime
import enum
from typing import Any, TypedDict

import aiohttp
import discord

from . import link
from .. import config

from ..queries import offshore_info_query

# Setup what is exported by default
__all__ = ('WarType', 'get_bar', 'find_end_attack', 'war_description', 'mil_text', 'time_after_turns',
           'get_offshore_id')


class WarType(enum.Enum):
    def __init__(self, v):
        if v:
            self.string = 'attacker'
            self.string_short = 'att'
        else:
            self.string = 'defender'
            self.string_short = 'def'

    ATT = True
    DEF = False


def get_bar(resist: int):
    if resist:
        t, o = divmod(resist, 10)
        if not t:
            central = '🟧' if o >= 7 else '🟥'
        elif t == 10 or o >= 8:
            central = '🟩'
        elif o <= 3:
            central = '⬛'
        else:
            central = '🟧'
        return t * '🟩' + central + (9 - t) * '⬛'
    return '⬛' * 10


def find_end_attack(w: dict[str, Any]) -> dict | None:
    return discord.utils.find(lambda attack: attack['type'] in ('VICTORY', 'PEACE'), w['attacks'])


sen = object


def war_description(w: dict[str, Any], end_attack: dict | None | object = sen) -> str:
    s = f'[War Page]({link.war(w["id"])})\n{w["war_type"].capitalize()} War\n\n'
    if end_attack is sen:
        end_attack = find_end_attack(w)
    if end_attack is None and w['turns_left'] > 0:
        # ongoing war
        for k in WarType.ATT, WarType.DEF:
            n = w[k.string]
            a = n['alliance']
            resist = w[f"{k.string_short}_resistance"]
            s += (f'{k.string.capitalize()}: [{n["nation_name"]}]({link.nation(n["id"])}) ({n["num_cities"]} 🏙)\n' +
                  ('None\n' if a is None else f'[{a["name"]}]({link.alliance(a["id"])}) ') +
                  (f'(Applicant)\n' if n["alliance_position"] == 'APPLICANT' else '\n') +
                  f'War Policy: {n["war_policy"]}\n\n'
                  f'{get_bar(resist)} {resist:3d} Resistance\n\n'
                  f'{mil_text(n, w[f"{k.string_short}_points"])}\n\n')
        return s

    for k in WarType.ATT, WarType.DEF:
        n = w[k.string]
        resist = w[f"{k.string_short}_resistance"]
        s += (f'{k.string.capitalize()}: [{n["nation_name"]}]({link.nation(n["id"])})\n\n'
              f'{get_bar(resist)} {resist:3d} Resistance\n\n')
    if end_attack is None:
        # expired war
        end_time = discord.utils.format_dt(datetime.datetime.fromisoformat(w['date']) +
                                           datetime.timedelta(days=5))
        s += f'The conflict expired at {end_time}.'
    else:
        end_time = discord.utils.format_dt(datetime.datetime.fromisoformat(end_attack['date']))

        s += (f'Truce was agreed upon at {end_time}.' if end_attack['type'] == 'PEACE' else
              f'The war was won by the {"defender" if w["winner_id"] == n else "attacker"} at {end_time}.')
    return s


class MilDict(TypedDict):
    soldiers: int
    tanks: int
    aircraft: int
    ships: int
    missiles: int
    nukes: int


def mil_text(nation: MilDict, action_points: int | None = None) -> str:
    a = f'{action_points} ⚔️' if action_points is None else ''
    return (
        f'```{a}'
        f'{nation["soldiers"]} 💂 '
        f'{nation["tanks"]} 🚚 '
        f'{nation["aircraft"]}✈️ '
        f'{nation["ships"]}🚢  '
        f'{nation["missiles"]}🚀 '
        f'{nation["nukes"]}☢️```')


def time_after_turns(turns):
    now = datetime.datetime.now()
    return discord.utils.format_dt(
        now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=turns * 2 - now.hour % 2)
    )


async def get_offshore_id(session: aiohttp.ClientSession):
    data = await offshore_info_query.query(session, api_key=config.offshore_api_key)
    return data['nation']['alliance_id']
