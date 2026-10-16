"""`destroy(grace=0)` against real processes, with no bubblewrap (decision-193, TASK-0079.06).

A grace period is a window a hostile workload uses: a teardown that sends `SIGTERM` and waits 2 s
for a program that ignores it lets that program act for 2 s. `grace=0` skips the first two rungs of
the ladder, `SIGKILL` at once, and in a supervised jail ends the instance before anything else.
What this file shows, each with its control in the same test:

- no `SIGTERM` is sent at `grace=0` (a handler that would say so never ran) and one is at any other
  grace; a program that ignores `SIGTERM` is ended in well under what the grace gives it;
- the instance's group gets the first signal, ahead of every process's group, and the link is
  closed after it (a `kill_named` over a stand-in instance, the order read from the `killpg`s);
- an instance found running before and gone after is `ENDED`, a process whose leader ran before
  the instance was ended is too, and a repeat finds `ALREADY_GONE`;
- a negative grace is refused, saying what to pass.

The real instance, a supervisor's PID 1 with a `setsid()` child, is `tests/e2e/test_supervised_jail.py`'s.
"""

import itertools
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from brig.core import Spec, unenforced_report
from brig.run import IoPolicy, Jail, Process, _identity, teardown
from brig.run.teardown import KillOutcome, kill_named
from brig.stack import CompiledJail
from tests.conftest import launch, teardown_group, workload_argv

pytestmark = pytest.mark.integration

_counter = itertools.count()


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _launch(argv: list[str]) -> tuple[Jail, Process]:
    jail_dir = f"/tmp/bg{os.getpid()}ao{next(_counter)}"
    compiled = CompiledJail(
        spec=Spec(),
        report=unenforced_report(),
        wrap=_identity_wrap,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        mechanism_names=(),
        matrix_version=1,
    )
    return launch(
        compiled,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-destroy-at-once",
        jail_dir=jail_dir,
    )


def _answering(marker: Path) -> str:
    """A body that writes `marker` when it is sent `SIGTERM`: the main shell traps it, the
    program it waits on is the group's, and dies of it."""
    return f"trap 'echo SIGTERM > {marker}' TERM; sleep 100"


def test_a_destroy_with_no_grace_sends_no_sigterm_and_one_with_a_grace_does(
    run_id: str, tmp_path: Path
) -> None:
    """`grace=0` is `SIGKILL` and nothing before it: the handler never ran. Control: any other
    grace sends `SIGTERM` first, and the handler did run."""
    told = {}
    for grace in (0, 5.0):
        marker = tmp_path / f"term-{grace}"
        jail, process = _launch(workload_argv(f"{run_id}{grace}", _answering(marker)))
        try:
            time.sleep(0.5)  # the shell has set its trap
            report = jail.destroy(grace=grace)
            assert report.items[0].outcome is KillOutcome.ENDED, report
            told[grace] = marker.exists()
        finally:
            teardown_group(process)
    assert told == {0: False, 5.0: True}


def test_a_program_that_ignores_sigterm_is_ended_at_once_and_a_grace_period_is_waited_out(
    run_id: str,
) -> None:
    """A program that ignores `SIGTERM` is ended by `SIGKILL` at once, in far less than the grace
    the same program is given otherwise (the control: 1.0 s, waited out in full)."""
    elapsed = {}
    for grace in (0, 1.0):
        jail, process = _launch(workload_argv(f"{run_id}{grace}", "trap '' TERM; sleep 100"))
        try:
            time.sleep(0.5)
            began = time.monotonic()
            report = jail.destroy(grace=grace)
            elapsed[grace] = time.monotonic() - began
            assert [item.outcome for item in report.items] == [KillOutcome.ENDED], report
        finally:
            teardown_group(process)
    assert elapsed[0] < 0.5, elapsed
    assert elapsed[1.0] >= 1.0, elapsed


def test_a_second_destroy_with_no_grace_finds_everything_already_gone(run_id: str) -> None:
    jail, process = _launch(workload_argv(run_id, "sleep 100"))
    try:
        time.sleep(0.3)
        assert [item.outcome for item in jail.destroy(grace=0).items] == [KillOutcome.ENDED]
        again = jail.destroy(grace=0)
        assert [item.outcome for item in again.items] == [KillOutcome.ALREADY_GONE], again
    finally:
        teardown_group(process)


def test_a_negative_grace_is_refused_and_says_what_to_pass(run_id: str) -> None:
    jail, process = _launch(workload_argv(run_id, "sleep 100"))
    try:
        with pytest.raises(ValueError, match=r"pass 0 to end the jail at once"):
            jail.destroy(grace=-1.0)
        assert process.alive(), "a refused destroy ended something"
    finally:
        teardown_group(process)


def test_a_jail_with_no_supervisor_has_no_instance_group(run_id: str) -> None:
    jail, process = _launch(workload_argv(run_id, "sleep 100"))
    try:
        assert jail.instance_group is None
    finally:
        teardown_group(process)


def test_the_instance_is_signalled_first_then_the_link_closed_then_each_process(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first signal of `destroy(grace=0)` of a supervised jail goes to the instance's group,
    ahead of every process's group, and no signal is a `SIGTERM`; the link is closed after the
    instance's `SIGKILL` and not before (a supervisor that reads end-of-file starts its own
    ladder, `SIGTERM` first). A stand-in instance, a group of its own, shows the order, which no
    observation of a real jail can: the namespace's end is the same moment either way. Control:
    with a grace, the processes are signalled first and the instance last, as it was ruled in
    decision-192."""
    jail, first = _launch(workload_argv(run_id, "sleep 100"))
    record = jail._record()
    instance = subprocess.Popen(["sleep", "100"], start_new_session=True)
    stamp = _identity.start_stamp(instance.pid)
    try:
        order: list[tuple[str, int]] = []
        real = os.killpg

        def spy(pgid: int, sig: int) -> None:
            order.append((signal.Signals(sig).name, pgid))
            real(pgid, sig)

        monkeypatch.setattr(teardown.os, "killpg", spy)

        def end_of_file() -> None:
            order.append(("EOF", instance.pid))

        report = kill_named(
            known=record.processes,
            jail_dir=record.jail_dir,
            helper_pids=(),
            helper_stamps=(),
            supervisor=(instance.pid, stamp),
            end_of_file=end_of_file,
            grace=0,
        )
        assert order[0] == ("SIGKILL", instance.pid), order
        assert order.index(("EOF", instance.pid)) > 0, order  # after the first signal, never before
        assert not [name for name, _ in order if name == "SIGTERM"], order
        assert [item.kind for item in report.items] == ["workload_group", "supervisor"]
        assert all(item.outcome is KillOutcome.ENDED for item in report.items), report
    finally:
        instance.kill()
        instance.wait()
        teardown_group(first)

    # The control, a fresh jail and a fresh stand-in: with a grace the process is first, the
    # instance last, and its link is closed just before its own ladder.
    jail, first = _launch(workload_argv(f"{run_id}c", "sleep 100"))
    record = jail._record()
    instance = subprocess.Popen(["sleep", "100"], start_new_session=True)
    stamp = _identity.start_stamp(instance.pid)
    try:
        order.clear()
        kill_named(
            known=record.processes,
            jail_dir=record.jail_dir,
            helper_pids=(),
            helper_stamps=(),
            supervisor=(instance.pid, stamp),
            end_of_file=end_of_file,
            grace=5.0,
        )
        assert order[0] == ("SIGTERM", record.processes[0].pgid), order
        assert [entry for entry in order if entry[1] == instance.pid][0] == ("EOF", instance.pid), (
            order
        )
    finally:
        instance.kill()
        instance.wait()
        teardown_group(first)
