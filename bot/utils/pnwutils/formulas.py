__all__ = ('war_range', 'inverse_war_range', 'spy_range', 'inverse_spy_range', 'infra_value', 'infra_price',
           'mil_values', 'round_odds', 'battle_odds', 'odds')


def war_range(score: float) -> tuple[float, float]:
    return score * 0.75, score * 1.75


def inverse_war_range(score: float) -> tuple[float, float]:
    return score * 4. / 7., score * 4. / 3


def spy_range(score: float) -> tuple[float, float]:
    return score * .4, score * 2.5


# 0.4 ^ -1 = 2.5, so inverse is same
inverse_spy_range = spy_range


def infra_value(infra_lvl: float) -> float:
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


def mil_values(n: dict) -> tuple[float, float, float]:
    return n['soldiers'] * 1.75 + n['tanks'] * 40, n['aircraft'] * 3, n['ships'] * 4


def round_odds(att_val: float, def_val: float) -> float:
    sample_space = att_val * def_val * .36
    x, y = (att_val, def_val) if att_val > def_val else (def_val, att_val)
    overlap = y - x * .4
    p = (overlap * overlap * 0.5) / sample_space
    return 1 - p if att_val > def_val else p


BattleOdds = tuple[float, float, float, float]


def battle_odds(att_val: float, def_val: float) -> BattleOdds:
    # pnw runs 3 rounds
    # each side rolls between 0.4 - 1 times unit value
    # defender wins ties
    if att_val <= 0 or att_val * 2.5 <= def_val:
        return 1, 0, 0, 0

    if def_val * 2.5 <= att_val:
        return 0, 0, 0, 1

    p = round_odds(att_val, def_val)
    q = 1 - p
    return tuple(p ** k * q ** (3 - k) * (1 + 2 * (k == 1 or k == 2)) for k in range(4))  # type: ignore


def odds(a: dict, d: dict) -> tuple[BattleOdds, BattleOdds, BattleOdds, BattleOdds, BattleOdds, BattleOdds]:
    ag, aa, an = mil_values(a)
    dg, da, dn = mil_values(d)
    return (battle_odds(ag, dg + d['population'] / 400), battle_odds(aa, da), battle_odds(an, dn),
            battle_odds(dg, ag + a['population'] / 400), battle_odds(da, aa), battle_odds(ag, dg))
