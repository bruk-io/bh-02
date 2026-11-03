"""The sweep's grid: every combination of its axes over the base, budget and view among them."""

import pytest

from evals.sweep import points


def test_every_combination_of_the_axes_is_a_point_over_the_base():
    spec = {"base": {"view": "schema"}, "grid": {"schema.rare": [0.05, 0.15], "budget": [500, 2000]}}
    got = points(spec)
    assert [(p.config.schema.rare, p.budget, p.view) for p in got] == [
        (0.05, 500, "schema"),
        (0.05, 2000, "schema"),
        (0.15, 500, "schema"),
        (0.15, 2000, "schema"),
    ]
    assert got[0].axes == (("schema.rare", 0.05), ("budget", 500))


def test_a_spec_without_a_grid_or_with_a_bad_axis_says_what_to_write():
    with pytest.raises(ValueError, match=r"needs a \[grid\]"):
        points({"base": {}})
    with pytest.raises(ValueError, match="needs a list of values"):
        points({"grid": {"schema.rare": 0.1}})
    with pytest.raises(ValueError, match="no knob"):
        points({"grid": {"schema.rarity": [0.1]}})
    with pytest.raises(ValueError, match="view 'outline' is none of sample, schema"):
        points({"grid": {"view": ["outline"]}})
