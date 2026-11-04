"""`approval`: the one rule for whether the model's code runs unasked, and its row."""

from collections.abc import Mapping
from dataclasses import dataclass

from cordis.loader import resolve
from cordis.testing import drive
from runner_cordis_plugin import (
    PLANNED,
    UNENFORCED,
    Approval,
    BrigConfig,
    BrigJail,
    Runner,
    approval,
    is_confined,
)


@dataclass(frozen=True)
class _Host:
    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""
    grants: str = ""


_CONFINED = {**UNENFORCED, "fs_write": "enforced", "network": "enforced"}
_QUESTION = {"name": "python", "input": {"code": "print(1)"}}


class _Runner:
    """A `runner` that reports the grades it is given, and starts nothing."""

    def __init__(self, report: Mapping[str, str]) -> None:
        self.grades = report

    def report(self) -> Mapping[str, str]:
        return self.grades


def test_confined_means_writes_and_network_are_enforced() -> None:
    assert is_confined({"fs_write": "enforced", "network": "enforced", "fs_read": "unenforced"})
    assert not is_confined({"fs_write": "enforced", "network": "best_effort"})
    # brig grades writes best-effort while the jail holds a path with a mount the host can undo; that
    # is confined only for a runner that says it armed a tripwire (bh-02's `host_undo`), which ends the
    # jail then; one it could not hold at all is not
    assert is_confined({"fs_write": "best_effort", "network": "enforced", "host_undo": "tripwired"})
    assert is_confined({"fs_write": "enforced", "network": "enforced"})  # nothing to undo: no axis needed
    assert not is_confined({"fs_write": "unenforced", "network": "enforced", "host_undo": "tripwired"})
    assert not is_confined({"fs_write": "violated", "network": "enforced"})
    assert not is_confined(UNENFORCED)
    assert not is_confined({})


def test_best_effort_network_is_confined_only_on_the_strength_of_an_egress_policy_and_never_violated() -> (
    None
):
    """brig grades `network` best-effort whenever the jail sees any host root, so best-effort counts
    as confined only when the start passed an egress policy (bh-02's `egress: proxied`); a jail that
    sees a socket place is `violated`, which never counts, egress policy or not."""
    base = {"fs_write": "enforced", "network": "best_effort"}
    assert not is_confined(base)
    assert not is_confined({**base, "egress": "none"})
    assert is_confined({**base, "egress": "proxied"})
    assert not is_confined({**base, "network": "violated", "egress": "proxied"})
    assert not is_confined({**base, "network": "unenforced", "egress": "proxied"})
    assert Approval(_Runner({**base, "egress": "proxied"})).unasked(_QUESTION)
    assert not Approval(_Runner(base)).unasked(_QUESTION)


def test_the_planned_grades_are_what_approval_counts_as_confined() -> None:
    assert PLANNED["network"] == "best_effort" and PLANNED["egress"] == "proxied"
    assert is_confined(PLANNED)


def test_best_effort_writes_are_not_confined_without_the_runner_s_word_that_a_tripwire_is_armed() -> None:
    """The premise of counting best-effort writes as confined is the tripwire, which brig does not
    grade: a report without `host_undo: tripwired` (any other runner's, or a start that armed none)
    is not confined, however brig graded the rest."""
    best_effort = {"fs_write": "best_effort", "network": "enforced"}
    assert not is_confined(best_effort)
    assert not is_confined({**best_effort, "host_undo": "none"})
    assert not Approval(_Runner(best_effort)).unasked(_QUESTION)
    assert Approval(_Runner({**best_effort, "host_undo": "tripwired"})).unasked(_QUESTION)


def test_confined_code_runs_unasked_and_unconfined_code_does_not() -> None:
    granted = Approval(_Runner(_CONFINED))
    assert granted.confined and granted.unasked(_QUESTION)
    loose = Approval(_Runner(UNENFORCED))
    assert not loose.confined and not loose.unasked(_QUESTION)


def test_a_call_that_runs_in_bh_02_s_own_process_is_asked_about_however_confined_the_runner() -> None:
    """A tool whose calls run on the host (`runs = "host"`, CONTRACTS.md: tools) is outside every
    jail, so the runner's grades decide nothing: it is never unasked."""
    granted = Approval(_Runner(_CONFINED))
    assert not granted.unasked({**_QUESTION, "name": "search", "runs": "host"})
    assert granted.unasked({**_QUESTION, "runs": "jail"})


def test_bh_02_s_own_harness_tool_is_unasked_when_the_runner_confines_and_asked_under_no_jail() -> None:
    """A tool declaring `runs = "harness"` acts only on the session's jail and bh-02's own state
    (CONTRACTS.md: tools): it goes ahead where the jail's own calls do, and is asked where they
    are, while `"host"` is asked either way."""
    question = {**_QUESTION, "name": "agents", "runs": "harness"}
    granted = Approval(_Runner(_CONFINED))
    assert granted.unasked(question)
    assert not granted.unasked({**question, "runs": "host"})
    loose = Approval(_Runner(UNENFORCED))
    assert not loose.unasked(question)
    assert not loose.unasked({**question, "runs": "host"})


def test_bh_02_s_memory_tool_is_never_asked_jailed_or_under_no_jail_while_host_always_is() -> None:
    """A tool declaring `runs = "memory"` runs in bh-02's own process but writes only beneath
    `host.auto_memory`, through no link, which the jailed model can already write unasked
    (CONTRACTS.md: tools): nothing is gained by asking, however confined the runner. Every other
    `"host"` call is still asked in both."""
    question = {**_QUESTION, "name": "memory", "runs": "memory", "input": {"action": "read", "name": "x"}}
    for report in (_CONFINED, UNENFORCED, {}):
        runner = Approval(_Runner(report))
        assert runner.unasked(question)
        assert not runner.unasked({**question, "runs": "host"})
    assert not Approval(_Runner(UNENFORCED)).unasked({**question, "name": "search", "runs": "host"})
    assert not Approval(_Runner(UNENFORCED)).unasked(
        {**question, "runs": "cloud"}
    )  # an unknown value is not it


def test_confined_is_read_from_the_runner_each_time() -> None:
    """The runner's grades are its last start's: a Python process started again under a looser
    jail makes the next call asked about, with no new rule."""
    runner = _Runner(_CONFINED)
    granted = Approval(runner)
    assert granted.unasked(_QUESTION)
    runner.grades = {**_CONFINED, "network": "violated"}
    assert not granted.confined and not granted.unasked(_QUESTION)


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


def test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start() -> None:
    """On darwin every start of `runner:confined` refuses, so nothing is ever jailed: the report
    that decides `confined` (and the status bar's `jailed`) says so before an input, not after one fails."""
    runner = Runner(BrigJail(BrigConfig(), _Host(), platform="darwin"))
    assert Approval(runner).confined is False
    assert runner.report() == UNENFORCED
