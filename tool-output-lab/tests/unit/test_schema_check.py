"""Layer 1's readers catch every kind of false claim an envelope's text could make."""

import random

from compressors.envelope import Role
from compressors.envelope_json import envelope
from evals.envelope_check import problems
from evals.schema_check import shape_claims, walk
from evals.truth import Number, promotes, score_fold


def _data() -> dict:
    rng = random.Random(4)
    pods = [{"name": f"web-{i:04d}x", "phase": "Running", "restarts": rng.randint(0, 3)} for i in range(200)]
    pods[9]["phase"] = pods[99]["phase"] = "Failed"
    return {"items": pods}


def _shape(data: dict) -> str:
    return "\n".join(envelope(data, frozenset(), 2000, view="schema").level(Role.SHAPE).body)


def test_a_true_envelope_has_no_false_claims():
    data = _data()
    assert problems("", data, envelope(data, frozenset(), 2000, view="schema"), run_jq=False) == []
    assert shape_claims(data, _shape(data)) == []


def test_a_false_count_a_false_unique_and_a_false_row_count_in_a_shape_are_each_caught():
    data = _data()
    shape = _shape(data)
    assert any(
        'says "Running" 199' in p for p in shape_claims(data, shape.replace('"Running" 198', '"Running" 199'))
    )
    assert any(
        "says unique" in p
        for p in shape_claims(data, shape.replace(".restarts  ", ".restarts  int, unique; ", 1))
    )
    assert shape_claims(data, shape.replace("array[200]", "array[201]"))


def test_walk_reads_jq_paths_and_iterates_arrays_and_objects():
    data = {"releases": {"1.0": [{"f": "a"}, {"f": "b"}], "2.0": [{"f": "c"}]}, "pod-list": [1, 2]}
    assert walk(data, ".releases[][].f") == ["a", "b", "c"]
    assert walk(data, '.releases["1.0"][1].f') == ["b"] and walk(data, '["pod-list"][0]') == [1]
    assert walk(data, ".missing.deeper") == []


def test_an_envelopes_anomalies_count_as_promotion_and_a_count_of_2_is_not_20():
    assert promotes(
        'shape:\n  .items: array[5] of object\nanomalies: 3 rows, all listed\n  .items[1] a: .phase "x"'
    )
    assert not promotes("shape:\n  .items: array[5] of object\nanomalies: none")
    truth = Number(2, frozenset(), ('"Failed" 2',))
    assert score_fold(truth, '.phase  "Running" 198, "Failed" 2').correct
    assert not score_fold(truth, '.phase  "Running" 180, "Failed" 20').correct
