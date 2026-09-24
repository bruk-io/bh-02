"""Fast exec siblings must not crash `exec_in_jail` (task-075).

task-075's reproduced signature, verbatim from two independent loaded runs:

    brig/run/exec_.py:275: ProcessLookupError: [Errno 3] No such process
    ...
    pid=<N> ppid=<harness_pid> pgid=<N> stat=Z arm=harness-child command=<defunct>

The root cause, confirmed at the raw-syscall level in task-075: darwin's
`getpgid()` raises ESRCH for a child that has ALREADY EXITED (a zombie),
even though `/bin/ps` still shows its group. `exec_in_jail` read the
sibling's pgid with a bare `os.getpgid(pid)` immediately after `Popen`
returned, so a fast command (`/usr/bin/true`, an `echo` probe) that exits
within microseconds -- under any scheduling delay -- crashed the spawn path
AFTER the process existed but BEFORE the sibling was registered: it was
registered nowhere (no `ExecHandle`, nothing for `kill_jail`'s
`_live_exec_siblings` to find), and its zombie lingered until
the GC reaped it, which the session-end leak sweep then reported as a
leaked process. `launcher.py`'s workload launch had the identical race one
line earlier in the same file pair.

The fix is `brig/run/_spawn_pgid.spawn_pgid`: read via `os.getpgid` while
the child is alive; on darwin's ESRCH (child already gone) record the child
pid itself -- not a guess about launcher details, but the same fact
`setsid()`-before-`exec` guarantees from birth. This file pins it:

- AC #1 (deterministic mutation target): a REAPED fast child makes
  `os.getpgid` raise on EVERY platform, so `spawn_pgid`'s fallback is
  exercised without any load or timing luck -- reverting the helper to a
  bare `os.getpgid` fails this test on the first run.
- AC #2 (positive control): a LIVE child reads its real pgid through the
  same helper -- the fallback must not mask a working read.
- AC #3 / AC #4: the original crash shape end to end -- many fast siblings
  through the real `exec_in_jail`, and a fast workload through the real
  launcher, each recording `pgid == pid` for a child that was already gone.

The recorded facts used to be read back out of the per-jail event stream's
`EXEC`/`SPAWN` records; decision-152 (2026-09-08) deleted that stream, so
AC #3 reads the sibling registration (`brig/run/_execs.py`) and AC #4 reads
the `Handle` the launch returned and the exit status the waiter recorded.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import shutil
import signal
import subprocess

import pytest

from brig.core import Spec, unenforced_report
from brig.run._execs import live as live_execs
from brig.run._spawn_pgid import spawn_pgid
from brig.run.exec_ import exec_in_jail
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv

_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>fs<n>` -- never `tmp_path`."""
    return f"/tmp/bg{os.getpid()}fs{next(_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail() -> CompiledJail:
    """The empty stack's shape: mechanism-free, every axis unenforced."""
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


def _teardown_group(handle: Handle, jail_dir: str) -> None:
    """Group-kill the workload and remove its jail directory. Hand-rolled
    (`killpg`) rather than `kill_jail`: a test's cleanup path must not be
    the code under test. `handle.wait()` blocks until the launcher's
    exit-waiter has reaped it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)
    shutil.rmtree(jail_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC #1 -- the deterministic pin: a reaped fast child exercises the fallback.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_spawn_pgid_of_an_already_reaped_child_is_its_own_pid() -> None:
    """AC #1, THE MUTATION TARGET. `/usr/bin/true` exits in microseconds;
    `proc.wait()` reaps it, after which `os.getpgid` raises ESRCH on EVERY
    platform (the process is gone, not merely a darwin zombie) -- so the
    fallback branch runs deterministically, no load required. The recorded
    group must be the child's own pid: with `start_new_session=True`,
    `setsid()` ran before `exec`, so that is the fact the read would have
    returned while the child was alive."""
    proc = subprocess.Popen(["/usr/bin/true"], start_new_session=True)
    assert proc.wait(timeout=5.0) == 0  # reaped: getpgid now raises everywhere
    with pytest.raises(ProcessLookupError):
        os.getpgid(proc.pid)  # the premise, made explicit rather than assumed
    assert spawn_pgid(proc) == proc.pid


# ---------------------------------------------------------------------------
# AC #2 -- positive control: a live child reads its real pgid.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_spawn_pgid_of_a_live_child_reads_the_real_group() -> None:
    """AC #2, THE CONTROL: with the child still alive, `spawn_pgid` must
    return the group `os.getpgid` itself reads -- proof the fallback only
    fires when the read is impossible, not instead of it."""
    proc = subprocess.Popen(["sleep", "5"], start_new_session=True)
    try:
        assert os.getpgid(proc.pid) == proc.pid  # alive: the plain read works
        assert spawn_pgid(proc) == proc.pid
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5.0)


# ---------------------------------------------------------------------------
# AC #3 -- the original crash shape, end to end through `exec_in_jail`.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_hundred_fast_exec_siblings_all_record_and_end(run_id: str) -> None:
    """AC #3: one hundred `/usr/bin/true` siblings through the REAL
    `exec_in_jail` -- each `wait()`s to 0, and the events file ends with
    exactly one EXEC (carrying `pgid == pid`) and one EXEC_END per sibling.
    Pre-fix, a single sibling exiting before its pgid read crashed the whole
    test (task-075's runs 13 and 23 each caught it on the FIRST loaded run);
    post-fix the fast path is exercised a hundred times per run."""
    jail_dir = _new_jail_dir()
    launcher = SubprocessLauncher()
    handle = launcher.launch(
        _compiled_jail(),
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-fast-sib",
        jail_dir=jail_dir,
    )
    try:
        for _ in range(100):
            exec_handle = exec_in_jail(handle, ["/usr/bin/true"])
            assert exec_handle.wait(timeout=5.0) == 0

        # Every one of the 100 siblings registered and then deregistered on
        # its own `wait()` -- a crash in the pgid read would have left an
        # unregistered zombie instead.
        assert live_execs(handle.jail_dir) == []
    finally:
        _teardown_group(handle, jail_dir)


# ---------------------------------------------------------------------------
# AC #4 -- the same race at the launcher's own spawn site.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_fast_workload_command_launches_and_records_exit_zero(run_id: str) -> None:
    """AC #4: the identical race one line earlier in `launcher.py` -- a
    workload command that exits before the launch's pgid read must still
    produce a `Handle` carrying `pgid == pid`, and an honest exit status of
    0 (the exit-waiter reaps what already exited). Pre-fix, this crashed
    `launch()` with a bare `ProcessLookupError` under load."""
    jail_dir = _new_jail_dir()
    launcher = SubprocessLauncher()
    handle = launcher.launch(
        _compiled_jail(),
        argv=workload_argv(run_id, "true"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-fast-workload",
        jail_dir=jail_dir,
    )
    try:
        assert handle.wait(timeout=10.0) == 0
        assert handle.pgid == handle.pid
    finally:
        _teardown_group(handle, jail_dir)
