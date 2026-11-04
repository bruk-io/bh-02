"""The compressor's knobs: set by name, checked, named in reports, and they change the fold."""

import re

import pytest

from compressors.config import DEFAULT, changes, label, sets, with_sets, with_values
from compressors.envelope_json import envelope


def test_knobs_are_set_by_dotted_name_and_typed_by_their_default():
    config = with_sets(DEFAULT, ["schema.rare=0.15", "tree_envelope.min_items=4", "worth_it=0.8"])
    assert (config.schema.rare, config.tree_envelope.min_items, config.worth_it) == (0.15, 4, 0.8)
    assert with_values(DEFAULT, {"schema.rows": 10}).schema.rows == 10
    assert config.schema.dominant == DEFAULT.schema.dominant  # the rest stay as they were


def test_a_wrong_knob_or_value_says_what_would_be_right():
    with pytest.raises(
        ValueError, match=re.escape("no knob 'schema.rarity'; the knobs are: worth_it, schema.dominant")
    ):
        with_sets(DEFAULT, ["schema.rarity=0.1"])
    with pytest.raises(ValueError, match=re.escape("tree_envelope.min_items takes a int, not 'many'")):
        with_sets(DEFAULT, ["tree_envelope.min_items=many"])
    with pytest.raises(ValueError, match="--set takes NAME=VALUE"):
        with_sets(DEFAULT, ["schema.rare"])


def test_a_config_is_named_by_what_it_changes_and_rebuilt_from_its_sets():
    config = with_sets(DEFAULT, ["schema.rare=0.15", "log_envelope.few=8"])
    assert label(DEFAULT) == "defaults" and changes(DEFAULT) == {}
    assert label(config) == "schema.rare=0.15, log_envelope.few=8"
    assert with_sets(DEFAULT, sets(config)) == config


def test_a_knob_changes_what_the_view_shows():
    pods = [{"name": f"p{i:03d}x", "phase": "Failed" if i < 12 else "Running"} for i in range(100)]
    default = envelope(pods, frozenset(), 2000, view="schema").text()
    wider = envelope(pods, frozenset(), 2000, config=with_sets(DEFAULT, ["schema.rare=0.15"]), view="schema")
    assert "anomalies: none" in default  # 12 of 100 is not rare at 10%
    assert "anomalies: 12 rows, all listed" in wider.text()
