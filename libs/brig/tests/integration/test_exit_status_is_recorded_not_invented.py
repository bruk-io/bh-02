"""The exit record: a workload's status is observed, or the read refuses.

The defect this pins, in the shape it shipped: `SubprocessLauncher` read
`proc.pid` and dropped the `Popen`, so `subprocess._cleanup()` -- which runs
inside every `Popen.__init__` anywhere in the process -- reaped the workload.
Five integration helpers hand-rolled `os.waitpid(pid)`, caught the resulting
`ChildProcessError`, and returned **0**.

Zero is the dangerous answer in both directions. A denial assertion
(`assert status != 0`) fails, reading as a jail that did not deny. An
allowed-write control (`assert status == 0`) *passes without observing
anything* -- the control that exists to prove a denial test is not vacuous
becomes vacuous itself.

**The record was an `EXIT` line in the per-jail JSONL stream until
decision-152 (2026-09-08) deleted that stream, and lived only in the
launching process's memory until decision-156 (2026-09-08) gave the durable
half back.** It is now two agreeing sources: the launching process's own
waiter thread (`brig/run/_waiters.py`), and `<jail_dir>/exit`, written once
by the tiny wrapper the launcher runs every workload under
(`brig/run/_exit_status.py`). The wrapper ends the same way its child did, so
the number the waiter thread observes and the number on disk are the same
number by construction -- which is what the SIGTERM test below discriminates,
because a `/bin/sh` wrapper reading `$?` could not tell `exit 143` from death
by `SIGTERM` and would have to guess.

What did NOT change is the half this file exists for: where nothing recorded
a status, the read is still a refusal and never a fabricated `0`. What
narrowed is when that happens -- no longer "you are not the launching
process", now only "no wrapper ever wrote", which the last test reaches by
deleting the file.
"""

from __future__ import annotations

import itertools
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest

from brig.core import Spec
from brig.run import ExitStatusUnobservable, Handle, IoPolicy, SubprocessLauncher, _waiters
from brig.run._exit_status import exit_path
from brig.stack import Stack

_jail_counter = itertools.count()

_HELPER = str(pathlib.Path(__file__).parent / "_rehydrate_and_kill_helper.py")


def _new_jail_dir() -> str:
    """Short scratch root -- `sun_path` is 104 bytes on darwin. The `xr` infix
    is this file's alone, so it cannot collide with a sibling's counter."""
    return f"/tmp/bg{os.getpid()}xr{next(_jail_counter)}"


def _launch(argv: list[str]) -> Handle:
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)
    return SubprocessLauncher().launch(
        Stack([]).compile(Spec()),
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"exitstatus-{os.path.basename(jail_dir)}",
        jail_dir=jail_dir,
    )


def _forget_the_in_process_record(handle: Handle) -> None:
    """Drop this process's own observation of how the workload ended.

    It WAITS for that observation first, and the wait is not caution: the
    wrapper writes `<jail_dir>/exit` and only then exits, so the file is
    readable a moment BEFORE the launching process's waiter thread reaps and
    records. `wait()` can therefore answer from the file while no record
    exists yet, and a `forget` fired at that instant would forget nothing --
    leaving the record to appear afterwards and quietly answer the very
    question the test is trying to ask off disk."""
    deadline = time.monotonic() + 10.0
    while _waiters.recorded_exit(handle.pid) is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _waiters.recorded_exit(handle.pid) is not None, (
        "the launching process never recorded this workload's exit, so there is "
        "nothing to drop and the control below would be vacuous"
    )
    _waiters.forget(handle.pid)


def _in_a_second_process(handle: Handle, tmp_path: pathlib.Path) -> dict[str, object]:
    """Rehydrate `handle` in a FRESH INTERPRETER and ask it how the workload
    ended. The serialized dict is that process's sole input: it never
    parented the workload, holds no waiter record, and shares no memory with
    this one, so any status it reports came off disk."""
    json_path = tmp_path / "handle.json"
    json_path.write_text(json.dumps(handle.to_dict()))
    done = subprocess.run(
        [sys.executable, _HELPER, str(json_path), "--wait"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    parsed: dict[str, object] = json.loads(done.stdout)
    return parsed


@pytest.mark.integration
def test_a_failing_status_survives_concurrent_popen_churn() -> None:
    """THE REGRESSION. Other spawns run `subprocess._cleanup()`, the exact
    interleaving that used to reap the workload out from under `waitpid`."""
    handle = _launch(["/bin/sh", "-c", "exit 3"])
    for _ in range(5):
        subprocess.run(["/bin/echo", "churn"], capture_output=True, check=True)
    assert handle.wait(timeout=20.0) == 3, "the real status must survive the churn"
    assert handle.wait(timeout=20.0) == 3, "and must be idempotent, read from the record"


@pytest.mark.integration
def test_a_clean_exit_is_observed_not_assumed() -> None:
    """THE CONTROL for the assertion above: the 0 case must be a real
    observation, reached by the same path, not a default."""
    handle = _launch(["/bin/sh", "-c", "exit 0"])
    assert handle.wait(timeout=20.0) == 0


@pytest.mark.integration
def test_a_rehydrated_handle_in_this_process_still_reads_the_record() -> None:
    """A handle that never parented the workload can still read how it
    ended."""
    handle = _launch(["/bin/sh", "-c", "exit 7"])
    assert handle.wait(timeout=20.0) == 7
    assert Handle.from_dict(handle.to_dict()).wait(timeout=20.0) == 7


@pytest.mark.integration
def test_death_by_signal_is_recorded_as_a_signal_not_as_128_plus_n(
    tmp_path: pathlib.Path,
) -> None:
    """The status is `Popen`'s own encoding -- `-15` for death by `SIGTERM`,
    never the shell's `143` -- and the FILE says the same thing this process
    does.

    This is the discriminating case for decision-156's choice of wrapper. A
    `/bin/sh` wrapper capturing `$?` sees `143` for both "the workload exited
    143" and "the workload was killed by SIGTERM", and would have to guess
    which; the wrapper is a Python program precisely so it does not. Asserted
    in BOTH places, because a file that disagreed with the launching process
    would be worse than no file at all."""
    handle = _launch(["/bin/sh", "-c", "kill -TERM $$"])
    assert handle.wait(timeout=20.0) == -signal.SIGTERM

    with open(exit_path(handle.jail_dir), encoding="utf-8") as recorded:
        assert recorded.read().strip() == str(-signal.SIGTERM)

    result = _in_a_second_process(handle, tmp_path)
    assert result["exit_status"] == -signal.SIGTERM, result


@pytest.mark.integration
def test_a_rehydrated_handle_in_a_second_process_reads_the_exit_file(
    tmp_path: pathlib.Path,
) -> None:
    """decision-156's whole point: the status crosses a process boundary
    again, without the event stream decision-152 deleted coming back.

    THE CONTROL that keeps it from being satisfied by shared memory: this
    process DROPS its own waiter record (`_waiters.forget`) before the second
    process runs. Nothing in this interpreter can answer the question any
    more, and the fresh one -- which never parented the workload -- answers
    it anyway, from `<jail_dir>/exit` and nothing else."""
    handle = _launch(["/bin/sh", "-c", "exit 9"])
    assert handle.wait(timeout=20.0) == 9

    _forget_the_in_process_record(handle)

    result = _in_a_second_process(handle, tmp_path)
    assert "exit_error" not in result, result
    assert result["exit_status"] == 9, result
    assert result["pid"] != os.getpid(), "the helper did not run as its own process"


@pytest.mark.integration
def test_an_unrecorded_exit_refuses_instead_of_reporting_success() -> None:
    """THE HALF THAT MATTERS MOST. With no observation of how the workload
    ended, the status is unknowable and the honest answer is a refusal.
    Returning 0 here is what made the allowed-write control vacuous.

    The unobserved state is the one decision-156 left standing and named: a
    jail whose wrapper never wrote -- the group was `SIGKILL`ed, or the jail
    directory has been swept. It is reached deterministically by removing the
    exit file and dropping this process's own record, rather than by racing a
    kill against a write.

    THE CONTROL is the first assertion: the same handle answers `0` while
    both records are in place, so the refusal below is attributable to their
    removal and not to `wait()` being broken outright."""
    handle = _launch(["/bin/sh", "-c", "exit 0"])
    assert handle.wait(timeout=20.0) == 0

    _forget_the_in_process_record(handle)
    os.remove(exit_path(handle.jail_dir))

    with pytest.raises(ExitStatusUnobservable):
        handle.wait(timeout=5.0)


@pytest.mark.integration
def test_a_second_launch_in_one_jail_dir_does_not_read_the_first_status() -> None:
    """decision-162 (2026-09-08): a stale record is cleared at launch.

    The defect, in the shape it was found: two launches into the SAME jail
    directory. `wait()` prefers whatever `<jail_dir>/exit` holds, so the
    second launch returned the FIRST workload's status the instant it was
    asked -- before its own workload had finished, which also meant its
    stdio was read empty. It was found on Linux, by the one test that
    launches twice into a directory (`tests/integration/test_bwrap_fs.py`'s
    read-allowlist control), and it was never a Linux fact: nothing in this
    reproduction is platform-specific.

    THE CONTROL is the first assertion -- the first launch's own status,
    observed the ordinary way, is what makes `7` a number that was really
    there to be wrongly returned.
    """
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)

    def launch_in(argv: list[str], io: IoPolicy) -> Handle:
        return SubprocessLauncher().launch(
            Stack([]).compile(Spec()),
            argv=argv,
            cwd=jail_dir,
            io=io,
            jail_id=f"exitstatus-reuse-{os.path.basename(jail_dir)}",
            jail_dir=jail_dir,
        )

    first = launch_in(["/bin/sh", "-c", "exit 7"], IoPolicy())
    assert first.wait(timeout=20.0) == 7
    assert os.path.exists(exit_path(jail_dir))

    second = launch_in(
        ["/bin/sh", "-c", "sleep 0.3; echo SECOND; exit 0"],
        IoPolicy(stdout_name="second-stdout.log", stderr_name="second-stderr.log"),
    )
    assert second.wait(timeout=20.0) == 0, "the second launch answered with the first's status"
    with open(second.stdout_path, encoding="utf-8") as f:
        assert "SECOND" in f.read(), "wait() returned before the second workload had run"
