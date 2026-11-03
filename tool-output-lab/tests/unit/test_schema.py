"""The schema view of JSON: exact field statistics, the rows that break the pattern, and a query."""

import json
import random
import re

from compressors.common import estimate_tokens
from compressors.schema import schema_view


def _pods(n: int, seed: int = 1) -> list[dict]:
    rng = random.Random(seed)
    return [
        {
            "name": f"web-{rng.getrandbits(40):010x}",
            "phase": "Running",
            "restarts": rng.randint(0, 3),
            "node": f"node-{rng.choice('abcd')}",
            "labels": {"app": "web"},
        }
        for _ in range(n)
    ]


def _view(value, budget: int = 2000, **kw) -> str:
    return schema_view(value, frozenset(), budget, **kw)


def test_every_count_the_view_states_is_the_count_in_the_data():
    pods = _pods(300)
    pods[10]["phase"] = pods[20]["phase"] = "Failed"
    view = _view({"items": pods})
    line = next(x for x in view.splitlines() if x.strip().startswith(".node"))
    for value, count in re.findall(r'"(node-\w)" (\d+)', line):
        assert int(count) == sum(p["node"] == value for p in pods)
    assert '.phase "Running" 298, "Failed" 2' in re.sub(r" +", " ", view)
    assert '"web" (all 300)' in view and "str, unique like web-<hex>" in view


def test_a_rare_value_an_outlier_a_rare_key_a_missing_key_and_another_type_are_each_an_exception():
    pods = _pods(200)
    pods[5]["phase"] = "CrashLoopBackOff"
    pods[50]["restarts"] = 97
    pods[90]["error"] = "OOMKilled"
    del pods[120]["node"]
    pods[150]["restarts"] = "3"
    view = _view({"items": pods})
    rows = {m[0]: m[1] for m in re.findall(r"^\s+(\.items\[\d+\]) web-\w+: (.*)$", view, re.M)}
    assert rows[".items[5]"] == '.phase "CrashLoopBackOff"'
    assert rows[".items[50]"] == ".restarts 97 (outlier)"
    assert rows[".items[90]"] == 'has .error "OOMKilled"'
    assert rows[".items[120]"] == "lacks .node"
    assert rows[".items[150]"] == '.restarts is str "3"'
    assert len(rows) == 5 and "exceptions in 5 rows:" in view


def test_rows_that_all_share_the_pattern_have_no_exceptions_and_no_query():
    view = _view({"items": _pods(200)})
    assert "exceptions" not in view and "query:" not in view


def test_the_query_selects_on_the_field_that_broke_and_names_rows_by_their_identifying_field():
    pods = _pods(200)
    pods[7]["phase"] = "Failed"
    assert (
        _view({"items": pods}).splitlines()[-1]
        == "query: jq '.items[] | select(.phase != \"Running\") | .name' FILE"
    )
    assert _view(pods).splitlines()[-1] == "query: jq '.[] | select(.phase != \"Running\") | .name' FILE"
    assert (
        _view(pods, slurp=True)
        .splitlines()[-1]
        .startswith('query: jq -s \'.[] | select(.phase != "Running")')
    )


def test_an_object_keyed_by_version_lists_its_keys_and_the_files_inside_it_are_a_collection():
    releases = {
        f"1.{i}": [
            {
                "filename": f"pkg-1.{i}.tar.gz",
                "upload_time": f"2020-01-{i % 28 + 1:02d}T00:00:00",
                "yanked": False,
            }
        ]
        for i in range(30)
    }
    releases["1.7"][0]["yanked"] = True
    view = _view({"releases": releases})
    assert ".releases: object of 30 keys like <n>.<n>, each array" in view
    assert "keys: 1.0, 1.1, 1.2" in view
    assert ".releases[]: array[30] of object" in view
    assert "2020-01-01T00:00:00 to 2020-01-28T00:00:00" in view
    assert '.releases["1.7"][0] pkg-1.7.tar.gz: .yanked true' in view
    assert "query: jq '.releases[][] | select(.yanked != false) | .filename' FILE" in view


def test_rows_holding_a_query_term_few_rows_hold_are_shown():
    pods = _pods(200)
    view = schema_view({"items": pods}, frozenset({pods[42]["name"]}), 2000)
    assert "matches the query: .items[42] " in view and pods[42]["name"] in view


def test_the_view_fits_the_budget_by_showing_less_and_saying_what_it_left_out():
    rows = [{f"k{j}": (i * j) % 7 for j in range(60)} | {"name": f"r{i:05d}x"} for i in range(400)]
    for i in range(0, 400, 10):
        rows[i]["k1"] = 999  # 40 rows break k1's pattern
    view = _view(rows, budget=500)
    assert estimate_tokens(view) <= 500
    assert re.search(r"\[\.\.\. \d+ more fields: ", view) and re.search(
        r"\[\.\.\. \d+ more exception rows\]", view
    )


def test_the_views_size_depends_on_the_structure_not_the_number_of_rows():
    small, large = _view({"items": _pods(100)}), _view({"items": _pods(10_000)})
    assert abs(estimate_tokens(large) - estimate_tokens(small)) <= 10
    assert estimate_tokens(json.dumps({"items": _pods(10_000)})) > 100 * estimate_tokens(large)
