"""`Jail.destroy()` / `teardown.kill_named`: group teardown of a launched
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
`Jail.create` and `jail.start` launches with `start_new_session=True` (task-019).

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
import ctypes
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator

import pytest

from brig.core import Spec, unenforced_report
from brig.run import IoPolicy, Jail, Process, _identity, _records
from brig.run import teardown as teardown_mod
from brig.run.teardown import KillOutcome, group_alive
from brig.stack import CompiledJail
from tests.conftest import destroy_with_grace, launch, workload_argv


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


def _gone_or_zombie(pid: int) -> bool:
    """Whether `pid` is gone, or has only exited and waits for a parent that
    does not reap (state `Z`). `os.kill(pid, 0)` succeeds on a zombie, so it
    cannot tell the two apart; where PID 1 does not reap (this container's
    `process_api`, Docker without `--init`), a killed jail's orphans stay
    zombies for good, and that is a jail that ended (decision-171)."""
    state = _ps_state(pid)
    return not state or state.startswith("Z")


def _ps_state(pid: int) -> str:
    """The `/bin/ps` state of `pid`, `""` when it has no row."""
    proc = subprocess.run(
        ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip()


def _launch(
    argv: list[str], *, jail_id: str = "jail-under-test", jail_dir: str
) -> tuple[Jail, Process]:
    return launch(
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


def _positive_pre_assertion(process: Process) -> tuple[int, int, int]:
    """AC #2: BEFORE any kill, prove the tree is real -- a second pid
    exists beyond the workload (leader) pid, it differs from the leader
    pid, and both report the same pgid. Returns (leader_pid, child_pid,
    pgid), parsed integers, for the caller to assert on directly and to
    print as evidence."""
    rows = _ps_rows()
    children = [pid for pid, ppid, _pgid in rows if ppid == process.pid]
    assert children, (
        f"expected the workload leader (pid={process.pid}) to have a live "
        f"child before any kill; full ps rows: {rows}"
    )
    child_pid = children[0]
    assert child_pid != process.pid

    leader_rows = [r for r in rows if r[0] == process.pid]
    child_rows = [r for r in rows if r[0] == child_pid]
    assert leader_rows and child_rows
    leader_pgid = leader_rows[0][2]
    child_pgid = child_rows[0][2]
    assert leader_pgid == child_pgid

    print(
        f"PRE-ASSERTION (AC #2): leader_pid={process.pid} child_pid={child_pid} "
        f"pgid={leader_pgid} (process._record.pgid={process._record.pgid})"
    )
    return process.pid, child_pid, leader_pgid


# ---------------------------------------------------------------------------
# AC #2 / #3 / #6 -- the positive pre-assertion, the claim, and the report shape.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_leaves_no_process_from_the_tree_alive(run_id: str, jail_dir: str) -> None:
    """AC #2 + #3 + #6 (THE CLAIM). This is also the deterministic test
    named by the out-of-band MUTATION CHECK (AC #5): replacing the group
    signal in `brig/run/teardown.py` with a single-pid signal to the
    leader makes exactly this test fail, because the child below stops
    being torn down."""
    argv = workload_argv(run_id, "sleep 100")
    jail, process = _launch(argv, jail_dir=jail_dir)
    leader_pid, child_pid, pgid = _positive_pre_assertion(process)
    assert pgid == process._record.pgid

    report = jail.destroy()

    # AC #3: every pid found in the pre-assertion, not just the leader.
    for pid in (leader_pid, child_pid):
        assert _gone_or_zombie(pid), f"pid {pid} is still running after kill()"

    # AC #6: per-item KillReport, the enum member asserted directly.
    assert len(report.items) >= 1
    workload_items = [item for item in report.items if item.kind == "workload_group"]
    assert len(workload_items) == 1
    item = workload_items[0]
    assert item.identity == str(process._record.pgid)
    assert item.outcome is KillOutcome.ENDED
    print(f"KillReport (AC #6): {report}")


# ---------------------------------------------------------------------------
# AC #4 -- THE CONTROL (test-local single-pid kill; no library edit).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_control_single_pid_kill_leaves_the_child_alive(run_id: str, jail_dir: str) -> None:
    """AC #4, THE CONTROL from `.claude/rules/integration-tests.md`'s
    control rule -- NOT the mutation check (see decision-026 rule 3,
    quoted in this task's description): no line of `brig/run/teardown.py`
    is touched here. A second, identically-shaped workload is torn down
    with a single `os.kill(leader_pid, SIGKILL)` instead of a group kill,
    and its child is shown to survive that -- proof that the tree-survival
    probe in the test above is discriminating, not vacuous."""
    argv = workload_argv(run_id, "sleep 100")
    jail, process = _launch(argv, jail_dir=jail_dir)
    leader_pid, child_pid, pgid = _positive_pre_assertion(process)

    try:
        # THE CONTROL: single-pid kill, deliberately not a group kill.
        os.kill(leader_pid, signal.SIGKILL)
        process.wait(timeout=20.0)

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
        process.wait(timeout=20.0)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _ps_has_row_for(child_pid):
            time.sleep(0.02)


# ---------------------------------------------------------------------------
# AC #7 -- verification is real (SIGKILL escalation), and its control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_escalates_to_sigkill_when_the_leader_ignores_sigterm(
    run_id: str, jail_dir: str
) -> None:
    """AC #7: a workload whose leader traps and ignores `SIGTERM` still
    ends up `ENDED`, and every pid from the pre-assertion is actually
    gone -- provable only if the SIGKILL escalation rung ran AND the
    post-signal verification is real (a report saying ENDED because
    SIGTERM was merely *sent* would be wrong here: the leader ignores it)."""
    body = "trap '' TERM; sleep 100"
    argv = workload_argv(run_id, body)
    jail, process = _launch(argv, jail_dir=jail_dir)
    leader_pid, child_pid, _pgid = _positive_pre_assertion(process)

    report = destroy_with_grace(jail, 0.3)

    for pid in (leader_pid, child_pid):
        assert _gone_or_zombie(pid), f"pid {pid} is still running after kill()"
    assert report.items[0].outcome is KillOutcome.ENDED


@pytest.mark.integration
def test_control_kill_ends_a_cooperative_group_without_needing_escalation(
    run_id: str, jail_dir: str
) -> None:
    """AC #7's control: a workload that exits on `SIGTERM` (no trap) also
    reports `ENDED` -- and does so well inside the grace window, without
    needing the `SIGKILL` rung. Without this, the escalation test above
    cannot distinguish "the SIGKILL rung actually ran" from "this
    machinery always reports ENDED no matter what"."""
    argv = workload_argv(run_id, "sleep 100")
    jail, process = _launch(argv, jail_dir=jail_dir)
    _positive_pre_assertion(process)

    started = time.monotonic()
    report = jail.destroy()  # default grace (2.0s)
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
# TASK-0077 / decision-171 -- a zombie in the group is gone.
# ---------------------------------------------------------------------------

_PR_SET_CHILD_SUBREAPER = 36

# A program that starts a child which exits at once, and never waits for it: a zombie in its group. It
# keeps the `Popen`, because a dropped one reaps its child in `__del__` when the child has already exited
# (always, on a machine loaded enough that the parent runs after it), and then no zombie is planted.
_PLANTS_A_ZOMBIE = 'import subprocess, time; zombie = subprocess.Popen(["true"]); time.sleep(100)'


@pytest.fixture
def non_reaping_init() -> Iterator[list[int]]:
    """Make THIS process the init of every orphan beneath it, and never reap
    them: the shape of a container whose PID 1 does not reap (this
    container's `process_api`, Docker without `--init`), reproduced under
    any real PID 1, tini included. `PR_SET_CHILD_SUBREAPER` sends a dead
    parent's children to the nearest subreaper ancestor, which here is the
    test process, and the test process never waits for them. The test adds
    the pids it planted to the yielded list, and only those are reaped at
    teardown (never an exit status a brig waiter thread is waiting for)."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        pytest.skip("PR_SET_CHILD_SUBREAPER is unavailable here")
    planted: list[int] = []
    try:
        yield planted
    finally:
        libc.prctl(_PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0)
        for pid in planted:
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, os.WNOHANG)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_CHILD_SUBREAPER is Linux")
@pytest.mark.integration
def test_kill_counts_a_zombie_the_init_never_reaps_as_gone(
    run_id: str, non_reaping_init: list[int], jail_dir: str
) -> None:
    """The jail's leader runs a child that exits at once and is never waited
    for, so a zombie sits in the jail's group. `kill()` ends the leader, the
    zombie is orphaned to a PID 1 that does not reap, and it stays in the
    table for good. The report must still say `ENDED`: the zombie has exited.
    Before decision-171 the `/bin/ps` scan counted it and the item was
    `FAILED`."""
    body = f"{sys.executable} -c '{_PLANTS_A_ZOMBIE}'"
    jail, process = _launch(workload_argv(run_id, body), jail_dir=jail_dir)
    deadline = time.monotonic() + 10
    zombies: list[int] = []
    while time.monotonic() < deadline and not zombies:
        zombies = [
            pid
            for pid, _ppid, pgid in _ps_rows()
            if pgid == process._record.pgid and _ps_state(pid).startswith("Z")
        ]
        time.sleep(0.05)
    assert zombies, "CONTROL failed: no zombie was planted in the jail's group"
    non_reaping_init.extend(pid for pid, _ppid, pgid in _ps_rows() if pgid == process._record.pgid)

    report = jail.destroy()

    still_there = [pid for pid in zombies if _ps_state(pid).startswith("Z")]
    assert still_there == zombies, "CONTROL failed: the zombie was reaped, so PID 1 reaps here"
    assert report.items[0].outcome is KillOutcome.ENDED, report.items[0].detail
    assert not jail.alive()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_CHILD_SUBREAPER is Linux")
@pytest.mark.integration
def test_group_alive_counts_a_zombie_the_init_never_reaps_as_gone(
    run_id: str, non_reaping_init: list[int], jail_dir: str
) -> None:
    """TASK-0079.19: a group whose only members are zombies reads gone through
    `group_alive`, though `os.killpg(pgid, 0)` still finds it."""
    body = f"{sys.executable} -c '{_PLANTS_A_ZOMBIE}'"
    jail, process = _launch(workload_argv(run_id, body), jail_dir=jail_dir)
    deadline = time.monotonic() + 10
    zombies: list[int] = []
    while time.monotonic() < deadline and not zombies:
        zombies = [
            pid
            for pid, _ppid, pgid in _ps_rows()
            if pgid == process._record.pgid and _ps_state(pid).startswith("Z")
        ]
        time.sleep(0.05)
    assert zombies, "CONTROL failed: no zombie was planted in the jail's group"
    non_reaping_init.extend(pid for pid, _ppid, pgid in _ps_rows() if pgid == process._record.pgid)
    assert group_alive(process._record.pgid), "a live leader keeps the group alive"

    os.killpg(process._record.pgid, signal.SIGKILL)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and group_alive(process._record.pgid):
        time.sleep(0.05)

    os.killpg(process._record.pgid, 0)  # CONTROL: the group is still found, by its zombies
    assert not group_alive(process._record.pgid)


_ZOMBIE_LEADER_PARENT = """
import subprocess, sys, time
leader = subprocess.Popen(
    [sys.executable, "-c", sys.argv[1]], start_new_session=True, stdout=subprocess.PIPE, text=True
)
print(leader.pid, leader.stdout.readline().strip(), flush=True)
time.sleep(100)
"""

_LEADER_THAT_LEAVES_A_MEMBER = (
    "import subprocess; m = subprocess.Popen(['sleep', '100']); print(m.pid, flush=True)"
)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_CHILD_SUBREAPER is Linux")
@pytest.mark.integration
def test_kill_ends_a_live_member_of_a_group_whose_leader_is_a_zombie(
    non_reaping_init: list[int],
    jail_dir: str,
) -> None:
    """The leader of the group has exited and sits as a zombie (its parent,
    another process, never waits for it), while a member of its group still
    runs. The leader reads gone, but the group is not: `kill()` must still
    signal the group, end that member, and only then report `ENDED`."""
    parent = subprocess.Popen(
        [sys.executable, "-c", _ZOMBIE_LEADER_PARENT, _LEADER_THAT_LEAVES_A_MEMBER],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert parent.stdout is not None
    leader_s, member_s = parent.stdout.readline().split()
    leader_pid, member_pid = int(leader_s), int(member_s)
    non_reaping_init.extend([leader_pid, member_pid])
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not _ps_state(leader_pid).startswith("Z"):
            time.sleep(0.02)
        assert _ps_state(leader_pid).startswith("Z"), "CONTROL failed: the leader is not a zombie"
        assert _ps_state(member_pid) and not _gone_or_zombie(member_pid), (
            "CONTROL failed: the member is not running"
        )
        leader = _records.ProcessRecord(
            id="",
            order=0,
            pid=leader_pid,
            pgid=leader_pid,
            start_time=_identity.start_stamp(leader_pid),
            argv=(),
            stdout_path="",
            stderr_path="",
        )

        report = teardown_mod.kill_named(
            known=(leader,), jail_dir=jail_dir, helper_pids=(), helper_stamps=(), grace=0.5
        )

        assert _gone_or_zombie(member_pid), "the live member survived kill()"
        assert report.items[0].outcome is KillOutcome.ENDED, report.items[0].detail
    finally:
        # A member kill() missed must not outlive the test.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(leader_pid, signal.SIGKILL)
        parent.kill()
        parent.wait()


# ---------------------------------------------------------------------------
# AC #8 -- idempotence.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_is_idempotent(run_id: str, jail_dir: str) -> None:
    """AC #8: a second `kill()` on the same handle reports `ALREADY_GONE`
    and raises nothing."""
    argv = workload_argv(run_id, "sleep 100")
    jail, process = _launch(argv, jail_dir=jail_dir)
    _positive_pre_assertion(process)

    first = jail.destroy()
    assert first.items[0].outcome is KillOutcome.ENDED

    second = jail.destroy()  # must not raise
    assert second.items[0].outcome is KillOutcome.ALREADY_GONE
    assert second.items[0].kind == "workload_group"
    assert second.items[0].identity == str(process._record.pgid)


# ---------------------------------------------------------------------------
# AC #9 -- the record teardown leaves behind.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_returns_the_teardown_record_and_writes_none(run_id: str, jail_dir: str) -> None:
    """AC #9. It used to read a decodable `KILL` record out of the jail's
    events file. decision-152 (2026-09-08) deleted the stream and the
    `KILL` kind with it: the returned `KillReport` was always the richer
    record (the events were written FROM it, one per item, after the fact),
    so what is checked now is the report itself -- and that teardown wrote
    no log beside it, which is the half a deletion has to prove.

    **Exactly one file appears, and teardown did not write it**
    (decision-156, 2026-09-08): the process's exit record (since
    decision-181 `<jail_dir>/procs/<id>/exit`), written by the exit
    wrapper as the group came down, holding `-15` because the ladder's first
    rung is what ended the workload. Asserting its CONTENT rather than
    merely tolerating its name is what keeps this a claim: the ordinary
    teardown rung leaves a status a later process can still read, and only
    the `SIGKILL` rung does not."""
    argv = workload_argv(run_id, "sleep 100")
    jail, process = _launch(argv, jail_id="jail-kill-evt", jail_dir=jail_dir)
    _positive_pre_assertion(process)

    records_dir = os.path.dirname(process.stdout_path)
    before = sorted(os.listdir(jail.jail_dir))
    before_records = sorted(os.listdir(records_dir))
    report = jail.destroy()

    assert len(report.items) == 1
    item = report.items[0]
    assert item.kind == "workload_group"
    assert item.identity == str(process._record.pgid)
    assert int(item.identity) == process._record.pgid
    assert item.outcome is KillOutcome.ENDED

    assert sorted(os.listdir(jail.jail_dir)) == before, "teardown wrote into the jail directory"
    after = sorted(os.listdir(records_dir))
    assert set(after) - set(before_records) == {_records.EXIT_FILENAME}, (
        f"teardown left files beside the exit record: {sorted(set(after) - set(before_records))!r}"
    )
    with open(os.path.join(records_dir, _records.EXIT_FILENAME), encoding="utf-8") as recorded:
        assert recorded.read().strip() == str(-signal.SIGTERM)
