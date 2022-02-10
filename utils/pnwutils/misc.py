from typing import TypedDict

# Setup what is exported by default
__all__ = ('war_range', 'infra_value', 'infra_price', 'mil_text')


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
