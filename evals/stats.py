"""Intervals for the layer-2 report: Wilson for accuracy, a seeded bootstrap for paired differences."""

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
