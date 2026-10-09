"""`approval`: the one rule for whether the model's code runs unasked, and its row."""

from collections.abc import Mapping

from cordis.loader import resolve
from cordis.testing import drive
from runner_cordis_plugin import UNENFORCED, Approval, approval, is_confined

_CONFINED = {**UNENFORCED, "fs_write": "enforced", "network": "enforced"}
_REQUEST = {"name": "python", "input": {"code": "print(1)"}}


class _Runner:
    """A `runner` that reports the grades it is given, and starts nothing."""

    def __init__(self, report: Mapping[str, str]) -> None:
        self.grades = report

    def report(self) -> Mapping[str, str]:
        return self.grades


def test_confined_means_writes_and_network_are_enforced() -> None:
    assert is_confined({"fs_write": "enforced", "network": "enforced", "fs_read": "unenforced"})
    assert not is_confined({"fs_write": "enforced", "network": "best_effort"})
    assert not is_confined(UNENFORCED)
    assert not is_confined({})


def test_confined_code_runs_unasked_and_unconfined_code_does_not() -> None:
    granted = Approval(_Runner(_CONFINED))
    assert granted.confined and granted.unasked(_REQUEST)
    loose = Approval(_Runner(UNENFORCED))
    assert not loose.confined and not loose.unasked(_REQUEST)


def test_a_call_that_runs_in_bh_02_s_own_process_is_asked_about_however_confined_the_runner() -> None:
    """A tool whose calls run on the host (`runs = "host"`, CONTRACTS.md: tools) is outside every
    jail, so the runner's grades decide nothing: it is never unasked."""
    granted = Approval(_Runner(_CONFINED))
    assert not granted.unasked({**_REQUEST, "name": "search", "runs": "host"})
    assert granted.unasked({**_REQUEST, "runs": "jail"})


def test_confined_is_read_from_the_runner_each_time() -> None:
    """The runner's grades are its last start's: a Python process started again under a looser
    jail makes the next call asked about, with no new rule."""
    runner = _Runner(_CONFINED)
    granted = Approval(runner)
    assert granted.unasked(_REQUEST)
    runner.grades = {**_CONFINED, "network": "best_effort"}
    assert not granted.confined and not granted.unasked(_REQUEST)


async def test_the_row_binds_approval_over_the_runner() -> None:
    runner = _Runner(UNENFORCED)
    effects = await drive(approval(runner=runner))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "approval")]
    assert effects[0].args[1] == Approval(runner)


def test_the_row_depends_on_the_runner_alone() -> None:
    """`/clear` restarts the python tool: the approval row, and the loop's and the extensions'
    hold on it, stay up; asking is the asker's (`output.confirm`), so a new ui reloads none of it."""
    row = resolve("runner:approval")
    assert row.inject == {"runner"} and row.provides == {"approval"}
