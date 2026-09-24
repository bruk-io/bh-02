"""`python -m brig.mech.trampoline` against a real OS process: MILESTONES.md
M3's rlimits exit criterion -- a spin loop under `cpu_seconds=1` dies with
`SIGXCPU` within tolerance -- plus the control that the trampoline is not
simply killing everything, and the claim that it EXECS rather than forks
(no intermediate process survives the launch).

Every subprocess this file starts is `wait()`-ed on synchronously within its
own test (`communicate`/`wait` with a timeout), so nothing needs a
`workload_argv` run-id token: by the time a test returns, the trampoline
process itself has already been reaped, and arm (c) of the leak sweep
(`ppid == harness_pid`) never has anything alive to catch at teardown.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time

import pytest

_TRAMPOLINE_ARGV = [sys.executable, "-m", "brig.mech.trampoline"]

# A tight busy loop: no sleeps, no I/O, so it burns CPU time as fast as the
# interpreter can -- the workload `--cpu 1` is meant to trip inside the
# test's own timeout.
_SPIN_LOOP = "x = 0\nwhile True:\n    x += 1\n"


@pytest.mark.integration
def test_cpu_limited_spin_loop_dies_with_sigxcpu_within_tolerance() -> None:
    """The claim half of MILESTONES.md M3 EC2: `cpu_seconds=1` trips SIGXCPU."""
    start = time.monotonic()
    proc = subprocess.Popen(
        [*_TRAMPOLINE_ARGV, "--cpu", "1", "--", sys.executable, "-c", _SPIN_LOOP],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    returncode = proc.wait(timeout=10)
    wall_time = time.monotonic() - start

    # A process killed by a signal reports Python's own encoding: a negative
    # returncode whose absolute value is the signal number.
    assert returncode == -signal.SIGXCPU, (
        f"expected termination by SIGXCPU ({signal.SIGXCPU}), got returncode={returncode}"
    )
    # RLIMIT_CPU counts CPU time, not wall time, but a tight busy loop with a
    # single thread spends essentially all its wall time on CPU, so the trip
    # is expected well inside the test's own 10s safety timeout. A generous
    # tolerance (the limit is 1s of CPU time) rather than a tight one, since
    # CI/dev-machine scheduling noise is not this test's subject.
    assert wall_time < 10.0


@pytest.mark.integration
def test_control_generous_cpu_limit_lets_a_quick_command_finish() -> None:
    """The control MILESTONES.md M3 asks for: the trampoline is not simply
    killing everything it wraps -- a workload that finishes well inside a
    generous limit exits normally and its stdout is exactly what it printed."""
    proc = subprocess.run(
        [*_TRAMPOLINE_ARGV, "--cpu", "60", "--", "/bin/echo", "hi"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout == "hi\n"


@pytest.mark.integration
def test_trampoline_execs_the_workload_rather_than_forking() -> None:
    """`os.execvp` replaces the trampoline's own process image: the pid the
    workload observes itself running as must equal the pid the trampoline
    process was started as. No intermediate process survives the launch --
    a fork+exec (or fork+run) shape would give the workload a NEW, larger
    pid, as the child of the pid captured here."""
    proc = subprocess.Popen(
        [
            *_TRAMPOLINE_ARGV,
            "--cpu",
            "60",
            "--",
            sys.executable,
            "-c",
            "import os, sys; sys.stdout.write(str(os.getpid()))",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    trampoline_pid = proc.pid
    stdout, _ = proc.communicate(timeout=10)
    assert proc.returncode == 0
    workload_pid = int(stdout)
    assert workload_pid == trampoline_pid
