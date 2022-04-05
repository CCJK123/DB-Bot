__all__ = ('war_range', 'inverse_war_range', 'spy_range', 'inverse_spy_range', 'infra_value', 'infra_price',)


def war_range(score: float) -> tuple[float, float]:
    return score * 0.75, score * 1.75


def inverse_war_range(score: float) -> tuple[float, float]:
    return score * 4. / 7., score * 4. / 3


def spy_range(score: float) -> tuple[float, float]:
    return score * .4, score * 2.5


# 0.4 ^ -1 = 2.5, so inverse is same
inverse_spy_range = spy_range


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
