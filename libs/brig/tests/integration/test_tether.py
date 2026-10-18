"""A tethered launch: the jail's process group ends when its launching process is gone.

SPEC.md section 8 (decision-167, decision-183). `Jail.create(..., tether=fd)` takes the
read end of a pipe whose write end the embedder keeps, and nothing else ever holds. The exit
wrapper starts a watcher in the jail's process group that blocks on it; once every write end
is closed -- the embedder closed it, or the kernel did because the embedder died, `SIGKILL`
included -- the watcher sends `SIGKILL` to its own group. A program the workload left
running in the background goes with it, which `Jail.destroy` would have done had anyone been
left to call it.

The claims, each against the empty stack (no mechanism: what is under test is the launcher's
plumbing, which every stack shares; a launch is `create` then a first `start`):

1. A launching process killed with `SIGKILL` takes the jail's whole group with it (the
   control: the same launch untethered leaves the group running).
2. `Process.interrupt` (SIGINT to the group) does not end the watcher: the tether still ends
   the group after one.
3. `Jail.destroy` of a tethered jail still verifies the group empty: the watcher ends on the
   ladder's first rung like any member.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from brig.core import Spec, unenforced_report
from brig.run import IoPolicy, Jail, Process
from brig.run.teardown import KillOutcome
from brig.stack import CompiledJail
from tests.conftest import launch, workload_argv


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail() -> CompiledJail:
    return CompiledJail(
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


def _group_lives(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gone_within(pgid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _group_lives(pgid):
            return True
        time.sleep(0.05)
    return not _group_lives(pgid)


# The launching process: launches a workload that keeps a background job running, prints the
# group, and waits to be killed.
_LAUNCHER = """
import os, sys, time
from brig.core import Spec, unenforced_report
from brig.run import HostRuntime, Jail
from brig.stack import CompiledJail

compiled = CompiledJail(
    spec=Spec(), report=unenforced_report(), wrap=lambda argv: argv, env={}, staged=(),
    helpers=(), requires=frozenset(), mechanism_names=(), matrix_version=1,
)

jail_dir, tethered, argv = sys.argv[1], sys.argv[2] == "1", sys.argv[3:]
read_end, write_end = os.pipe()
jail = Jail.create(
    compiled, runtime=HostRuntime(), cwd=jail_dir, jail_id="tethered",
    jail_dir=jail_dir, **({"tether": read_end} if tethered else {}),
)
os.close(read_end)
process = jail.start(argv)
print(process._record.pgid, flush=True)
time.sleep(600)
"""


def _killed_launcher(run_id: str, *, tethered: bool, jail_dir: str) -> int:
    """Start `_LAUNCHER`, read the jail's group from it, `SIGKILL` it; the group."""
    launcher = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _LAUNCHER,
            jail_dir,
            "1" if tethered else "0",
            *workload_argv(run_id, "sleep 100"),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert launcher.stdout is not None
    pgid = int(launcher.stdout.readline())
    assert _group_lives(pgid)
    launcher.send_signal(signal.SIGKILL)
    launcher.wait()
    return pgid


@pytest.mark.integration
def test_a_tethered_jail_ends_when_its_launching_process_is_killed(
    run_id: str, jail_dir: str
) -> None:
    pgid = _killed_launcher(run_id, tethered=True, jail_dir=jail_dir)
    assert _gone_within(pgid, 5.0), f"group {pgid} outlived its SIGKILLed launcher"


@pytest.mark.integration
def test_an_untethered_jail_outlives_its_launching_process(run_id: str, jail_dir: str) -> None:
    """The control: without the tether nothing ends the group, which is what makes the claim
    above the tether's and not the launcher's death alone."""
    pgid = _killed_launcher(run_id, tethered=False, jail_dir=jail_dir)
    try:
        time.sleep(1.0)
        assert _group_lives(pgid)
    finally:
        os.killpg(pgid, signal.SIGKILL)
    assert _gone_within(pgid, 5.0)


def _tethered(argv: list[str], *, jail_dir: str) -> tuple[Jail, Process, int]:
    read_end, write_end = os.pipe()
    try:
        jail, process = launch(
            _compiled_jail(),
            argv=argv,
            cwd=jail_dir,
            io=IoPolicy(),
            jail_id="tethered",
            jail_dir=jail_dir,
            tether=read_end,
        )
    finally:
        os.close(read_end)
    return jail, process, write_end


@pytest.mark.integration
def test_an_interrupt_does_not_end_the_tether(run_id: str, jail_dir: str) -> None:
    """SIGINT to the group is for the workload. A backgrounded `sleep` ignores it (POSIX gives
    a non-interactive shell's `&` jobs SIG_IGN), so the group lives on after it; closing the
    tether then still ends it, so the watcher was not among what the interrupt ended."""
    jail, process, write_end = _tethered(workload_argv(run_id, "sleep 100"), jail_dir=jail_dir)
    try:
        time.sleep(0.5)  # the watcher and the job are up
        assert process.interrupt()
        time.sleep(0.5)
        assert _group_lives(process._record.pgid)
    finally:
        os.close(write_end)
    assert _gone_within(process._record.pgid, 5.0)


@pytest.mark.integration
def test_kill_verifies_a_tethered_jail_s_group_empty(run_id: str, jail_dir: str) -> None:
    jail, process, write_end = _tethered(workload_argv(run_id, "sleep 100"), jail_dir=jail_dir)
    try:
        time.sleep(0.3)
        report = jail.destroy()
    finally:
        os.close(write_end)
    (item,) = [item for item in report.items if item.kind == "workload_group"]
    assert item.outcome is KillOutcome.ENDED, report
