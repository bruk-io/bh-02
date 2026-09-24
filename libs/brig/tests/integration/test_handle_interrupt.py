"""`Handle.interrupt`: SIGINT to the workload group, and what `True` means.

SPEC.md law 7, verbatim: "Control must not require cooperation. Interrupt
and kill are delivered by mechanism-level means that work when the jail is
spinning, wedged, or hostile. Teardown is process-group/tree-shaped, and its
deliverability is itself graded in the report."

`interrupt` is the first rung of that: `os.killpg(pgid, SIGINT)`, never a
single pid. Three claims, each with its own discriminating control:

1. **It reaches every member of the group, not just the leader.** The
   workload here is `workload_argv`'s own `<body> & wait` shape, so the
   leader is a shell and the interesting process is a BACKGROUNDED CHILD of
   it. A single-pid signal would leave that child alive and orphaned, which
   is exactly the "single-pid SIGKILL that leaves the interesting child
   alive" failure SPEC.md section 9 names. The child reports its OWN pid
   from inside its `SIGINT` handler, so the proof is the signal's arrival
   at a non-leader, not an inference from the group emptying.

   **The child has to re-arm `SIGINT` for this to mean anything**, and that
   is a fact about shells rather than about brig: POSIX has a
   non-interactive shell set `SIGINT` to `SIG_IGN` for every asynchronous
   (`&`) command, and `SIG_IGN` survives `exec`, so a backgrounded child
   that does nothing ignores the signal. `_INTERRUPT_CHILD` installs its own
   handler, which overrides the inherited disposition.
2. **`True` is deliverability, not death.** A workload that survives the
   signal still gets `True` -- the return value is `os.killpg` not raising,
   and the method's docstring says so rather than implying an outcome it
   never verified. Asserted with the group still non-empty AFTER the
   interrupt, which is the half that makes it a claim about delivery.
3. **`False` is an honest "not delivered".** A group that has already been
   torn down returns `False` rather than raising `ProcessLookupError` at a
   caller who would only have to translate it.

**The arm is a PRECONDITION, and waiting for the fork is not waiting for
it.** The same `SIG_IGN` that makes claim 1's re-arm necessary makes the
window before that re-arm fatal rather than slow: a `SIGINT` that lands
between the shell forking the child and the child calling `signal.signal`
is DISCARDED, not queued, so the marker never appears no matter how long a
test waits for it. The group reaching two members says the fork happened;
it says nothing about a cold interpreter having got as far as arming. So
`_launch_child` blocks on a readiness file the child writes with its own
hand, immediately after the arm and never before it -- the only observation
that means what the tests below need it to mean.

**Two things were still wrong with that handshake, and this file fixes both
(2026-09-08).** It had been observed to fail once in 26 runs of the second
test, on the 5-second marker wait.

- *The handshake shared its clock with a wait that is not it.* The readiness
  loop ran against a deadline the PRECEDING group-membership loop had
  already been consuming, so a slow fork left the arm wait with whatever was
  left over -- possibly nothing, in which case the file was checked exactly
  once and the test failed claiming the child never armed. The arm wait now
  owns its own budget, and the group's shape is read afterwards as a control
  rather than waited on as a gate: the readiness file is strictly the
  stronger observation, since a child that has armed has certainly forked.
- *The marker wait was budgeted like a settle.* Five seconds is the right
  order for "a signalled group clears"; it is not the right order for "a
  cold CPython, on a machine running the rest of this suite, reaches a
  handler and completes a write". Both are waits for something that has
  already happened, and both are on the passing path, so the only cost of a
  generous budget is a slow failure and the cost of a tight one is a red
  suite that is not about brig. `_MARKER_S` is now as generous as the start
  budget.

Every workload is `workload_argv`-tagged so the suite's leak sweep catches
anything a test's own teardown misses, and every test tears down with
`tests.conftest.teardown_group` -- never with `Handle.kill`, which is code
under test elsewhere in this suite.
"""

from __future__ import annotations

import itertools
import os
import subprocess
import sys
import time

import pytest

from brig.core import Spec
from brig.run import Handle, IoPolicy, SubprocessLauncher
from brig.stack import Stack
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()

#: How long a test waits for a signalled group to actually clear. Generous
#: against scheduling; short against the suite: a group that is going to
#: clear does so in milliseconds once its members have been signalled.
_SETTLE_S = 5.0

#: How long a test waits for a DELIVERED signal's marker to land. Much more
#: generous than `_SETTLE_S`, because what it covers is not a group emptying
#: but a cold interpreter's `SIGINT` handler running and completing a file
#: write while the rest of this suite has the machine. The signal has
#: already been delivered by the time this wait starts -- so the wait only
#: ever ends early on the FAILING path, and budgeting it tightly buys
#: nothing but flakes.
_MARKER_S = 30.0

#: How long a test waits for a jail's child to START -- fork, exec, and a
#: cold interpreter reaching its `signal.signal` call. A separate, far more
#: generous budget than `_SETTLE_S` on purpose: it covers a process spawn on
#: a loaded machine, and nothing downstream is racing it.
_START_S = 30.0

#: A workload child that RE-ARMS `SIGINT` (overriding the `SIG_IGN` a
#: non-interactive shell gives every `&` command, which `exec` preserves),
#: ANNOUNCES that arm, records its own pid on arrival, and then either exits
#: or keeps running -- the two shapes claims 1 and 2 need. argv:
#: `<marker path> <ready path> exit|survive`.
_INTERRUPT_CHILD = """\
import os, signal, sys, time

marker, ready, mode = sys.argv[1], sys.argv[2], sys.argv[3]


def _on_int(signum, frame):
    del signum, frame
    # Written-then-renamed, exactly like the readiness file below: the
    # reader polls for this path, and a reader that caught it between
    # `open` and `write` would read `""` and have to guess whether the
    # signal arrived. A rename is atomic, so there is nothing to guess.
    with open(marker + ".tmp", "w") as f:
        f.write(str(os.getpid()))
    os.replace(marker + ".tmp", marker)
    if mode == "exit":
        sys.exit(130)


signal.signal(signal.SIGINT, _on_int)

# The readiness file announces the ARM, never the start. Everything above
# this line runs under the inherited `SIG_IGN`, where a `SIGINT` is dropped
# on the floor rather than queued, so a reader that took the fork for the
# arm would be signalling into a void. Written-then-renamed, so a reader can
# never mistake a half-written file for the announcement.
with open(ready + ".tmp", "w") as f:
    f.write(str(os.getpid()))
os.replace(ready + ".tmp", ready)

deadline = time.monotonic() + 100.0
while time.monotonic() < deadline:
    time.sleep(0.05)
"""


def _child_body(jail_dir: str, marker: str, ready: str, mode: str) -> str:
    """The `workload_argv` body that runs `_INTERRUPT_CHILD`. The script is
    written into the jail directory rather than passed with `python -c`, so
    nothing has to survive two layers of shell quoting."""
    script = os.path.join(jail_dir, "child.py")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(_INTERRUPT_CHILD)
    return f"{sys.executable} {script} {marker} {ready} {mode}"


def _new_jail_dir(run_id: str) -> str:
    """A short scratch root -- `sun_path` is 104 bytes on darwin. The `ir`
    infix is this file's alone, so it cannot collide with a sibling's
    counter."""
    path = f"/tmp/bg{os.getpid()}ir{run_id[:8]}{next(_jail_counter)}"
    os.makedirs(path, exist_ok=True)
    return path


def _launch(argv: list[str], *, run_id: str) -> Handle:
    jail_dir = _new_jail_dir(run_id)
    return SubprocessLauncher().launch(
        Stack([]).compile(Spec()),
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"interrupt-{os.path.basename(jail_dir)}",
        jail_dir=jail_dir,
    )


def _group_members(pgid: int) -> list[int]:
    """Every pid the kernel currently places in `pgid`, per a fresh
    `/bin/ps -Ao pid=,pgid=` scan (alias-proof per decision-026 -- never a
    bare `ps`). The same technique `teardown.py` itself uses, reproduced
    here so a test's observation is not the code under test."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid="], capture_output=True, text=True, check=True
    )
    members: list[int] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and int(parts[1]) == pgid:
            members.append(int(parts[0]))
    return members


def _wait_until_empty(pgid: int, timeout: float = _SETTLE_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _group_members(pgid):
            return True
        time.sleep(0.02)
    return not _group_members(pgid)


def _launch_child(run_id: str, mode: str) -> tuple[Handle, str]:
    """A jail whose backgrounded child is `_INTERRUPT_CHILD` in `mode`,
    returned only once that child has ARMED its `SIGINT` handler. Returns
    the handle and the marker path the child writes on arrival.

    The readiness wait is what makes every caller's `interrupt()` a test of
    brig rather than a race against a cold interpreter -- see the module
    docstring. A child that never arms is torn down and reported as a broken
    workload, not left to fail later as a missing marker (which reads as
    "the signal did not arrive" and would send the next reader hunting in
    `Handle.interrupt`).
    """
    jail_dir = _new_jail_dir(run_id)
    marker = os.path.join(jail_dir, "sigint-arrived")
    ready = os.path.join(jail_dir, "sigint-armed")
    handle = SubprocessLauncher().launch(
        Stack([]).compile(Spec()),
        argv=workload_argv(run_id, _child_body(jail_dir, marker, ready, mode)),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"interrupt-{os.path.basename(jail_dir)}",
        jail_dir=jail_dir,
    )
    # ONE wait, on the ONE observation that means "a SIGINT sent now will be
    # caught", with its own full budget. Waiting on the group first would
    # spend that budget on a weaker fact -- a child that has armed has
    # certainly forked, so the fork is implied by what this waits for and
    # never needs its own clock.
    deadline = time.monotonic() + _START_S
    while not os.path.exists(ready) and time.monotonic() < deadline:
        time.sleep(0.02)
    if not os.path.exists(ready):
        teardown_group(handle)
        raise AssertionError(
            f"the workload child never armed its SIGINT handler within {_START_S}s "
            f"({ready!r} was never written), so a signal sent now would land in the "
            "inherited SIG_IGN and be discarded. The workload is broken; nothing "
            "below would have been a claim about brig."
        )
    return handle, marker


def _wait_for_marker(marker: str) -> str:
    deadline = time.monotonic() + _MARKER_S
    while time.monotonic() < deadline:
        if os.path.exists(marker):
            with open(marker, encoding="utf-8") as handle:
                content = handle.read()
            if content:
                return content
        time.sleep(0.02)
    raise AssertionError(
        f"no SIGINT reached the workload child within {_MARKER_S}s: {marker!r} was "
        "never written. The child had already ANNOUNCED its arm before the signal "
        "was sent, so this is a delivery failure, not a race with a cold start."
    )


@pytest.mark.integration
def test_interrupt_reaches_a_non_leader_member_of_the_group(run_id: str) -> None:
    """Claim 1: the signal arrives at the BACKGROUNDED CHILD, which reports
    its own pid from inside its handler -- a pid that is not the leader's,
    which is what "group, not leader" means. CONTROL, in the same test: the
    group has at least two members BEFORE the interrupt, so "the child got
    it" is not satisfied by a workload that never forked one."""
    handle, marker = _launch_child(run_id, "exit")
    try:
        # Read, not waited on: `_launch_child` already blocked until the
        # child announced its arm, and a child that has armed has forked.
        before = _group_members(handle.pgid)
        assert len(before) >= 2, (
            f"CONTROL failed: expected the leader and its backgrounded child in "
            f"pgid {handle.pgid}, got {before!r}"
        )

        assert handle.interrupt() is True

        reported = int(_wait_for_marker(marker))
        assert reported != handle.pid, (
            f"the marker names the LEADER ({handle.pid}), so this proves nothing "
            "about the rest of the group"
        )
        assert reported in before, (
            f"pid {reported} was not a member of pgid {handle.pgid}: {before!r}"
        )
        assert _wait_until_empty(handle.pgid), (
            f"pgid {handle.pgid} still had members after SIGINT: {_group_members(handle.pgid)!r}"
        )
    finally:
        teardown_group(handle)


@pytest.mark.integration
def test_interrupt_returns_true_for_a_workload_that_survives_the_signal(
    run_id: str,
) -> None:
    """Claim 2: the child takes the signal, records it, and KEEPS RUNNING.
    `interrupt()` returns `True` anyway -- `True` is deliverability -- and
    the group is still non-empty afterwards, which is the half that proves
    the return value is not quietly claiming an outcome nothing verified.
    The marker is what keeps it non-vacuous: the signal really arrived."""
    handle, marker = _launch_child(run_id, "survive")
    try:
        assert handle.interrupt() is True
        _wait_for_marker(marker)

        # Give the group every chance to clear, then observe that it has not.
        assert not _wait_until_empty(handle.pgid, timeout=1.0), (
            "the group cleared after all -- this test's whole point is a "
            "member that SURVIVES the interrupt, so it is now vacuous"
        )
    finally:
        teardown_group(handle)


@pytest.mark.integration
def test_interrupt_returns_false_once_the_group_is_gone(run_id: str) -> None:
    """Claim 3, with its own control: the SAME handle returns `True` while
    the group is there and `False` once it is not -- so `False` is
    attributable to the group's absence and not to this handle being
    unsignalable from the start."""
    handle = _launch(workload_argv(run_id, "sleep 100"), run_id=run_id)
    # A START wait, not a settle: the control below needs the group to be
    # THERE, and budgeting a process spawn at `_SETTLE_S` is the mistake the
    # module docstring's readiness note is about.
    deadline = time.monotonic() + _START_S
    while not _group_members(handle.pgid) and time.monotonic() < deadline:
        time.sleep(0.02)

    assert handle.interrupt() is True  # control: deliverable while it exists

    teardown_group(handle)
    assert _wait_until_empty(handle.pgid)

    assert handle.interrupt() is False
