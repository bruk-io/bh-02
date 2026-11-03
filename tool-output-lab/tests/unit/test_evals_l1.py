"""Layer 1 inside `./lab check`: the fold's guarantees, on a sample of the eval tasks."""

import json

import pytest

from compressors.route import fold
from evals.l1 import check, coverage, json_markers
from evals.tasks import tasks

_BY_ID = {t.task_id: t for t in tasks()}


def _sample() -> list[str]:
    """Every synthetic task at M (folded, and quick), and every real task."""
    return [t.task_id for t in _BY_ID.values() if t.band == "M" or t.path]


@pytest.mark.parametrize("task_id", _sample())
def test_folds_account_for_every_line_and_every_marker_is_true(task_id):
    task = _BY_ID[task_id]
    for query_on in {False, bool(task.query)}:
        assert check(task, 2000, query_on).violations == []


@pytest.mark.parametrize(
    "task_id", [t for t in _sample() if _BY_ID[t].kind in ("spot", "absent") and "quiet" not in t]
)
def test_an_anomaly_the_fold_has_a_rule_for_is_in_view_and_none_is_ever_invented(task_id):
    """Quiet anomalies (no rule) are measured, not promised: they are in the l1 report."""
    assert check(_BY_ID[task_id], 2000, query_on=False).sufficient


@pytest.mark.parametrize(
    ("task_id", "query_on"),
    [
        ("figma-M-count-k7", False),  # 7 of 100 hidden: more than three promoted, and rare up to 10%
        ("a11y-L-enumerate-k4", False),
        ("log-L-lookup-at50", True),  # `req` is in every line: a term most lines share is dropped
        ("figma-L-lookup-at90", True),  # promoted by how many query terms match
        ("xml-L-lookup-JP-13", True),  # a short code, matched deep inside its country
        ("xml-L-enumerate-AD", True),  # a header match outweighs `Ad` in other countries' names
        ("pypi-L-lookup-sha", True),  # digests are never cut
        ("pypi-L-enumerate-2023", True),  # keys kept for what their values hold
        ("pypi-L-count-releases", False),  # the key total is in the marker
    ],
)
def test_cases_the_layer_1_fixes_made_sufficient(task_id, query_on):
    assert check(_BY_ID[task_id], 2000, query_on).sufficient


def test_coverage_catches_a_marker_that_skips_or_overlaps():
    source = "\n".join(f"line {i}" for i in range(1, 11))
    good = "line 1\n[... lines 2-9 omitted (8 lines)]\nline 10"
    assert coverage(source, good, numbered=False) == []
    assert coverage(source, "line 1\n[... lines 3-9 omitted (7 lines)]\nline 10", numbered=False)
    assert coverage(source, "line 1\n[... lines 2-9 omitted (8 lines)]", numbered=False)


def test_the_jsonl_note_is_checked_against_the_lines_it_names():
    rows = [json.dumps({"name": f"pod-{i:04d}", "phase": "Running"}) for i in range(300)]
    for raw in ("\n".join(rows), "\n" + "\n\n".join(rows)):
        folded = fold(raw, budget_tokens=300)
        assert folded is not None and json_markers(raw, folded.body) == []
    gappy = "\n" + "\n\n".join(rows)
    false = fold("\n".join(rows), budget_tokens=300)  # claims index i is line i+1
    assert false is not None
    assert json_markers(gappy, false.body) == [
        "the JSONL note maps index i to line i+1, and a record is not there"
    ]
