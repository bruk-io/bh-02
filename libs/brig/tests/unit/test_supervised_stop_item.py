"""What a supervised process's `stop` reports (decision-192, TASK-0079.06).

The supervisor says how it ended a process's group, and the host looks at the process table
itself. `stop_item` is the pure decision between the two: `ENDED` only when both agree, so a
supervisor that says a group ended while the host sees it run is a `FAILED` item and never an
`ENDED` one (law 1).
"""

from __future__ import annotations

import pytest

from brig.run import KillOutcome
from brig.run._records import ProcessRecord
from brig.run._supervised import stop_item

pytestmark = pytest.mark.unit

_PROCESS = ProcessRecord(
    id="0123456789abcdef",
    order=1,
    pid=4242,
    pgid=4242,
    start_time="linux-starttime:1",
    argv=("sleep", "1"),
    stdout_path="/o",
    stderr_path="/e",
)


@pytest.mark.parametrize(
    ("said", "host_found_it_gone", "outcome"),
    [
        ("ended", True, KillOutcome.ENDED),
        ("already_gone", True, KillOutcome.ALREADY_GONE),
        ("ended", False, KillOutcome.FAILED),
        ("already_gone", False, KillOutcome.FAILED),
        ("failed", True, KillOutcome.FAILED),
        ("failed", False, KillOutcome.FAILED),
    ],
)
def test_ended_is_reported_only_when_the_supervisor_and_the_host_agree(
    said: str, host_found_it_gone: bool, outcome: KillOutcome
) -> None:
    item = stop_item("exec_sibling", _PROCESS, said, "the detail", gone=host_found_it_gone)
    assert (item.kind, item.identity, item.outcome) == ("exec_sibling", "4242", outcome)


def test_a_disagreement_says_who_saw_what_and_what_to_do() -> None:
    item = stop_item("workload_group", _PROCESS, "ended", "", gone=False)
    assert "supervisor said" in item.detail and "host still finds" in item.detail
    assert "kill -KILL -- -4242" in item.detail


def test_the_supervisors_own_failure_detail_is_kept() -> None:
    item = stop_item("workload_group", _PROCESS, "failed", "group 7 still had a member", gone=True)
    assert item.detail == "group 7 still had a member"
