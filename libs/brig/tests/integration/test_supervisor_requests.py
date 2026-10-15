"""The requests on a supervised jail's control socket, in a real jail, with the host-side seams
that need patching (decision-191, decision-192, TASK-0079.06).

What `tests/e2e/test_supervised_jail.py` shows through the public API alone this file shows with a
private seam in hand, because each claim needs one:

- a request with no answer, by a supervisor the host stopped, ends the jail at its host-side
  deadline, and the same stop resumed in time is answered (a patched deadline);
- a process never runs before its record is written (a record whose write is made to fail);
- every import is done before a process starts, and the supervisor refuses one after (a program
  with a lazy import planted in it, through the same runtime);
- a supervisor that cannot start, or speaks another protocol, ends the instance and says what
  it said;
- requests from several threads are in flight at once and each reply finds its own caller.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path

import pytest

import brig.run._records as records
import brig.run._supervised as supervised
import brig.run.host as host
from brig.run import (
    KillOutcome,
    SupervisorFailed,
    SupervisorUnresponsive,
    TetherClosed,
    WorkloadSpawnFailed,
)
from brig.run._supervised import host_pid_of
from brig.run._supervisor_program import SUPERVISOR_SOURCE
from tests.supervised_jail import (
    cleanup,
    create_jail,
    instance_group,
    needs_a_supervised_jail,
    new_jail_dir,
    process_state,
    run_to_end,
    running_with,
    sh,
    supervisor_host_pid,
    unique_sleep,
    until,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _needs_a_jail() -> None:
    needs_a_supervised_jail()


def _ended(jail) -> None:  # type: ignore[no-untyped-def]
    report = jail.destroy()
    assert not [item for item in report.items if item.outcome is KillOutcome.FAILED], report


# ---------------------------------------------------------------------------------------------
# A request with no answer ends the jail.
# ---------------------------------------------------------------------------------------------


def test_a_request_the_supervisor_does_not_answer_destroys_the_jail_at_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(supervised, "REQUEST_TIMEOUT_S", 1.0)
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    marker, sleep = unique_sleep()
    try:
        victim = jail.start(sleep)
        assert until(lambda: running_with(marker) == [victim.pid])
        assert victim.interrupt() is True  # answered, promptly: the control
        init = supervisor_host_pid(instance_group(jail))

        os.kill(init, signal.SIGSTOP)  # wedged: it reads nothing and answers nothing
        assert until(lambda: process_state(init) == "T")
        began = time.monotonic()
        with pytest.raises(SupervisorUnresponsive, match="did not answer 'signal' within 1.0s"):
            victim.interrupt()
        # At once (decision-193): the deadline, then a SIGKILL the stopped init cannot defer; a
        # ladder that sent SIGTERM first would add its 2 s grace to a SIGSTOPped init's.
        assert time.monotonic() - began < 2.5

        # Destroyed without it: the stopped init took the SIGKILL of the ladder, and its namespace,
        # the sleeper in it, went with it.
        assert until(lambda: process_state(init) == "gone")
        assert until(lambda: running_with(marker) == [])
        assert until(lambda: not jail.alive())
        report = jail.destroy()
        assert all(item.outcome is not KillOutcome.FAILED for item in report.items), report
    finally:
        _ended(jail)
        cleanup(jail_dir)


def test_the_same_stop_resumed_within_the_deadline_is_answered_and_the_jail_lives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: it is the missed deadline that ends the jail, not the stop."""
    monkeypatch.setattr(supervised, "REQUEST_TIMEOUT_S", 20.0)
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    _, sleep = unique_sleep()
    try:
        victim = jail.start(sleep)
        init = supervisor_host_pid(instance_group(jail))
        os.kill(init, signal.SIGSTOP)
        assert until(lambda: process_state(init) == "T")
        answered: list[bool] = []
        thread = threading.Thread(target=lambda: answered.append(victim.interrupt()))
        thread.start()
        time.sleep(0.5)
        assert answered == [], "answered while stopped"
        os.kill(init, signal.SIGCONT)
        thread.join(10)
        assert answered == [True]
        # The request was carried out once it could be: the sleeper got its SIGINT. And the jail
        # lived through a stop that was resumed in time.
        assert victim.wait(10) == -signal.SIGINT and jail.alive()
    finally:
        _ended(jail)
        cleanup(jail_dir)


# ---------------------------------------------------------------------------------------------
# A process never runs before its record is written.
# ---------------------------------------------------------------------------------------------


def test_a_process_is_not_allowed_to_run_until_its_record_is_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir, workspace=str(workspace))
    ran = workspace / "ran"
    try:
        real = records.write

        def failing(jail_dir: str, process: records.ProcessRecord) -> str:
            raise OSError(28, "No space left on device (planted)")

        monkeypatch.setattr(records, "write", failing)
        with pytest.raises(OSError, match="planted"):
            jail.start(sh(f"echo ran > {ran}"))
        time.sleep(1.0)
        assert not ran.exists(), "the process ran although its record could not be written"
        assert jail.processes() == ()

        # The control: with the record writable, the same start runs the same command.
        monkeypatch.setattr(records, "write", real)
        assert run_to_end(jail.start(sh(f"echo ran > {ran}")))[0] == 0
        assert ran.exists()
    finally:
        _ended(jail)
        cleanup(jail_dir)


# ---------------------------------------------------------------------------------------------
# Every import before any process; none after.
# ---------------------------------------------------------------------------------------------

#: Where a live process is signalled for a stop: no rehearsal reaches it (the rehearsal stops a
#: process that is already gone), so an import planted here is a late one.
_LIVE_STOP = "        self.signal_group(entry[0], signal.SIGTERM)\n"


def test_a_supervisor_that_imports_after_it_is_ready_fails_the_request_that_needed_the_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert SUPERVISOR_SOURCE.count(_LIVE_STOP) == 1
    planted = SUPERVISOR_SOURCE.replace(_LIVE_STOP, "        import colorsys\n" + _LIVE_STOP)
    marker, sleep = unique_sleep()
    jail_dir = new_jail_dir()
    try:
        monkeypatch.setattr(host, "SUPERVISOR_SOURCE", planted)
        jail = create_jail(jail_dir)  # the planted program says it is ready: the import is lazy
        try:
            item = jail.start(sleep).stop().items[0]
            assert item.outcome is KillOutcome.FAILED
            assert "'colorsys' was not imported before" in item.detail, item.detail
            assert running_with(marker), "the stop that was refused must not have stopped it"
        finally:
            _ended(jail)
        # The control: the program as shipped does the same stop.
        monkeypatch.setattr(host, "SUPERVISOR_SOURCE", SUPERVISOR_SOURCE)
        marker, sleep = unique_sleep()
        jail = create_jail(new_jail_dir(), jail_id="shipped")
        try:
            assert jail.start(sleep).stop().items[0].outcome is KillOutcome.ENDED
        finally:
            _ended(jail)
    finally:
        cleanup(jail_dir)


#: A Python whose `ctypes` and `traceback` do not load `warnings` for the supervisor, which
#: `os.get_exec_path` needs the first time a program is found by name: found by running brig's
#: bwrap tiers in `scripts/linux-jail-check`'s container (Ubuntu's `python3 -I`), where a start of
#: `bash` was refused (3.13 loads it through those two modules, which is why this machine never
#: showed it). Simulated here, whichever Python the test runs under, by unloading it just before
#: `main()` runs.
_BEFORE_MAIN = "\nmain()\n"
_UNLOAD_WARNINGS = '\nimport sys as _sys\n_sys.modules.pop("warnings", None)\nmain()\n'
_TOP_IMPORT = "import warnings  # os.get_exec_path imports it, late, on every Python; the rehearsal covers the rest\n"
_REHEARSAL_CALL = "    supervisor.rehearse()\n"


def test_a_program_found_by_name_starts_where_the_interpreter_loads_nothing_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert SUPERVISOR_SOURCE.count(_TOP_IMPORT) == SUPERVISOR_SOURCE.count(_REHEARSAL_CALL) == 1
    assert SUPERVISOR_SOURCE.count(_BEFORE_MAIN) == 1
    unloaded = SUPERVISOR_SOURCE.replace(_BEFORE_MAIN, _UNLOAD_WARNINGS)
    naive = unloaded.replace(_TOP_IMPORT, "").replace(_REHEARSAL_CALL, "")
    jail_dir = new_jail_dir()
    try:
        monkeypatch.setattr(host, "SUPERVISOR_SOURCE", unloaded)
        jail = create_jail(jail_dir)
        try:
            assert run_to_end(jail.start(["sh", "-c", "echo found by name"])) == (
                0,
                "found by name\n",
            )
        finally:
            _ended(jail)
        # The planted bug: with neither the import nor the rehearsal, the same start is refused.
        monkeypatch.setattr(host, "SUPERVISOR_SOURCE", naive)
        jail = create_jail(new_jail_dir(), jail_id="naive")
        try:
            with pytest.raises(WorkloadSpawnFailed, match="'warnings' was not imported before"):
                jail.start(["sh", "-c", "echo found by name"])
        finally:
            _ended(jail)
    finally:
        cleanup(jail_dir)


# ---------------------------------------------------------------------------------------------
# A supervisor that does not start.
# ---------------------------------------------------------------------------------------------


def test_a_supervisor_that_cannot_start_ends_the_instance_and_says_what_it_said() -> None:
    jail_dir = new_jail_dir()
    try:
        with pytest.raises(SupervisorFailed) as raised:
            create_jail(jail_dir, channel=True, python="/usr/bin/python3.99")
        message = str(raised.value)
        assert "python3.99" in message and "control socket closed" in message, message
        assert os.path.join(jail_dir, "supervisor", "stderr.log") in message
        # Nothing of it is left: the instance was ended before the error came.
        assert until(lambda: running_with(os.path.basename(jail_dir)) == [])
    finally:
        cleanup(jail_dir)


def test_a_supervisor_that_speaks_another_protocol_is_refused_and_ended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = SUPERVISOR_SOURCE.replace("PROTOCOL = 1\n", "PROTOCOL = 99\n", 1)
    assert other != SUPERVISOR_SOURCE
    jail_dir = new_jail_dir()
    try:
        monkeypatch.setattr(host, "SUPERVISOR_SOURCE", other)
        with pytest.raises(SupervisorFailed, match="speaks protocol 99 and this brig speaks 1"):
            create_jail(jail_dir, channel=True)
        assert until(lambda: running_with(os.path.basename(jail_dir)) == [])
    finally:
        cleanup(jail_dir)


# ---------------------------------------------------------------------------------------------
# Several requests in flight, a reply to its caller.
# ---------------------------------------------------------------------------------------------


def test_a_wait_in_flight_does_not_hold_up_a_start_from_another_thread() -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    marker, sleep = unique_sleep()
    try:
        slow = jail.start(sleep)
        waited: list[object] = []

        def wait_for_it() -> None:
            try:
                waited.append(slow.wait(20))
            except Exception as error:  # the test reports it
                waited.append(error)

        thread = threading.Thread(target=wait_for_it)
        thread.start()
        time.sleep(0.5)  # the wait request is outstanding at the supervisor now

        began = time.monotonic()
        quick = [jail.start(sh(f"echo {n}")) for n in range(4)]
        outputs = [run_to_end(p)[1].strip() for p in quick]
        assert time.monotonic() - began < 5.0, "starts waited behind a wait"
        assert outputs == ["0", "1", "2", "3"], "a reply reached the wrong caller"
        assert waited == [] and thread.is_alive(), "the wait answered while its process ran"

        slow.stop()
        thread.join(20)
        assert waited == [-signal.SIGTERM]
    finally:
        _ended(jail)
        cleanup(jail_dir)


# ---------------------------------------------------------------------------------------------
# A tether that has ended refuses a start before anything is made.
# ---------------------------------------------------------------------------------------------


def test_a_start_on_a_jail_whose_tether_has_ended_is_refused_before_anything_is_made() -> None:
    jail_dir = new_jail_dir()
    watched, tether = os.pipe()
    jail = create_jail(jail_dir, tether=watched)
    os.close(watched)
    try:
        assert run_to_end(jail.start(sh("echo yes")))[1] == "yes\n"
        procs = os.path.join(jail_dir, "procs")
        before = sorted(os.listdir(procs))
        os.close(tether)  # every write end is closed: the tether has ended
        with pytest.raises(TetherClosed):
            jail.start(sh("echo too late"))
        assert sorted(os.listdir(procs)) == before, "a refused start made something"
    finally:
        _ended(jail)
        cleanup(jail_dir)


# ---------------------------------------------------------------------------------------------
# The kernel's own translation between pid namespaces.
# ---------------------------------------------------------------------------------------------


def test_host_pid_of_names_a_process_by_its_pidfd_and_not_one_that_has_gone() -> None:
    import subprocess

    child = subprocess.Popen(["/bin/sleep", "30"])
    try:
        fd = os.pidfd_open(child.pid)
        try:
            assert host_pid_of(fd) == child.pid
            child.kill()
            child.wait()
            assert host_pid_of(fd) is None, "a process that has gone has no pid to name"
        finally:
            os.close(fd)
        assert host_pid_of(10**6) is None  # not a descriptor of ours
    finally:
        child.kill()
        child.wait()


def test_a_jail_that_is_destroyed_answers_no_more_requests_and_says_so() -> None:
    from brig.run import SupervisorGone

    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    try:
        jail.destroy()
        with pytest.raises(SupervisorGone):
            jail.start(["/bin/true"])
    finally:
        _ended(jail)
        cleanup(jail_dir)
