"""Integration tests for `brig.mech.rlimits`: MILESTONES.md M3 EC2 -- the
real `SIGXCPU` trip through the compiled trampoline invocation, the control
that tells "died" apart from "never started," and the event-stream record
the trip produces.

**`run` does not yet consume `Step.events`.** Verified: `grep -rln
classify_exit brig/` finds only `brig/core/events.py` (the `EventKind`
member) and `brig/mech/__init__.py`/`brig/mech/rlimits.py` (the contract and
this mechanism) -- nothing under `brig/run/` calls `classify_exit` or
`known_at_compile`. So the event-stream tests below play `run`'s part by
hand: append `SPAWN` via `EventLog` exactly as `SubprocessLauncher.launch`
does (`brig/run/launcher.py`), spawn the compiled argv, wait for the REAL
process, build `ExitOutcome` from its OBSERVED returncode, hand it to
`step.events.classify_exit`, and append whatever payload comes back the same
way `run` will once that wiring lands. This is a stand-in for that wiring,
not a claim that it exists.

Every subprocess here is `wait()`-ed on (or killed-and-waited) synchronously
within its own test -- same posture as `tests/integration/test_trampoline.py`
-- so no `workload_argv` run-id token is needed for the conftest sweep's
pgid/token arms. A distinctive marker is embedded directly in the spin-loop
source (visible in `/bin/ps` while the process is alive, since it is passed
as the `-c` script argument) so AC #11's residue check can name what it is
looking for independent of the conftest sweep's own automatic verdict.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from brig.core import EventKind, Limits, Spec
from brig.mech import CompileCtx, ExitOutcome
from brig.mech.rlimits import rlimits
from brig.run.events import stamp

_CTX = CompileCtx(jail_dir="/unused/rlimits-integration-test", platform=sys.platform)

#: Embedded in the spin-loop source so it shows up in `/bin/ps`'s command
#: column while the process is alive -- AC #11's residue-check subject.
_SPIN_LOOP_MARKER = "RLIMITS_SPIN_MARKER"
_SPIN_LOOP = f"# {_SPIN_LOOP_MARKER}\nx = 0\nwhile True:\n    x += 1\n"

_PS_ARGV = ["/bin/ps", "-Ao", "pid=,command="]

#: task-042 (doc-013 §3.3/§3.6): the trampoline's `os.execvp` has not
#: necessarily completed by the time `Popen` returns control to the caller.
#: Between the fork and the exec landing, darwin's `/bin/ps` reports the
#: parenthesized accounting name (e.g. `(python3.14)`) instead of the
#: workload's real argv -- a single sample races that window. The workload
#: is a spin loop and is long-lived by construction (doc-013 measured "no ps
#: row at all" in 0 of 60 samples), so the deadline below exists to fail
#: loudly on a genuinely dead workload, not to paper over a hang.
_POLL_DEADLINE_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.02


def _command_for_pid(pid: int) -> str | None:
    """The command line of the process with this exact pid, or `None` if no
    such process is currently visible to `/bin/ps`. Absolute path, no bare
    `ps` (WORKFLOW.md decision-026 rule 1: a shell alias cannot redefine
    `/bin/ps`).

    PID-SCOPED ON PURPOSE, not a substring search over the whole process
    table: a bare `marker in ps_output` check is satisfied by ANY row
    carrying the marker string, including this very `/bin/ps` invocation's
    own argv, or a `grep`'s -- exactly the false positive this file's own
    residue-check evidence hit twice while gathering AC #11's evidence.
    Scoping to `proc.pid` makes a match possible only from the workload
    process itself. The trampoline `exec`s rather than forks
    (`tests/integration/test_trampoline.py`'s own pid-identity test), so
    `proc.pid` names the actual spin-loop process throughout its life."""
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
    `/bin/ps` sample that raced it (task-042, doc-013 §3.3/§3.6).

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


@pytest.mark.integration
def test_ec2_positive_spin_loop_dies_with_sigxcpu_signal_24() -> None:
    """MILESTONES.md M3 EC2, the claim half: a spin loop launched through
    the compiled trampoline invocation with `cpu_seconds=1` terminates on
    `SIGXCPU`. Asserts the EXACT termination signal number (24), not a
    substring of any message, and records the observed wall time (AC #2)."""
    assert int(signal.SIGXCPU) == 24  # platform pin, asserted rather than assumed
    step = rlimits.compile(Spec(limits=Limits(cpu_seconds=1)), _CTX)
    argv = step.wrap((sys.executable, "-c", _SPIN_LOOP))

    start = time.monotonic()
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    returncode = proc.wait(timeout=10)
    wall_time = time.monotonic() - start

    assert returncode == -24, f"expected termination by SIGXCPU (-24), got returncode={returncode}"
    assert wall_time < 10.0


@pytest.mark.integration
def test_ec2_control_generous_limit_still_running_then_torn_down() -> None:
    """AC #3, the control the integration rules require beside every
    denial: the SAME spin-loop workload under `cpu_seconds=60` is still
    running when checked, then is torn down. Without this, "died" cannot be
    told apart from "never started" in the positive test above."""
    step = rlimits.compile(Spec(limits=Limits(cpu_seconds=60)), _CTX)
    argv = step.wrap((sys.executable, "-c", _SPIN_LOOP))

    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # The real "alive" check (and AC #11's evidence): THIS pid's own
        # `/bin/ps` row exists and carries the marker -- not merely "the
        # marker appears somewhere in the process table," which pytest's
        # own command line or the `/bin/ps` call itself could also
        # satisfy (a discriminating control: a workload that never
        # started, or already exited, has no row for `proc.pid` at all).
        # SYNCHRONIZED, not a single sample (task-042): the trampoline's
        # `os.execvp` may not have completed the instant `Popen` returns,
        # so this polls until the marker appears rather than racing that
        # window -- see `_poll_command_for_pid`.
        alive_command = _poll_command_for_pid(proc.pid, _SPIN_LOOP_MARKER)
        assert _SPIN_LOOP_MARKER in alive_command
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=2)
    finally:
        proc.kill()
        proc.wait(timeout=10)

    # "Gone" half: no /bin/ps row for this pid survives teardown. Genuinely
    # synchronized already, not raced (task-042 notes): `proc.wait()` above
    # blocks until the kernel has reaped the (SIGKILL-ed) child, and once
    # `waitpid` returns, the process table entry is gone -- there is no
    # window analogous to the exec race the "alive" half polls for, so no
    # poll is added here.
    assert _command_for_pid(proc.pid) is None


@pytest.mark.integration
def test_trip_stamps_into_a_limit_trip_record(tmp_path: Path) -> None:
    """AC #5: after the workload dies, `classify_exit` makes a
    `LIMIT_TRIP` payload of the ending, and `run`'s stamper turns it into
    an `Event` carrying this jail's id, naming the limit field and the
    signal. The payload is derived from the workload's OWN observed
    returncode, never hand-built. (decision-152: there is no
    `events.jsonl` to read this back out of any more -- `run` stamps and
    hands the record to the embedder.)"""
    del tmp_path
    step = rlimits.compile(Spec(limits=Limits(cpu_seconds=1)), _CTX)
    argv = step.wrap((sys.executable, "-c", _SPIN_LOOP))
    jail_id = "rlimits-trip-test"

    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    returncode = proc.wait(timeout=10)

    assert step.events is not None
    payload = step.events.classify_exit(ExitOutcome(returncode=returncode))
    assert payload is not None
    record = stamp(payload, jail_id)

    assert record.kind is EventKind.LIMIT_TRIP
    assert record.jail_id == jail_id
    assert record.data["field"] == "cpu"
    assert record.data["signal"] == 24


@pytest.mark.integration
def test_control_clean_exit_produces_no_limit_trip_record(tmp_path: Path) -> None:
    """Control for the trip test above: a workload that exits cleanly under
    a generous limit produces no record at all -- `classify_exit`
    recognizes nothing and returns `None`. Without this, the trip test
    could pass merely because SOMETHING was produced, not because the
    SIGXCPU trip specifically was."""
    del tmp_path
    step = rlimits.compile(Spec(limits=Limits(cpu_seconds=60)), _CTX)
    argv = step.wrap(("/bin/echo", "hi"))

    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    returncode = proc.wait(timeout=10)

    assert returncode == 0
    assert step.events is not None
    assert step.events.classify_exit(ExitOutcome(returncode=returncode)) is None
