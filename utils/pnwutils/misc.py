import enum
from typing import Any, TypedDict

from . import link

# Setup what is exported by default
__all__ = ('war_range', 'infra_value', 'infra_price', 'WarType', 'war_description', 'mil_text')


def war_range(score: str | float) -> tuple[float, float]:
    if isinstance(score, str):
        score = float(score)
    return score * 0.75, score * 1.75


def infra_value(infra_lvl: float):
    return 300 + abs(infra_lvl - 10) ** 2.2 / 710


def infra_price(start: float, end: float) -> float:
    if start == end:
        return 0

    diff = end - start
    if diff < 0:
        return 150 * diff
    if diff > 100 and (mod := diff % 100):
        return infra_value(start) * mod + infra_price(start + mod, end)
    if diff > 100:
        return infra_value(start) * 100 + infra_price(start + 100, end)
    return infra_value(start) * diff


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
            central = '🟧' if o >= 8 else '🟥'
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


def mil_text(nation: MilDict, action_points: int):
    return (f'{action_points} ⚔️\n'
            f'{nation["soldiers"]} 🪖\n'
            f'{nation["tanks"]} :truck:\n'
            f'{nation["aircraft"]} ✈\n'
            f'{nation["ships"]} 🚢\n'
            f'{nation["missiles"]} 🚀\n'
            f'{nation["nukes"]} ☢️')
