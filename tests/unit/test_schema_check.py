"""Layer 1's check of a schema view catches every kind of false claim."""

import random

from compressors.schema import schema_view
from evals.schema_check import claims, walk
from evals.truth import Number, promotes, score_fold


def _data() -> dict:
    rng = random.Random(4)
    pods = [{"name": f"web-{i:04d}x", "phase": "Running", "restarts": rng.randint(0, 3)} for i in range(200)]
    pods[9]["phase"] = pods[99]["phase"] = "Failed"
    return {"items": pods}


def test_a_true_view_has_no_false_claims():
    data = _data()
    assert claims(data, schema_view(data, frozenset(), 2000)) == []


def test_a_false_count_a_false_unique_a_false_range_and_a_false_note_are_each_caught():
    data = _data()
    view = schema_view(data, frozenset(), 2000)
    assert any(
        'says "Running" 199' in p for p in claims(data, view.replace('"Running" 198', '"Running" 199'))
    )
    assert any(
        "says unique" in p
        for p in claims(
            data,
            view.replace(".restarts  ", ".restarts  int, unique; ", 1).replace(
                "int, unique; 0", "int, unique; 0"
            ),
        )
    )
    assert claims(
        data, view.replace('.items[9] web-0009x: .phase "Failed"', '.items[9] web-0009x: .phase "Pending"')
    )
    assert claims(data, view.replace("array[200]", "array[201]"))


def test_a_row_left_out_of_an_uncut_exception_list_is_caught():
    data = _data()
    view = schema_view(data, frozenset(), 2000)
    dropped = "\n".join(line for line in view.splitlines() if ".items[99]" not in line)
    assert any('row 99 holds .phase "Failed" and is not listed' in p for p in claims(data, dropped))


def test_walk_reads_jq_paths_and_iterates_arrays_and_objects():
    data = {"releases": {"1.0": [{"f": "a"}, {"f": "b"}], "2.0": [{"f": "c"}]}, "pod-list": [1, 2]}
    assert walk(data, ".releases[][].f") == ["a", "b", "c"]
    assert walk(data, '.releases["1.0"][1].f') == ["b"] and walk(data, '["pod-list"][0]') == [1]
    assert walk(data, ".missing.deeper") == []


def test_a_schema_views_exceptions_count_as_promotion_and_a_count_of_2_is_not_20():
    assert promotes('x\n  exceptions in 3 rows:\n    .items[1] a: .phase "x"')
    assert not promotes('.items: array[5] of object\n  .phase  "Running" (all 5)')
    truth = Number(2, frozenset(), ('"Failed" 2',))
    assert score_fold(truth, '.phase  "Running" 198, "Failed" 2').correct
    assert not score_fold(truth, '.phase  "Running" 180, "Failed" 20').correct
