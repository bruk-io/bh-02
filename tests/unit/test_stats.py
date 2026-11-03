import math
import statistics

from evals.stats import bootstrap, paired, paired_accuracy, wilson


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


def test_paired_accuracy_mirrors_scales_and_reduces_to_wilson_when_uncorrelated():
    change, lo, hi, p = paired_accuracy(12, 9, 2, 21)
    assert lo < change < hi and round(p, 4) == 0.0654  # McNemar: 2 * (1 + 11 + 55) / 2**11
    mirrored = paired_accuracy(12, 2, 9, 21)
    assert math.isclose(mirrored[1], -hi) and math.isclose(mirrored[2], -lo)
    _, lo4, hi4, _ = paired_accuracy(48, 36, 8, 84)  # the same table, four times the pairs
    assert 0.4 < (hi4 - lo4) / (hi - lo) < 0.6
    _, lo0, hi0, _ = paired_accuracy(25, 25, 25, 25)  # both*neither == gains*losses: no correlation
    (l1, u1), (l2, u2) = wilson(50, 100), wilson(50, 100)
    assert math.isclose(lo0, -math.hypot(0.5 - l1, u2 - 0.5))
    assert math.isclose(hi0, math.hypot(u1 - 0.5, 0.5 - l2))


def test_paired_accuracy_is_not_sure_of_a_gain_four_pairs_show_nor_of_no_change():
    change, lo, hi, p = paired_accuracy(96, 4, 0, 4)  # P2's control: in effect the same condition twice
    assert round(change, 3) == 0.038 and lo < 0 < hi and p == 0.125
    change, lo, hi, p = paired_accuracy(87, 8, 1, 8)
    assert lo > 0 and round(p, 3) == 0.039
    _, lo, hi, p = paired_accuracy(104, 0, 0, 0)  # every pair agrees: still not certain of 0
    assert lo < -0.03 < 0.03 < hi and p == 1.0
