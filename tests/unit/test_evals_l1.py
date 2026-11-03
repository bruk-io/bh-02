"""Layer 1 inside `./lab check`: the fold's guarantees, on a sample of the eval tasks."""

import pytest

from evals.l1 import check, coverage
from evals.tasks import tasks
from evals.truth import Absent, Items, Number, Score, mentions, score_answer, score_fold

_BY_ID = {t.task_id: t for t in tasks()}


def _sample() -> list[str]:
    """Every synthetic task at M (folded, and quick), and every real task."""
    return [t.task_id for t in _BY_ID.values() if t.band == "M" or t.path]


@pytest.mark.parametrize("task_id", _sample())
def test_folds_account_for_every_line_and_every_marker_is_true(task_id):
    task = _BY_ID[task_id]
    for query_on in {False, bool(task.query)}:
        assert check(task, 2000, query_on).violations == []


@pytest.mark.parametrize("task_id", [t for t in _sample() if _BY_ID[t].kind in ("spot", "absent")])
def test_an_anomaly_is_always_in_view_and_none_is_ever_invented(task_id):
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


def test_scorers():
    assert mentions("version 8.1.", "8.1") and not mentions("8.1.7", "8.1")
    assert score_answer(Absent(frozenset({"pod-1"})), "None of them.").correct
    assert not score_answer(Absent(frozenset({"pod-1"})), "pod-1 looks odd").correct
    items = Items(frozenset({"a1", "a2"}), frozenset({"a1", "a2", "b1", "b2", "b3"}))
    assert score_answer(items, "a1, a2, b1").correct is False  # precision 2/3
    assert score_answer(items, "a1 and a2") == Score(True, 1.0, 1.0)
    assert score_fold(Number(3, frozenset({"x", "y", "z"})), "x y z").correct  # countable
    assert not score_fold(Number(3, frozenset({"x", "y", "z"})), "x y").correct
