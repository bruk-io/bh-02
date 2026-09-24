"""A pid is not an identity: every liveness and kill decision compares the
pid AND the moment its process started (decision-155, 2026-09-08).

SPEC.md section 9 carried the gap in prose for four milestones -- "Sibling
liveness is matched by pid, and pid is not identity", and `alive()`'s own
paragraph admitting a rehydrated handle could read `True` against "an
unrelated process that now happens to hold that number". decision-144
accepted the window on the grounds that the blast radius was a signal and no
atomic alternative existed at this layer; its second stated condition for
ending that acceptance was "holding a pid across a durable boundary", which
is exactly what a serialized `Handle` in an embedder's log does.

**How a recycled pid is reproduced here.** Not by exhausting the pid space
and waiting for the OS to wrap -- that is hours of churn for one bit of
information, and it would still be a race rather than a test. A pid whose
occupant is not the one the handle recorded is, from every decision site's
point of view, exactly a handle whose `start_time` does not match what
`/bin/ps` (or `/proc`) says about that pid right now. So the tests below
take a REAL, live jail and rewrite that one field, which puts the code under
test in precisely the state pid reuse would put it in, deterministically.

**Every one of them carries the control in the same test**: the SAME handle,
with its real stamp, is asked the same question and answers the other way.
Without that, "reads as gone" is satisfied by a handle that was broken from
the start, and "signalled nothing" by a jail that never ran.
"""

from __future__ import annotations

import itertools
import os
import subprocess
import time
from dataclasses import replace

import pytest

from brig.core import Spec
from brig.run import Handle, IoPolicy, SubprocessLauncher
from brig.run import _identity as identity
from brig.run.teardown import KillOutcome
from brig.stack import Stack
from tests.conftest import teardown_group, workload_argv

pytestmark = pytest.mark.integration

_jail_counter = itertools.count()

#: A stamp no live process can be carrying: the reading is prefixed by the
#: platform that produced it, and neither prefix is this one. Using a
#: syntactically alien value rather than a plausible-looking timestamp keeps
#: the test from accidentally naming a real start time on a slow machine.
_A_STAMP_NO_PROCESS_HAS = "never:this-is-not-any-process's-start-time"


def _new_jail_dir() -> str:
    """A short scratch root -- `sun_path` is 104 bytes on darwin. The `id`
    infix is this file's alone, so it cannot collide with a sibling's
    counter."""
    path = f"/tmp/bg{os.getpid()}id{next(_jail_counter)}"
    os.makedirs(path, exist_ok=True)
    return path


def _launch(run_id: str, body: str = "sleep 100") -> Handle:
    jail_dir = _new_jail_dir()
    return SubprocessLauncher().launch(
        Stack([]).compile(Spec()),
        argv=workload_argv(run_id, body),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"identity-{os.path.basename(jail_dir)}",
        jail_dir=jail_dir,
    )


def _group_members(pgid: int) -> list[int]:
    """Every pid the kernel currently places in `pgid`, per a fresh
    `/bin/ps -Ao pid=,pgid=` scan (alias-proof per decision-026 -- never a
    bare `ps`). The observation is made without the code under test, which
    is what makes "nothing was signalled" a claim rather than a restatement."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid="], capture_output=True, text=True, check=True
    )
    return [
        int(parts[0])
        for parts in (line.split() for line in proc.stdout.splitlines())
        if len(parts) == 2 and int(parts[1]) == pgid
    ]


def _wait_for_the_group(pgid: int, timeout: float = 30.0) -> None:
    """Block until the jail's group has members. A START wait, not a settle:
    the controls below need the group to be THERE."""
    deadline = time.monotonic() + timeout
    while not _group_members(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)


def _with_a_stranger_at_the_pid(handle: Handle) -> Handle:
    """The same handle, describing a pid whose occupant is not the process
    it was launched against -- what the OS recycling that number leaves
    behind."""
    return replace(handle, start_time=_A_STAMP_NO_PROCESS_HAS)


# ---------------------------------------------------------------------------
# The reading itself.
# ---------------------------------------------------------------------------


def test_a_start_stamp_is_stable_for_one_process_and_absent_for_a_dead_one() -> None:
    """The stamp has to be two things or it is worth nothing: the SAME on
    two readings of one live process (or every comparison is a false
    mismatch), and ABSENT for a pid that names no process (or a recycled pid
    could never be told from a live one)."""
    mine = identity.start_stamp(os.getpid())
    assert mine != identity.UNKNOWN, "this process has no readable start time"
    assert identity.start_stamp(os.getpid()) == mine, "the reading is not stable"

    proc = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
    proc.wait()  # reaped: the number it held now names no process at all
    # Read immediately: darwin allocates pids upward through a 99999-wide
    # space, so the number just released is not handed to anything else in
    # the microseconds before the next line runs.
    assert identity.start_stamp(proc.pid) == identity.UNKNOWN, (
        "a reaped process still had a readable start time"
    )


def test_an_unknown_stamp_degrades_to_a_pid_check_rather_than_a_false_mismatch() -> None:
    """`UNKNOWN` is what a launch records when the read lost its race with a
    workload that had already exited. It must degrade to the pid-only
    behaviour that preceded decision-155 -- never to "gone", which would
    report a live jail as dead, and never to "recycled", which would stop
    teardown signalling a group that is still there."""
    assert identity.identity_holds(os.getpid(), identity.UNKNOWN) is True
    assert identity.recycled(os.getpid(), identity.UNKNOWN) is False

    # And the discriminating half: a stamp that IS recorded and does not
    # match is a mismatch, from the same call, on the same live pid.
    assert identity.identity_holds(os.getpid(), _A_STAMP_NO_PROCESS_HAS) is False
    assert identity.recycled(os.getpid(), _A_STAMP_NO_PROCESS_HAS) is True


# ---------------------------------------------------------------------------
# What every decision site does with it.
# ---------------------------------------------------------------------------


def test_alive_reads_a_recycled_pid_as_gone(run_id: str) -> None:
    """`alive()` asks two questions now. THE CONTROL is the first assertion:
    the same live jail, the same pid, the real stamp -- `True`."""
    handle = _launch(run_id)
    try:
        _wait_for_the_group(handle.pgid)
        assert handle.alive() is True, "CONTROL failed: the jail is not running"
        assert _with_a_stranger_at_the_pid(handle).alive() is False, (
            "a pid whose occupant is a different process still read as this jail"
        )
    finally:
        teardown_group(handle)


def test_interrupt_delivers_nothing_to_a_recycled_pid(run_id: str) -> None:
    """`interrupt` returns `False` -- not delivered, because what this handle
    names is gone -- rather than sending a `SIGINT` into a group led by a
    stranger that happens to hold the number.

    THE CONTROL that makes "returned False" mean "sent nothing": the group is
    still there, with the same members, AFTER the call. And the second
    control, in the same test: the unmodified handle returns `True` against
    that same group, so `False` is attributable to the stamp and not to this
    jail being unsignalable from the start."""
    handle = _launch(run_id)
    try:
        _wait_for_the_group(handle.pgid)
        before = _group_members(handle.pgid)
        assert before, "CONTROL failed: the jail's process group is empty"

        assert _with_a_stranger_at_the_pid(handle).interrupt() is False
        assert set(before) <= set(_group_members(handle.pgid)), (
            "a member of the group is gone, so something was delivered to it after all"
        )

        assert handle.interrupt() is True, (
            "CONTROL failed: the real handle could not signal its own group"
        )
    finally:
        teardown_group(handle)


def test_kill_reports_already_gone_for_a_recycled_pid_and_signals_nothing(
    run_id: str,
) -> None:
    """Teardown's ladder never reaches a rung. The item says `ALREADY_GONE`
    and its detail names WHY -- a start time that does not match -- so a
    reader of the report is not left to guess between "it had ended" and "I
    refused to touch it".

    THE CONTROL, in the same test and in this order: the group is still
    running after that report, and the unmodified handle then tears it down
    and reports `ENDED`. Without the second half, `ALREADY_GONE` would be
    indistinguishable from a jail that had died on its own."""
    handle = _launch(run_id)
    try:
        _wait_for_the_group(handle.pgid)
        assert _group_members(handle.pgid), "CONTROL failed: the group is empty"

        report = _with_a_stranger_at_the_pid(handle).kill()
        item = report.items[0]
        assert item.kind == "workload_group"
        assert item.outcome is KillOutcome.ALREADY_GONE, report
        assert "start time" in item.detail, item.detail
        assert _group_members(handle.pgid), (
            "the jail was torn down anyway -- the ladder ran against a pid the "
            "handle no longer names"
        )

        ended = handle.kill()
        assert ended.items[0].outcome is KillOutcome.ENDED, ended
    finally:
        teardown_group(handle)


def test_the_launcher_records_a_real_stamp_on_every_handle(run_id: str) -> None:
    """The field is only worth comparing if a launch actually fills it. A
    `sleep 100` workload cannot have lost the read race, so `UNKNOWN` here
    means the launcher never took the reading at all."""
    handle = _launch(run_id)
    try:
        _wait_for_the_group(handle.pgid)
        assert handle.start_time != identity.UNKNOWN
        assert handle.start_time == identity.start_stamp(handle.pid)
        # It survives serialization, which is the whole point of recording
        # it: the process that rehydrates the handle is the one whose pid
        # might have been recycled out from under it.
        assert Handle.from_dict(handle.to_dict()).start_time == handle.start_time
    finally:
        teardown_group(handle)
