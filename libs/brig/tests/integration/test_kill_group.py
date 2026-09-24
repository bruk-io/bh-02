"""`Handle.kill()` / `teardown.kill_jail`: group teardown of a launched
workload, per SPEC.md §9's fixed ladder (SIGTERM -> grace -> SIGKILL ->
VERIFY -> report).

MILESTONES.md M2 exit criterion 2, the spec anchor for this whole file:

    Group-kill mutation check: a workload that spawns a child (`bash -c
    'sleep 100 & wait'`-shaped); after `kill()`, no process from the tree
    survives -- and a deliberately single-pid kill (test-local) is shown
    to leak the child, proving the tree check detects what group-kill
    fixes.

Every workload here is built through `tests.conftest.workload_argv`, which
already produces exactly the `<body> & wait` shape the exit criterion
names when given `body="sleep 100"` (see that function's docstring) -- a
leader `bash` process that backgrounds a `sleep 100` child and then blocks
in `wait`, both landing in the leader's own process group because
`SubprocessLauncher` launches with `start_new_session=True` (task-019).

Vocabulary, per decision-026 rule 3 (quoted in this task's description --
read it before touching this file): THE CONTROL below is a test-local
single-pid kill that leaves a child alive, proving the tree-survival probe
discriminates a leak from a clean teardown. THE MUTATION CHECK is a
separate, out-of-band exercise against `brig/run/teardown.py` itself
(edit -> named test reds -> revert -> hash-proven restoration), evidenced
in the task's notes, not encoded as a standing test in this file -- a
mutation check that lived in the suite would leave `teardown.py` mutated
on every green run, which is exactly backwards.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import signal
import subprocess
import time

import pytest

from brig.core import Spec, unenforced_report
from brig.run import teardown as teardown_mod
from brig.run._exit_status import EXIT_FILENAME
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.run.teardown import KillOutcome
from brig.stack import CompiledJail
from tests.conftest import workload_argv

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>kg<n>` -- never `tmp_path`
    (CLAUDE.md: `sun_path` is 104 bytes on darwin).

    The `kg` (kill-group) infix is load-bearing, not decorative:
    `test_launcher.py`, `test_wait_ready.py` and `test_exec.py` each mint
    their own `/tmp/bg<pid>-<n>` sequence from an independent
    `itertools.count()` starting at 0 -- under `pytest -m integration`
    every one of these files shares the SAME `os.getpid()` (one pytest
    process), so without a distinguishing infix this file's Nth jail dir
    is byte-identical to some other file's Nth jail dir, and whichever
    test runs second silently inherits the first's leftover directory
    (observed: this collided with `test_launcher.py`'s
    `test_launch_refuses_a_jail_that_requires_pty`, which asserts its
    jail_dir was never created, and its `test_spawn_event_...`, which read
    back a stale `events.jsonl` from an unrelated jail_id -- only when all
    four integration files ran together, not in any 3-of-4 subset, because
    the collision depends on the exact cumulative dir count at the moment
    each file happens to reuse an index). This infix removes THIS file
    from that shared, order-dependent namespace; it does not fix the
    remaining risk between `test_launcher.py`, `test_wait_ready.py` and
    `test_exec.py`, which are outside this task's Deliverable."""
    return f"/tmp/bg{os.getpid()}kg{next(_jail_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail() -> CompiledJail:
    """The empty stack's shape (SPEC.md §3): mechanism-free, every axis
    unenforced, no requires -- kill/teardown does not care what the stack
    was, only what process group the launcher started."""
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


def _launch(argv: list[str], *, jail_id: str = "jail-under-test") -> Handle:
    jail_dir = _new_jail_dir()
    launcher = SubprocessLauncher()
    return launcher.launch(
        _compiled_jail(),
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _ps_rows() -> list[tuple[int, int, int]]:
    """(pid, ppid, pgid) for every process visible right now (alias-proof
    `/bin/ps`, decision-026 -- never a bare `ps`)."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,ppid=,pgid="],
        capture_output=True,
        text=True,
        check=True,
    )
    rows: list[tuple[int, int, int]] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return rows


def _ps_has_row_for(pid: int) -> bool:
    """`/bin/ps -p <pid>` literally (per AC #3's wording) -- a dead-but-
    valid pid returns a non-zero exit and only the header line."""
    proc = subprocess.run(["/bin/ps", "-p", str(pid)], capture_output=True, text=True)
    data_lines = [line for line in proc.stdout.strip().splitlines()[1:] if line.strip()]
    return proc.returncode == 0 and bool(data_lines)


def _positive_pre_assertion(handle: Handle) -> tuple[int, int, int]:
    """AC #2: BEFORE any kill, prove the tree is real -- a second pid
    exists beyond the workload (leader) pid, it differs from the leader
    pid, and both report the same pgid. Returns (leader_pid, child_pid,
    pgid), parsed integers, for the caller to assert on directly and to
    print as evidence."""
    rows = _ps_rows()
    children = [pid for pid, ppid, _pgid in rows if ppid == handle.pid]
    assert children, (
        f"expected the workload leader (pid={handle.pid}) to have a live "
        f"child before any kill; full ps rows: {rows}"
    )
    child_pid = children[0]
    assert child_pid != handle.pid

    leader_rows = [r for r in rows if r[0] == handle.pid]
    child_rows = [r for r in rows if r[0] == child_pid]
    assert leader_rows and child_rows
    leader_pgid = leader_rows[0][2]
    child_pgid = child_rows[0][2]
    assert leader_pgid == child_pgid

    print(
        f"PRE-ASSERTION (AC #2): leader_pid={handle.pid} child_pid={child_pid} "
        f"pgid={leader_pgid} (handle.pgid={handle.pgid})"
    )
    return handle.pid, child_pid, leader_pgid


# ---------------------------------------------------------------------------
# AC #2 / #3 / #6 -- the positive pre-assertion, the claim, and the report shape.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_leaves_no_process_from_the_tree_alive(run_id: str) -> None:
    """AC #2 + #3 + #6 (THE CLAIM). This is also the deterministic test
    named by the out-of-band MUTATION CHECK (AC #5): replacing the group
    signal in `brig/run/teardown.py` with a single-pid signal to the
    leader makes exactly this test fail, because the child below stops
    being torn down."""
    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv)
    leader_pid, child_pid, pgid = _positive_pre_assertion(handle)
    assert pgid == handle.pgid

    report = handle.kill()

    # AC #3: every pid found in the pre-assertion, not just the leader.
    for pid in (leader_pid, child_pid):
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert not _ps_has_row_for(pid), f"pid {pid} still has a /bin/ps -p row after kill()"

    # AC #6: per-item KillReport, the enum member asserted directly.
    assert len(report.items) >= 1
    workload_items = [item for item in report.items if item.kind == "workload_group"]
    assert len(workload_items) == 1
    item = workload_items[0]
    assert item.identity == str(handle.pgid)
    assert item.outcome is KillOutcome.ENDED
    print(f"KillReport (AC #6): {report}")


# ---------------------------------------------------------------------------
# AC #4 -- THE CONTROL (test-local single-pid kill; no library edit).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_control_single_pid_kill_leaves_the_child_alive(run_id: str) -> None:
    """AC #4, THE CONTROL from `.claude/rules/integration-tests.md`'s
    control rule -- NOT the mutation check (see decision-026 rule 3,
    quoted in this task's description): no line of `brig/run/teardown.py`
    is touched here. A second, identically-shaped workload is torn down
    with a single `os.kill(leader_pid, SIGKILL)` instead of a group kill,
    and its child is shown to survive that -- proof that the tree-survival
    probe in the test above is discriminating, not vacuous."""
    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv)
    leader_pid, child_pid, pgid = _positive_pre_assertion(handle)

    try:
        # THE CONTROL: single-pid kill, deliberately not a group kill.
        os.kill(leader_pid, signal.SIGKILL)
        handle.wait(timeout=20.0)

        # Give the kernel a moment, then assert POSITIVELY that the child
        # is still a live, running process -- not merely an unreaped
        # zombie entry.
        deadline = time.monotonic() + 2.0
        state = ""
        while time.monotonic() < deadline:
            proc = subprocess.run(
                ["/bin/ps", "-o", "state=", "-p", str(child_pid)],
                capture_output=True,
                text=True,
            )
            state = proc.stdout.strip()
            if state:
                break
            time.sleep(0.02)
        print(f"CONTROL (AC #4): child_pid={child_pid} state after single-pid kill: {state!r}")
        assert state, f"expected child pid {child_pid} to still be present in /bin/ps"
        assert not state.startswith("Z"), (
            f"child pid {child_pid} is a zombie, not running: {state!r}"
        )
        os.kill(child_pid, 0)  # does not raise -- the child is genuinely alive
    finally:
        # Clean up what the control deliberately leaked, via the group --
        # never leave a leaked child for the suite's leak-check to catch
        # ITSELF as a bug; this is the test cleaning up after its own
        # deliberate leak.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
        handle.wait(timeout=20.0)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _ps_has_row_for(child_pid):
            time.sleep(0.02)


# ---------------------------------------------------------------------------
# AC #7 -- verification is real (SIGKILL escalation), and its control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_escalates_to_sigkill_when_the_leader_ignores_sigterm(run_id: str) -> None:
    """AC #7: a workload whose leader traps and ignores `SIGTERM` still
    ends up `ENDED`, and every pid from the pre-assertion is actually
    gone -- provable only if the SIGKILL escalation rung ran AND the
    post-signal verification is real (a report saying ENDED because
    SIGTERM was merely *sent* would be wrong here: the leader ignores it)."""
    body = "trap '' TERM; sleep 100"
    argv = workload_argv(run_id, body)
    handle = _launch(argv)
    leader_pid, child_pid, _pgid = _positive_pre_assertion(handle)

    report = teardown_mod.kill_jail(handle, grace=0.3)

    for pid in (leader_pid, child_pid):
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    assert report.items[0].outcome is KillOutcome.ENDED


@pytest.mark.integration
def test_control_kill_ends_a_cooperative_group_without_needing_escalation(run_id: str) -> None:
    """AC #7's control: a workload that exits on `SIGTERM` (no trap) also
    reports `ENDED` -- and does so well inside the grace window, without
    needing the `SIGKILL` rung. Without this, the escalation test above
    cannot distinguish "the SIGKILL rung actually ran" from "this
    machinery always reports ENDED no matter what"."""
    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv)
    _positive_pre_assertion(handle)

    started = time.monotonic()
    report = teardown_mod.kill_jail(handle)  # default grace (2.0s)
    elapsed = time.monotonic() - started

    assert report.items[0].outcome is KillOutcome.ENDED
    # A cooperative group dies on SIGTERM alone; if this ever needed the
    # SIGKILL escalation it would take north of one grace period (2.0s).
    # 1.0s margin (half the grace) rather than a near-zero one: this
    # module's poll loop shells out to /bin/ps on every iteration, and
    # under a loaded suite (this file runs alongside three other
    # integration files) a tight margin here would be a plausible flake
    # unrelated to the property being tested.
    assert elapsed < 1.0, (
        f"cooperative group took {elapsed:.3f}s -- looks like it needed escalation"
    )


# ---------------------------------------------------------------------------
# AC #8 -- idempotence.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_is_idempotent(run_id: str) -> None:
    """AC #8: a second `kill()` on the same handle reports `ALREADY_GONE`
    and raises nothing."""
    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv)
    _positive_pre_assertion(handle)

    first = handle.kill()
    assert first.items[0].outcome is KillOutcome.ENDED

    second = handle.kill()  # must not raise
    assert second.items[0].outcome is KillOutcome.ALREADY_GONE
    assert second.items[0].kind == "workload_group"
    assert second.items[0].identity == str(handle.pgid)


# ---------------------------------------------------------------------------
# AC #9 -- the record teardown leaves behind.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_returns_the_teardown_record_and_writes_none(run_id: str) -> None:
    """AC #9. It used to read a decodable `KILL` record out of the jail's
    events file. decision-152 (2026-09-08) deleted the stream and the
    `KILL` kind with it: the returned `KillReport` was always the richer
    record (the events were written FROM it, one per item, after the fact),
    so what is checked now is the report itself -- and that teardown wrote
    no log beside it, which is the half a deletion has to prove.

    **Exactly one file appears, and teardown did not write it**
    (decision-156, 2026-09-08): `<jail_dir>/exit`, written by the exit
    wrapper as the group came down, holding `-15` because the ladder's first
    rung is what ended the workload. Asserting its CONTENT rather than
    merely tolerating its name is what keeps this a claim: the ordinary
    teardown rung leaves a status a later process can still read, and only
    the `SIGKILL` rung does not."""
    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv, jail_id="jail-kill-evt")
    _positive_pre_assertion(handle)

    before = sorted(os.listdir(handle.jail_dir))
    report = handle.kill()

    assert len(report.items) == 1
    item = report.items[0]
    assert item.kind == "workload_group"
    assert item.identity == str(handle.pgid)
    assert int(item.identity) == handle.pgid
    assert item.outcome is KillOutcome.ENDED

    after = sorted(os.listdir(handle.jail_dir))
    assert set(after) - set(before) == {EXIT_FILENAME}, (
        f"teardown left files beside the exit record: {sorted(set(after) - set(before))!r}"
    )
    with open(os.path.join(handle.jail_dir, EXIT_FILENAME), encoding="utf-8") as recorded:
        assert recorded.read().strip() == str(-signal.SIGTERM)
