"""MILESTONES.md M3 EC3 / task-038: the trampoline composes.

    3. The trampoline composes: the same behavior under the subprocess launcher
       with an extra no-op wrapper stacked outside it (composition smoke test).

SPEC.md §8, the claim EC3 is an early payment on:

    Because mechanisms are argv wrappers and rlimits ride a trampoline rather
    than `preexec_fn`, tmux composes with any stack -- the launcher/enforcement
    split exists precisely so "watchable" and "jailed" are independent axes.

**The wrapper is a test-local argv transformer, not a `Mechanism` (decision-063,
operator round 7, A4).** SPEC.md §7 step 3 refuses unknown mechanism pairs, so a
no-op `Mechanism` would either be refused by the compatibility matrix or force a
fake row into shipped compatibility data. Instead this file builds a plain
two-line shell script that `exec`s the rest of its argv in place (never forks)
and applies it as a PREFIX to the REAL `Stack([rlimits])`'s already-composed
argv, via `dataclasses.replace(jail, wrap=...)` -- swapping only the
`CompiledJail.wrap` callable a test holds locally, after the real `Stack`
compiled it and before the real `SubprocessLauncher` ever sees it. Nothing
under `brig/` is touched by this file (AC #6): no `Mechanism` is added, the
compatibility matrix gains no row, and `Stack`/`SubprocessLauncher` run
completely unmodified, exercising the identical code path
`tests/integration/test_launcher.py` and `tests/integration/test_rlimits.py`
already exercise.

**Why this uses the REAL `Stack` and the REAL `SubprocessLauncher`, not a
hand-rolled `subprocess.Popen` stand-in.** `tests/integration/test_rlimits.py`'s
own docstring is explicit that its direct-`Popen` shape is "a stand-in for
[the launcher] wiring, not a claim that it exists" -- true there because that
file also needs `Step.events`, which `run` does not yet consume. This file
needs no event wiring, so nothing stands between it and the real
`Stack.compile` / `SubprocessLauncher.launch` path EC3's own wording ("the
same behavior under the subprocess launcher") names directly.

**Why no subprocess here needs `tests.conftest.workload_argv`'s run-id
token.** Every subprocess this file starts is reaped synchronously within its
own test -- the workload's reap belongs to the launcher's exit-waiter, and
`_teardown` blocks on `handle.wait()` until that reap has landed (task-073) --
exactly the posture
`tests/integration/test_trampoline.py` and `tests/integration/test_rlimits.py`
already establish and document: by the time a test returns, nothing it
started is still alive for the session-teardown sweep to find. That includes
task-035's fourth (grandchild) arm: this file's own process trees never leak,
so on a clean run no arm -- including the grandchild one -- has anything to
catch. The grandchild arm's relevance to THIS milestone is structural, not
demonstrated by a live catch here: M3 is the first place a workload can sit
one hop below whatever the launcher itself spawns (a trampoline that execs,
or -- as here -- a wrapper's exec chain stacked in front of it), which is
exactly the shape task-035 added that arm to see if it ever escaped teardown.

`sun_path` is 104 bytes on darwin: every scratch path here is a short
`/tmp/bg<pid>-t038-<n>` root, never `tmp_path` (CLAUDE.md's trap list;
`tests/integration/test_launcher.py`'s own `_new_jail_dir` convention).
"""

from __future__ import annotations

import dataclasses
import itertools
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from brig.core import Limits, Spec
from brig.mech import CompileCtx
from brig.mech.rlimits import rlimits
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail, Stack
from tests.conftest import teardown_group

_CTX = CompileCtx(jail_dir="/unused/trampoline-composition-test", platform=sys.platform)

#: Embedded as the spin loop's own first source line so it shows up in
#: `/bin/ps`'s command column while the process is alive -- same convention
#: as `tests/integration/test_rlimits.py`'s `_SPIN_LOOP_MARKER`, this file's
#: own AC #7 residue-check subject.
_SPIN_LOOP_MARKER = "T038_SPIN_MARKER"
_SPIN_LOOP = f"# {_SPIN_LOOP_MARKER}\nx = 0\nwhile True:\n    x += 1\n"

#: Set by the transparent wrapper (AC #5's marker) and read back by the
#: pid-identity workload, proving the wrapper actually ran rather than the
#: launcher having silently ignored the prefix.
_WRAPPER_ENV_MARKER = "BRIG_T038_WRAPPER_RAN"

_PS_ARGV = ["/bin/ps", "-Ao", "pid=,command="]

#: task-042 (doc-013 §3.5/§3.6): this file's control shares
#: `test_rlimits.py`'s single-sample race against `os.execvp` -- structurally
#: identical, and traversing TWO execs (wrapper -> trampoline -> workload)
#: rather than one, so its window is if anything wider. Same deadline
#: rationale: the spin-loop workload is long-lived by construction, so this
#: exists to fail loudly on a genuinely dead workload, not to paper over a
#: hang.
_POLL_DEADLINE_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.02

_jail_counter = itertools.count()


def _new_scratch_dir() -> str:
    """A short `/tmp/bg<pid>-t038-<n>` root -- never `tmp_path` (sun_path is
    104 bytes on darwin; CLAUDE.md's trap list). Used for both jail
    directories and staged wrapper scripts; each test gets its own so
    parallel runs (and this file's own several tests) never collide."""
    path = f"/tmp/bg{os.getpid()}-t038-{next(_jail_counter)}"
    os.makedirs(path, exist_ok=True)
    return path


def _stage_transparent_wrapper(scratch_dir: str) -> tuple[str, ...]:
    """The real no-op wrapper (decision-063): sets the marker env var, then
    `exec`s the rest of its argv IN PLACE. `export` is a shell builtin (no
    process of its own); `exec "$@"` replaces the shell's own process image
    -- no fork anywhere in this script, ever. Returns the one-element argv
    PREFIX that invokes it."""
    script_path = Path(scratch_dir) / "noop_wrapper.sh"
    script_path.write_text(f'#!/bin/sh\nexport {_WRAPPER_ENV_MARKER}=1\nexec "$@"\n')
    script_path.chmod(0o700)
    return (str(script_path),)


def _stage_forking_wrapper(scratch_dir: str) -> tuple[str, ...]:
    """MUTATION-CHECK ONLY (AC #3): a wrapper that forks-and-waits instead
    of exec-ing. Never wired into a passing test -- swapped in temporarily,
    by hand, to prove the pid-identity assertion is falsifiable, then
    reverted. Still sets the marker (so the mutation isolates exactly the
    fork-vs-exec property, not the marker property)."""
    script_path = Path(scratch_dir) / "forking_wrapper.sh"
    script_path.write_text(f'#!/bin/sh\nexport {_WRAPPER_ENV_MARKER}=1\n"$@" &\nwait\n')
    script_path.chmod(0o700)
    return (str(script_path),)


#: Swapped to `_stage_forking_wrapper` ONLY for the AC #3 mutation check,
#: by hand, then reverted -- see this file's Evidence section in the task
#: notes for the scratch-copy-plus-sha256 record of that round trip.
_WRAPPER_STAGER = _stage_transparent_wrapper


def _outer_wrap(jail: CompiledJail, wrapper_prefix: tuple[str, ...]) -> CompiledJail:
    """decision-063: apply `wrapper_prefix` to the stack's ALREADY-composed
    argv, outside the stack -- a test-local transformer, not a `Mechanism`
    and not a matrix row. `dataclasses.replace` swaps only `wrap`; every
    other `CompiledJail` field (report, env, requires, mechanism_names, ...)
    is the real `Stack.compile` output, untouched, so the launcher is
    handed an otherwise-identical jail."""
    inner_wrap = jail.wrap
    return dataclasses.replace(jail, wrap=lambda argv: (*wrapper_prefix, *inner_wrap(argv)))


def _command_for_pid(pid: int) -> str | None:
    """The command line of the process with this exact pid, or `None` if no
    such process is currently visible -- PID-scoped, not a substring search
    over the whole table (same discriminating shape, and the same false
    positive it avoids, as `test_rlimits.py`'s helper of the same name)."""
    proc = subprocess.run(_PS_ARGV, capture_output=True, text=True, check=True)
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_field, _, command = stripped.partition(" ")
        if int(pid_field) == pid:
            return command.strip()
    return None


def _poll_command_for_pid(pid: int, marker: str, deadline: float = _POLL_DEADLINE_SECONDS) -> str:
    """Poll `_command_for_pid(pid)` until its command string carries `marker`,
    or `deadline` seconds elapse -- synchronization for the `os.execvp` race
    documented at `_POLL_DEADLINE_SECONDS` above, replacing the single
    `/bin/ps` sample that raced it (task-042, doc-013 §3.5/§3.6). Same helper
    as `test_rlimits.py`'s function of the same name.

    Returns the marker-carrying command string on success. On expiry, FAILS
    THE TEST (not merely raises) with a message naming the pid, the elapsed
    wall time, and the LAST OBSERVED command string -- task-042 AC #3."""
    start = time.monotonic()
    last_observed: str | None = None
    while True:
        last_observed = _command_for_pid(pid)
        if last_observed is not None and marker in last_observed:
            return last_observed
        elapsed = time.monotonic() - start
        if elapsed > deadline:
            pytest.fail(
                f"pid {pid}: marker {marker!r} did not appear in /bin/ps within "
                f"{deadline}s (elapsed {elapsed:.3f}s); last observed command: "
                f"{last_observed!r}"
            )
        time.sleep(_POLL_INTERVAL_SECONDS)


def _teardown(handle: Handle, scratch_dirs: list[str]) -> None:
    """Hand-rolled group-kill, same posture as `test_launcher.py`'s
    `_teardown_group`: the KILL is not the code under test (`Handle.kill()`),
    so a teardown bug here cannot hide behind that helper. The reap itself
    belongs to the launcher's exit-waiter (task-073); `handle.wait()` blocks
    until that waiter has reaped and recorded the `EXIT` -- which is what
    makes this call return only once the process table entry is gone. Also
    removes every scratch directory this test staged, so nothing under
    `/tmp` outlives the test."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)
    for scratch_dir in scratch_dirs:
        shutil.rmtree(scratch_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC #1 -- the unwrapped baseline.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_baseline_unwrapped_spin_loop_dies_with_sigxcpu() -> None:
    """AC #1: the reference behaviour EC3's "the same behavior" points at --
    a `cpu_seconds=1` spin loop, launched through the REAL `Stack([rlimits])`
    under the REAL `SubprocessLauncher`, with NO wrapper at all, dies on
    `SIGXCPU` (signal 24)."""
    assert int(signal.SIGXCPU) == 24  # platform pin, asserted not assumed
    scratch_dir = _new_scratch_dir()
    jail = Stack([rlimits]).compile(Spec(limits=Limits(cpu_seconds=1)), ctx=_CTX)
    launcher = SubprocessLauncher()

    start = time.monotonic()
    handle = launcher.launch(
        jail,
        argv=[sys.executable, "-c", _SPIN_LOOP],
        cwd=scratch_dir,
        io=IoPolicy(),
        jail_id="t038-baseline",
        jail_dir=scratch_dir,
    )
    try:
        status = handle.wait(timeout=10.0)
        wall_time = time.monotonic() - start
        assert status == -signal.SIGXCPU, (
            f"expected death by SIGXCPU ({-signal.SIGXCPU}), got {status}"
        )
        assert wall_time < 10.0
    finally:
        _teardown(handle, [scratch_dir])


# ---------------------------------------------------------------------------
# AC #2 -- the wrapped case: same workload, same stack, wrapper outside it.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_wrapped_spin_loop_still_dies_with_sigxcpu() -> None:
    """AC #2: the SAME workload and the SAME stack as the baseline above,
    with the no-op wrapper prepended to the composed argv, terminates on
    `SIGXCPU` within the same tolerance -- EC3's composition smoke test
    itself."""
    scratch_dir = _new_scratch_dir()
    jail = Stack([rlimits]).compile(Spec(limits=Limits(cpu_seconds=1)), ctx=_CTX)
    wrapper_prefix = _stage_transparent_wrapper(scratch_dir)
    wrapped_jail = _outer_wrap(jail, wrapper_prefix)
    launcher = SubprocessLauncher()

    workload = (sys.executable, "-c", _SPIN_LOOP)
    full_composed_argv = wrapped_jail.wrap(workload)

    start = time.monotonic()
    handle = launcher.launch(
        wrapped_jail,
        argv=list(workload),
        cwd=scratch_dir,
        io=IoPolicy(),
        jail_id="t038-wrapped",
        jail_dir=scratch_dir,
    )
    try:
        assert handle.argv == full_composed_argv
        status = handle.wait(timeout=10.0)
        wall_time = time.monotonic() - start
        assert status == -signal.SIGXCPU, (
            f"expected death by SIGXCPU ({-signal.SIGXCPU}), got {status}"
        )
        assert wall_time < 10.0
    finally:
        _teardown(handle, [scratch_dir])


# ---------------------------------------------------------------------------
# AC #3 / AC #5 -- the wrapper is transparent AND it really ran.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_wrapper_is_transparent_and_actually_ran() -> None:
    """AC #3: the wrapper is transparent, proved not assumed -- the workload
    observes itself running as a DIRECT CHILD of the pid the launcher
    started, one generation and no more (`os.execvp`, all the way down,
    replaces the process image at every hop: wrapper -> trampoline ->
    workload never fork). AC #5, the control against a vacuous pass: the
    wrapper's own marker env var, set before its `exec`, is still present in
    the workload's environment -- proving the wrapper really ran rather than
    the launcher having silently dropped an unrecognized prefix.

    **One generation, not zero** (decision-156, 2026-09-08). This used to
    assert exact pid EQUALITY, because the launcher spawned the compiled
    argv itself. It now spawns that argv under the exit wrapper
    (`brig/run/_exit_status.py`), which is the one process in the chain that
    deliberately forks rather than execs -- something has to outlive the
    workload by the microseconds it takes to write `<jail_dir>/exit`. So the
    invariant moves down exactly one generation and loses none of its
    discrimination: everything from the mechanism wrapper inward must still
    exec, and a `ppid` other than `handle.pid` says one of them forked.

    Mutation pairing (AC #3, deterministic): swap `_WRAPPER_STAGER` for
    `_stage_forking_wrapper` and re-run this exact test -- the parentage
    comparison reddens, because a forking wrapper leaves an intermediate
    process alive and makes the workload its GRANDchild.
    Evidence (scratch-copy-plus-sha256 round trip) is in the task notes.
    """
    scratch_dir = _new_scratch_dir()
    # A generous limit: this workload exits almost immediately, so what it
    # is bounded by is not this test's subject (contrast the SIGXCPU tests
    # above, which need a tight one).
    jail = Stack([rlimits]).compile(Spec(limits=Limits(cpu_seconds=60)), ctx=_CTX)
    wrapper_prefix = _WRAPPER_STAGER(scratch_dir)
    wrapped_jail = _outer_wrap(jail, wrapper_prefix)
    launcher = SubprocessLauncher()

    marker_workload_src = (
        "import os, sys\n"
        f"marker = os.environ.get({_WRAPPER_ENV_MARKER!r}, '')\n"
        "sys.stdout.write(str(os.getppid()) + ' ' + marker)\n"
    )
    workload = (sys.executable, "-c", marker_workload_src)
    handle = launcher.launch(
        wrapped_jail,
        argv=list(workload),
        cwd=scratch_dir,
        io=IoPolicy(),
        jail_id="t038-transparency",
        jail_dir=scratch_dir,
    )
    try:
        status = handle.wait(timeout=10.0)
        assert status == 0, f"workload did not exit cleanly, status={status}"
        stdout_text = Path(handle.stdout_path).read_text()
        ppid_field, _, marker_field = stdout_text.partition(" ")

        # AC #3: transparency, exact parentage -- the workload is the exit
        # wrapper's own child, with nothing in between.
        assert int(ppid_field) == handle.pid, (
            f"workload observed its parent as pid {ppid_field}, but the "
            f"launcher started pid {handle.pid} -- an intermediate process "
            "survived the wrapper, which means it forked instead of exec-ing"
        )
        # AC #5: the wrapper really ran (a no-op that silently did nothing
        # would leave this field empty, making this whole test a re-run of
        # the baseline).
        assert marker_field == "1", (
            f"expected the wrapper's marker env var to read '1', got {marker_field!r} -- "
            "the wrapper did not actually run"
        )
    finally:
        _teardown(handle, [scratch_dir])


# ---------------------------------------------------------------------------
# AC #4 -- control against a vacuous pass: a generous limit stays alive.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_control_wrapped_generous_limit_stays_alive_then_torn_down() -> None:
    """AC #4: the SAME wrapped invocation as AC #2, with `cpu_seconds=60`
    instead of `1`, is still alive when checked, then is torn down. Without
    this, "the wrapped run died on SIGXCPU" cannot be told apart from "the
    wrapper broke the argv and something died for another reason" -- the
    same discriminating shape `test_rlimits.py`'s own generous-limit control
    uses."""
    scratch_dir = _new_scratch_dir()
    jail = Stack([rlimits]).compile(Spec(limits=Limits(cpu_seconds=60)), ctx=_CTX)
    wrapper_prefix = _stage_transparent_wrapper(scratch_dir)
    wrapped_jail = _outer_wrap(jail, wrapper_prefix)
    launcher = SubprocessLauncher()

    handle = launcher.launch(
        wrapped_jail,
        argv=[sys.executable, "-c", _SPIN_LOOP],
        cwd=scratch_dir,
        io=IoPolicy(),
        jail_id="t038-control",
        jail_dir=scratch_dir,
    )
    try:
        # SYNCHRONIZED, not a single sample (task-042): this call traverses
        # TWO execs (wrapper -> trampoline -> workload), so the `os.execvp`
        # race `_poll_command_for_pid` guards against (see its docstring) is
        # if anything wider here than in `test_rlimits.py`'s control.
        alive_command = _poll_command_for_pid(handle.pid, _SPIN_LOOP_MARKER)
        assert _SPIN_LOOP_MARKER in alive_command
        assert handle.alive() is True
    finally:
        _teardown(handle, [scratch_dir])

    # "Gone" half: no /bin/ps row for this pid survives teardown, and
    # Handle.alive() agrees. Genuinely synchronized already, not raced
    # (task-042 notes, task-073 conversion): `_teardown` above blocks on
    # `handle.wait()` (after `os.killpg`) until the launcher's exit-waiter
    # has reaped the workload and recorded its `EXIT` -- by which point the
    # process table entry is gone. There is no window analogous to the exec
    # race the "alive" half polls for, so no poll is added here.
    assert _command_for_pid(handle.pid) is None
    assert handle.alive() is False
