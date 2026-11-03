"""Layer 1 inside `./lab check`: the fold's guarantees, on a sample of the eval tasks (building the
registry reads the real files on this host, so this is a functional test)."""

import pytest

from evals.l1 import check
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
