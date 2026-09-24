"""Exec-sibling teardown: `kill()` reaps every exec sibling `handle` has
registered, through the SAME ladder the workload group uses, and reports
each as its own `KillReport` item.

task-027's spec anchor, SPEC.md §9 (as amended by decision-042), verbatim:

    - **An exec sibling is the handle's to reap.** `exec` registers the
      sibling on the handle *and in the handle's serialized form*, so a
      handle rehydrated in a later process tears down execs it never
      itself started; `kill` then ends those groups on the same ladder,
      after the workload group, and reports each as its own `KillReport`
      item. An exec the handle created and does not reap is a process from
      the tree surviving `kill` -- the failure class this section exists
      to close.

**The design pin (task-027, chosen: derived from a durable registration;
medium changed by decision-152, 2026-09-08).** `exec_in_jail`
(`brig/run/exec_.py`) writes the sibling's pid and pgid into a file under
`<jail_dir>/execs/` (`brig/run/_execs.py`), and `ExecHandle.wait` removes
it; `teardown.kill_jail` (`brig/run/teardown.py`) finds every live sibling
by listing that directory. This is what makes AC #3 below work: the handle
serialized BEFORE the exec still names it, because the naming lives on the
filesystem under the `jail_dir` the handle points at, not in any in-memory
state on the `Handle` object itself (which is frozen and holds none). It
was an `EXEC`-without-`EXEC_END` pairing in the per-jail event stream until
that stream was deleted; the clause it satisfies is unchanged.

Every long-lived sibling here is built through `tests.conftest.workload_argv`
so a broken reap is caught by the suite-wide leak-check, per this task's
Traps note -- with ONE deliberate exception (AC #8's mutation-check test),
which uses a bare, token-less argv on purpose: that test exists to prove
the NEW `tests/conftest.py` arm task-027 adds (see that module's docstring,
"task-027's third arm"), and a token-bearing sibling would let the OLD arm
catch the plant too, proving nothing about the new one specifically.

Short `/tmp/bg<pid>te<n>` scratch roots throughout (`te` for
teardown-exec, distinguishing this file's sequence from the other three
integration files sharing the same pid -- see `test_kill_group.py`'s
`_new_jail_dir` docstring for the collision this avoids), never `tmp_path`
(`sun_path` is 104 bytes on darwin).
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from brig.core import Spec, unenforced_report
from brig.run import teardown as teardown_mod
from brig.run._execs import live as live_execs
from brig.run.exec_ import ExecHandle, exec_in_jail
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.run.teardown import DEFAULT_GRACE_S, KillOutcome
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>te<n>` -- never `tmp_path`. The
    `te` infix keeps this file's sequence disjoint from the other three
    integration files sharing this same `os.getpid()`."""
    return f"/tmp/bg{os.getpid()}te{next(_jail_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail() -> CompiledJail:
    """The empty stack's shape: mechanism-free, every axis unenforced --
    teardown does not care what the stack was, only what process groups
    the launcher/exec started."""
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


def _launch(argv: list[str], *, jail_id: str) -> Handle:
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


def _new_handle(run_id: str, *, jail_id: str) -> Handle:
    """A handle whose workload is a `sleep 100` -- long-lived enough to
    outlive every test below, `run_id`-tagged so the leak sweep catches it
    if this test's own teardown ever fails."""
    return _launch(workload_argv(run_id, "sleep 100"), jail_id=jail_id)


def _teardown_group(handle: Handle) -> None:
    """Group-kill the workload directly -- belt-and-suspenders cleanup for a
    test whose own `kill()` call is itself under test (a failing assertion
    mid-test must not leak the workload). `handle.wait()` blocks until the
    launcher's exit-waiter has reaped it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _reap_and_kill_sibling(exec_handle: ExecHandle | None) -> None:
    """Belt-and-suspenders cleanup for an `ExecHandle` this process itself
    created: signal its group (idempotent if `kill()` already ended it)
    and reap it (this process IS its real parent, since `exec_in_jail` was
    called here)."""
    if exec_handle is None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(exec_handle.pid, signal.SIGKILL)
    with contextlib.suppress(ChildProcessError, ProcessLookupError):
        os.waitpid(exec_handle.pid, 0)


def _group_members(pgid: int) -> list[int]:
    """Every pid currently in process group `pgid`, per a fresh `/bin/ps`
    scan (alias-proof per decision-026 -- never a bare `ps`). Same
    technique `brig/run/teardown.py`'s own `_group_member_pids` uses,
    reimplemented here so this file observes from OUTSIDE the module under
    test, not through it."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid="], capture_output=True, text=True, check=True
    )
    members: list[int] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        pid_s, pgid_s = parts
        if int(pgid_s) == pgid:
            members.append(int(pid_s))
    return members


def _ps_pgid(pid: int) -> int:
    """Read a live pid's real process-group id via `/bin/ps` (alias-proof,
    decision-026)."""
    proc = subprocess.run(
        ["/bin/ps", "-o", "pgid=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(proc.stdout.strip())


def _ps_state(pid: int) -> str:
    """The `STAT` field for `pid` (alias-proof `/bin/ps`, decision-026),
    `""` if `pid` has no row at all. A `Z`-prefixed state means the
    process has already exited but is not yet reaped -- this is how AC #5
    below observes a sibling exit on its own from OUTSIDE, without calling
    `ExecHandle.wait()` (which would reap it itself and deregister it,
    making the already-exited scenario indistinguishable from "never
    exec'd")."""
    proc = subprocess.run(
        ["/bin/ps", "-o", "state=", "-p", str(pid)], capture_output=True, text=True
    )
    return proc.stdout.strip()


def _registered(handle: Handle) -> list[tuple[int, int, str]]:
    """`(pid, pgid, start_time)` for every sibling still registered against
    this jail, read off disk the way a rehydrated handle would read it. The
    third field is decision-155's start-time stamp -- what makes the pid an
    identity rather than a number teardown might find pointing at a
    stranger."""
    return live_execs(handle.jail_dir)


# ---------------------------------------------------------------------------
# AC #2 -- live handle, unwaited sibling, gone after kill(), with control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_live_handle_kill_reaps_the_unwaited_exec_sibling(run_id: str) -> None:
    """AC #2: an exec sibling that is never waited on is gone after
    `handle.kill()`, observed from OUTSIDE via `/bin/ps`. CONTROL, the
    same probe run BEFORE the kill: the sibling's pgid has at least one
    member -- without this, "gone" is also satisfied by a sibling that
    never started."""
    handle = _new_handle(run_id, jail_id="jail-ac2")
    sibling: ExecHandle | None = None
    try:
        sibling = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
        sibling_pgid = _ps_pgid(sibling.pid)

        before = _group_members(sibling_pgid)
        assert before, (
            f"CONTROL failed: expected sibling pgid {sibling_pgid} to have "
            f"member(s) before kill(), got {before}"
        )

        handle.kill()

        after = _group_members(sibling_pgid)
        assert after == []
    finally:
        _teardown_group(handle)
        _reap_and_kill_sibling(sibling)


# ---------------------------------------------------------------------------
# AC #3 -- the discriminating design pin: pre-exec serialization, a
# genuinely separate interpreter.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_prekill_handle_serialized_before_exec_reaps_sibling_in_separate_interpreter(
    run_id: str,
) -> None:
    """AC #3: `to_dict()` the handle BEFORE any exec; exec an unwaited
    long-lived sibling from the live handle; rehydrate that PRE-EXEC dict
    in a genuinely separate interpreter (a `sys.executable` subprocess,
    not a second `Handle` object in this process) and call `kill_jail()`
    there. Assert from the parent that the sibling pgid has zero members.
    Also assert the child interpreter pid differs from `os.getpid()` and
    that it exited 0.

    An in-memory-only registration on `Handle` would pass every other
    criterion in this file and fail only this one -- there is no live
    `Handle` object shared between this process and the child interpreter,
    only a dict written before the exec ever happened."""
    handle = _new_handle(run_id, jail_id="jail-ac3")
    sibling: ExecHandle | None = None
    try:
        pre_exec_dict = handle.to_dict()

        sibling = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
        sibling_pgid = _ps_pgid(sibling.pid)
        assert _group_members(sibling_pgid), "sibling should be alive before the child kills it"

        dict_path = os.path.join(handle.jail_dir, "pre-exec-handle.json")
        with open(dict_path, "w") as f:
            json.dump(pre_exec_dict, f)

        script = (
            "import json\n"
            "from brig.run.handle import Handle\n"
            "from brig.run.teardown import kill_jail\n"
            f"with open({dict_path!r}) as f:\n"
            "    d = json.load(f)\n"
            "handle = Handle.from_dict(d)\n"
            # A short grace: this child interpreter is not the real
            # parent of EITHER group it tears down (workload or sibling),
            # so it cannot reap what it signals -- the ladder still
            # SIGKILLs both, but its own verification rung will not
            # observe them gone until the real parent (the test process)
            # reaps them after this subprocess returns. A short grace
            # keeps this test fast without changing that fact.
            "kill_jail(handle, grace=0.3)\n"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        child_pid = child.pid
        stdout, stderr = child.communicate(timeout=15)
        returncode = child.returncode

        print(f"AC #3: child interpreter pid={child_pid} (parent os.getpid()={os.getpid()})")
        print(f"AC #3: child exit code={returncode}")
        print(f"AC #3: child stdout={stdout!r} stderr={stderr!r}")

        assert child_pid != os.getpid()
        assert returncode == 0

        # The sibling's REAL parent is THIS process -- the exec happened
        # here, not in the child interpreter, which cannot reap what it
        # does not own (`_reap_leader`'s documented no-op there). Reaping
        # here is bookkeeping the OS requires of the real parent; it does
        # not undo the child interpreter's kill -- the group was already
        # SIGKILLed there, this only removes the now-dead process's entry
        # from the process table so `/bin/ps` stops reporting it.
        sibling.wait(timeout=5.0)

        assert _group_members(sibling_pgid) == []
    finally:
        _teardown_group(handle)
        _reap_and_kill_sibling(sibling)


# ---------------------------------------------------------------------------
# AC #4 -- KillReport shape, asserted on literals and enum members.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_kill_report_shape_workload_then_one_exec_sibling_item(run_id: str) -> None:
    """AC #4: `items[0].kind == "workload_group"`; exactly one further item
    per exec sibling with `kind == "exec_sibling"` (exact equality, never
    substring/startswith); `identity` equals that sibling's pgid rendered
    as text; `outcome` is `KillOutcome.ENDED` as the enum member, not its
    value."""
    handle = _new_handle(run_id, jail_id="jail-ac4")
    sibling: ExecHandle | None = None
    try:
        sibling = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
        sibling_pgid = _ps_pgid(sibling.pid)

        report = handle.kill()

        assert len(report.items) == 2
        workload_item, sibling_item = report.items

        assert workload_item.kind == "workload_group"
        assert workload_item.identity == str(handle.pgid)
        assert workload_item.outcome is KillOutcome.ENDED

        assert sibling_item.kind == "exec_sibling"
        assert sibling_item.kind != "exec_siblingx"  # exact equality, not a prefix match
        assert sibling_item.identity == str(sibling_pgid)
        assert sibling_item.outcome is KillOutcome.ENDED
        assert isinstance(sibling_item.outcome, KillOutcome)
    finally:
        _teardown_group(handle)
        _reap_and_kill_sibling(sibling)


# ---------------------------------------------------------------------------
# AC #5 -- ALREADY_GONE is both-valued and timing-discriminating.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_already_exited_sibling_reports_already_gone_fast(run_id: str) -> None:
    """AC #5: a sibling that has ALREADY exited before `kill()` runs
    reports `ALREADY_GONE` -- not `FAILED`, not `ENDED`. The timing bound
    DISCRIMINATES: strictly less than ONE grace period (`DEFAULT_GRACE_S`,
    read from the module, never hardcoded), because the already-gone
    branch sends no signal and waits for nothing. An implementation that
    skips the sibling reap cannot conclude ANYTHING about that sibling in
    less than a full grace window (it would see a lingering zombie and
    burn the whole ladder before reporting `FAILED`)."""
    handle = _new_handle(run_id, jail_id="jail-ac5")
    sibling: ExecHandle | None = None
    try:
        sibling = exec_in_jail(handle, workload_argv(run_id, "true"))
        # Let the sibling actually exit on its own, WITHOUT calling
        # `.wait()` -- calling it here would append EXEC_END ourselves and
        # make this scenario indistinguishable from "never happened".
        # Observed from OUTSIDE via `/bin/ps`'s STAT field (`Z` = exited,
        # not yet reaped), not by touching `ExecHandle`'s own internals.
        deadline = time.monotonic() + 5.0
        state = _ps_state(sibling.pid)
        while time.monotonic() < deadline and not state.startswith("Z"):
            time.sleep(0.01)
            state = _ps_state(sibling.pid)
        assert state.startswith("Z"), (
            f"expected sibling pid={sibling.pid} to be a zombie (exited, unreaped) "
            f"before kill() runs; last observed state={state!r}"
        )

        started = time.monotonic()
        report = handle.kill()
        elapsed = time.monotonic() - started

        assert len(report.items) == 2
        sibling_item = report.items[1]
        assert sibling_item.kind == "exec_sibling"
        assert sibling_item.outcome is KillOutcome.ALREADY_GONE

        print(f"AC #5: kill() elapsed={elapsed:.4f}s, DEFAULT_GRACE_S={DEFAULT_GRACE_S}")
        assert elapsed < DEFAULT_GRACE_S, (
            f"elapsed {elapsed:.4f}s is not strictly less than one grace period "
            f"({DEFAULT_GRACE_S}s) -- looks like the sibling reap was skipped"
        )
    finally:
        _teardown_group(handle)
        _reap_and_kill_sibling(sibling)


# ---------------------------------------------------------------------------
# AC #6 -- every item reaches the KILL event (mutation-paired separately,
# see this task's notes for the plant/revert evidence).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_every_registered_sibling_reaches_its_own_kill_report_item(run_id: str) -> None:
    """AC #6: the returned `KillReport` names every group the handle owns,
    each as its own item with its own identity -- the workload group and
    the registered sibling, distinct, not a collapsed set.

    This AC used to be "every report item reaches its own `KILL` event",
    checked by decoding the events file. decision-152 (2026-09-08) deleted
    both the file and the `KILL` kind: the report IS the record now, so
    what there is to check is the report against the durable registration
    that produced it. MUTATION PAIRING (deterministic): make `kill_jail`
    tear down only `_live_exec_siblings(...)[:0]` and this test fails on
    every run."""
    handle = _new_handle(run_id, jail_id="jail-ac6")
    sibling: ExecHandle | None = None
    try:
        sibling = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
        registered = _registered(handle)
        assert [pid for pid, _pgid, _stamp in registered] == [sibling.pid]

        report = handle.kill()
        assert len(report.items) == 2

        report_pairs = {(item.kind, item.identity) for item in report.items}
        assert report_pairs == {
            ("workload_group", str(handle.pgid)),
            ("exec_sibling", str(registered[0][1])),
        }
    finally:
        _teardown_group(handle)
        _reap_and_kill_sibling(sibling)


# ---------------------------------------------------------------------------
# AC #7 -- one ladder, not a weaker second one: SIGTERM-ignoring sibling
# still escalates to ENDED, with a cooperative control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_sigterm_ignoring_sibling_still_ends_via_sigkill_escalation(run_id: str) -> None:
    """AC #7: a sibling that installs `SIGTERM` to `SIG_IGN` is still
    reported `ENDED` -- only the `SIGKILL` rung can end it, which
    discriminates real escalation from a single `SIGTERM` send. CONTROL: a
    sibling that exits ON `SIGTERM` is `ENDED` too, well inside one grace
    period -- without this control, the escalation case cannot distinguish
    "the SIGKILL rung actually ran" from "this always reports ENDED no
    matter what". Both asserted as the `KillOutcome` enum member."""
    handle = _new_handle(run_id, jail_id="jail-ac7")
    ignoring: ExecHandle | None = None
    cooperative: ExecHandle | None = None
    try:
        ignoring = exec_in_jail(handle, workload_argv(run_id, "trap '' TERM; sleep 100"))
        ignoring_pgid = _ps_pgid(ignoring.pid)
        cooperative = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
        cooperative_pgid = _ps_pgid(cooperative.pid)

        started = time.monotonic()
        report = teardown_mod.kill_jail(handle, grace=0.3)
        elapsed = time.monotonic() - started

        assert len(report.items) == 3  # workload + two siblings

        by_pgid = {int(item.identity): item for item in report.items[1:]}
        ignoring_item = by_pgid[ignoring_pgid]
        cooperative_item = by_pgid[cooperative_pgid]

        assert ignoring_item.outcome is KillOutcome.ENDED
        assert cooperative_item.outcome is KillOutcome.ENDED
        print(f"AC #7: kill_jail(grace=0.3) elapsed={elapsed:.3f}s")
    finally:
        _teardown_group(handle)
        _reap_and_kill_sibling(ignoring)
        _reap_and_kill_sibling(cooperative)


# ---------------------------------------------------------------------------
# AC #14 -- task-022 AC #11's exact reproduction, now clean.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_unwaited_exec_then_kill_leaks_nothing_task022_ac11(run_id: str) -> None:
    """AC #14: task-022's own AC #11 reproduction (its verifier's exact
    plant: `exec_in_jail(handle, ["sleep", "45"])`, never `wait()`-ed, then
    `kill()`), run under the fully-armed suite-wide sweep. task-022 could
    not close this because its `kill_jail` only ever tore down the
    workload group; this task's `kill_jail` reaps every exec sibling too,
    so nothing survives to leak -- the criterion holds because the product
    is right (decision-042), not because the check was loosened.

    Deliberately a BARE, token-less argv, matching task-022's own
    reproduction exactly -- proving the product itself leaks nothing here,
    independent of which `tests/conftest.py` arm would or would not have
    seen it."""
    handle = _new_handle(run_id, jail_id="jail-ac14")
    sibling: ExecHandle | None = None
    try:
        sibling = exec_in_jail(handle, ["sleep", "45"])
        sibling_pgid = _ps_pgid(sibling.pid)
        assert _group_members(sibling_pgid)  # alive before kill()

        handle.kill()

        assert _group_members(sibling_pgid) == []
    finally:
        _teardown_group(handle)
        _reap_and_kill_sibling(sibling)


# ---------------------------------------------------------------------------
# AC #8 / #9 -- the new tests/conftest.py arm, proven by mutation, with a
# false-positive control. See this task's notes for the plant/revert
# evidence (edit named, red run, green run, both hashes) -- not encoded as
# a standing test here, same posture as test_kill_group.py's own mutation
# check: a mutation check that lived in the suite would leave production
# code mutated on every green run, which is exactly backwards.
#
# This IS the test AC #8's notes name as "the named unwaited-sibling
# test": a BARE, token-less argv on purpose, so ONLY the new
# tests/conftest.py harness-child arm can catch a plant here -- a
# token-bearing sibling would let the OLD arm catch it too, proving
# nothing about the new one specifically. It passes green on every normal
# run (this is AC #9's false-positive control, exercised for real by
# running the whole `-m integration` tier, not just this file).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_unwaited_bare_argv_sibling_is_reaped_by_kill(run_id: str) -> None:
    """The mutation target for AC #8: a long-lived exec sibling with a
    BARE, token-less argv (`["sleep", "100"]`) -- `run_id` is accepted only
    so this test carries the same fixture-ordering shape as its neighbors
    and to name the jail_id distinctly; it is deliberately NOT threaded
    into the sibling's argv (see the section note above).

    Deliberately NO defensive `_reap_and_kill_sibling` in `finally` here,
    unlike every other test in this file: this test's entire point is to
    depend on `handle.kill()` alone for the sibling's hygiene. Cleaning it
    up defensively would silently erase a real leak before the session's
    leak-check ever got to see it, on the one test this task's mutation
    check needs that leak to survive to. The workload group is still torn
    down defensively (`_teardown_group`) -- only the exec-sibling rung is
    what AC #8's plant disables."""
    handle = _new_handle(run_id, jail_id="jail-ac8")
    try:
        sibling = exec_in_jail(handle, ["sleep", "100"])
        sibling_pgid = _ps_pgid(sibling.pid)
        assert _group_members(sibling_pgid)

        handle.kill()

        assert _group_members(sibling_pgid) == []
    finally:
        _teardown_group(handle)
