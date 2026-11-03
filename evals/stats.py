"""Intervals for the layer-2 report: Wilson for accuracy, Newcombe's interval and McNemar's test for
paired accuracy, and a seeded bootstrap for paired differences in cost, context and time."""

import math
import random
import statistics
from collections.abc import Callable, Sequence


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval for k successes in n trials (95% by default)."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float] = statistics.median,
    iters: int = 2000,
    seed: int = 0,
) -> tuple[float, float, float]:
    """The statistic of the values, with a 95% percentile-bootstrap interval (deterministic seed)."""
    if not values:
        return math.nan, math.nan, math.nan
    rng = random.Random(seed)
    resampled = sorted(stat([rng.choice(values) for _ in values]) for _ in range(iters))
    return stat(values), resampled[int(0.025 * iters)], resampled[int(0.975 * iters) - 1]


def paired(a: dict[str, float], b: dict[str, float]) -> list[float]:
    """b - a for every key both have (the same task and repetition under two conditions)."""
    return [b[k] - a[k] for k in sorted(a.keys() & b.keys())]


def _binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def paired_accuracy(both: int, gains: int, losses: int, neither: int) -> tuple[float, float, float, float]:
    """The accuracy change over paired runs (`gains` pairs right only under the condition, `losses`
    only under native), its 95% interval by Newcombe's method 10 (the two rates' Wilson intervals,
    combined through their correlation), and McNemar's exact two-sided p.

    Not a bootstrap: with few discordant pairs it is too sure (4 gains and no losses can never
    resample to a loss, so its interval excludes zero although p is 0.125). Not an interval
    conditioned on the discordant count either: that one caps the change at the share of pairs that
    differ, and claims [0, 0] when none do."""
    n = both + gains + losses + neither
    if n == 0:
        return math.nan, math.nan, math.nan, 1.0
    change, p1, p2 = (gains - losses) / n, (both + gains) / n, (both + losses) / n
    (l1, u1), (l2, u2) = wilson(both + gains, n), wilson(both + losses, n)
    spread = (both + gains) * (losses + neither) * (both + losses) * (gains + neither)
    phi = (both * neither - gains * losses) / math.sqrt(spread) if spread else 0.0
    below = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    above = math.sqrt(max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
    m = gains + losses
    p = 1.0 if m == 0 else min(1.0, 2 * _binomial_cdf(min(gains, losses), m, 0.5))
    return change, change - below, change + above, p
