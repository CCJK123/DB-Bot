import datetime
import enum
from typing import Any, TypedDict

import discord

from . import link

# Setup what is exported by default
__all__ = ('WarType', 'war_description', 'mil_text', 'time_after_turns')


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


def war_description(w: dict[str, Any]) -> str:
    s = f'[War Page]({link.war(w["id"])})\n{w["war_type"].capitalize()} War\n\n'
    for k in WarType.ATT, WarType.DEF:
        n = w[k.string]
        a = n['alliance']
        aa_text = 'None' if a is None else f'[{a["name"]}]({link.alliance(a["id"])})'
        resist = w[f"{k.string_short}_resistance"]
        t, o = divmod(resist, 10)
        if not t:
            central = '🟧' if o >= 7 else '🟥'
        elif t == 10 or o >= 8:
            central = '🟩'
        elif o <= 3:
            central = '⬛'
        else:
            central = '🟧'
        bar = t * '🟩' + central + (9 - t) * '⬛'
        s += (f'{k.string.capitalize()}: [{n["nation_name"]}]'
              f'({link.nation(n["id"])})\n'
              f'{aa_text}\n\n'
              f'{bar} {resist} Resistance\n\n'
              f'{mil_text(n, w[f"{k.string_short}points"])}\n\n')
    return s


class MilDict(TypedDict):
    soldiers: int
    tanks: int
    aircraft: int
    ships: int
    missiles: int
    nukes: int


def mil_text(nation: MilDict, action_points: int | None = None) -> str:
    s = (f'{nation["soldiers"]} 🪖\n'
         f'{nation["tanks"]} :truck:\n'
         f'{nation["aircraft"]} ✈\n'
         f'{nation["ships"]} 🚢\n'
         f'{nation["missiles"]} 🚀\n'
         f'{nation["nukes"]} ☢️')
    return s if action_points is None else f'{action_points} ⚔️\n{s}'


def time_after_turns(turns):
    now = datetime.datetime.now()
    return discord.utils.format_dt(
        now + datetime.timedelta(hours=turns * 2 - now.hour % 2, minutes=-now.minute, seconds=-now.second)
    )
