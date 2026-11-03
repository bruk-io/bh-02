import statistics

from evals.stats import bootstrap, paired, wilson


def test_wilson_matches_known_values():
    lo, hi = wilson(13, 14)
    assert round(lo, 3) == 0.685 and round(hi, 3) == 0.987  # the interval the review quoted
    assert wilson(0, 0) == (0.0, 1.0)


def test_bootstrap_is_deterministic_and_brackets_the_statistic():
    values = [float(x) for x in range(-20, 41)]
    m, lo, hi = bootstrap(values)
    assert m == statistics.median(values) and lo <= m <= hi
    assert bootstrap(values) == (m, lo, hi)
    mean, lo, hi = bootstrap([1.0] * 10, statistics.mean)
    assert (mean, lo, hi) == (1.0, 1.0, 1.0)


def test_paired_differences_use_only_shared_keys():
    assert paired({"a": 1, "b": 2, "c": 5}, {"a": 3, "c": 1, "d": 9}) == [2, -4]
