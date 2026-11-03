"""The compressor's knobs: set by name, checked, named in reports, and they change the fold."""

import re

import pytest

from compressors.config import DEFAULT, changes, label, sets, with_sets, with_values
from compressors.schema import schema_view


def test_knobs_are_set_by_dotted_name_and_typed_by_their_default():
    config = with_sets(DEFAULT, ["schema.rare=0.15", "tree.max_promoted=4", "worth_it=0.8"])
    assert (config.schema.rare, config.tree.max_promoted, config.worth_it) == (0.15, 4, 0.8)
    assert with_values(DEFAULT, {"schema.rows": 10}).schema.rows == 10
    assert config.schema.dominant == DEFAULT.schema.dominant  # the rest stay as they were


def test_a_wrong_knob_or_value_says_what_would_be_right():
    with pytest.raises(
        ValueError, match=re.escape("no knob 'schema.rarity'; the knobs are: worth_it, schema.dominant")
    ):
        with_sets(DEFAULT, ["schema.rarity=0.1"])
    with pytest.raises(ValueError, match=re.escape("tree.max_promoted takes a int, not 'many'")):
        with_sets(DEFAULT, ["tree.max_promoted=many"])
    with pytest.raises(ValueError, match="--set takes NAME=VALUE"):
        with_sets(DEFAULT, ["schema.rare"])


def test_a_config_is_named_by_what_it_changes_and_rebuilt_from_its_sets():
    config = with_sets(DEFAULT, ["schema.rare=0.15", "tree.min_gap=8"])
    assert label(DEFAULT) == "defaults" and changes(DEFAULT) == {}
    assert label(config) == "schema.rare=0.15, tree.min_gap=8"
    assert with_sets(DEFAULT, sets(config)) == config


def test_a_knob_changes_what_the_view_shows():
    pods = [{"name": f"p{i:03d}x", "phase": "Failed" if i < 12 else "Running"} for i in range(100)]
    default = schema_view(pods, frozenset(), 2000)
    wider = schema_view(pods, frozenset(), 2000, knobs=with_sets(DEFAULT, ["schema.rare=0.15"]).schema)
    assert "exceptions" not in default  # 12 of 100 is not rare at 10%
    assert "exceptions in 12 rows:" in wider
