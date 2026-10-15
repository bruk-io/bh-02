"""Per-process records in a HOST jail (decision-181, TASK-0079.25).

`HostRuntime.create` makes the jail and starts nothing; every process, the
first included, is a `HostSupervisor.start` with its own exit wrapper, its own
tether watcher and its own records directory `<jail_dir>/procs/<id>/`
(`record.json`, `exit`, its stdio). The claims here, each observed from outside
the code under test where a process is concerned (`/bin/ps`, `os.path`):

- create starts nothing; each start has its own records, wrapper and watcher,
  and closing the tether ends every start's group, siblings included;
- a start refuses on a tether that has ended, and makes nothing;
- each process's exit record is its own, readable by a supervisor that never
  started it;
- a record write that fails after the spawn ends that process and raises;
- a record outlives `wait`: `destroy` after a waited sibling still ends a
  descendant the sibling left in its group (AC7, seen failing on the tree
  before the change, where `wait` deregistered the sibling);
- `create` over a used `jail_dir` removes a gone jail's records following no
  links, and on any doubt refuses and removes nothing, never a live jail's.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator

import pytest

from brig.core import Spec, unenforced_report
from brig.run import IoPolicy, Jail, Process, _identity, _records, _waiters
from brig.run._tether import TetherClosed
from brig.run.host import HostRuntime, _clear_earlier_records
from brig.run.runtime import JailRecord
from brig.run.teardown import KillOutcome
from brig.stack import CompiledJail
from tests.conftest import (
    launch,
    teardown_group,
    teardown_pgid,
    tether_has_ended,
    workload_argv,
)

pytestmark = pytest.mark.integration

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root with this file's own infix (`pd`)."""
    return f"/tmp/bg{os.getpid()}pd{next(_jail_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail() -> CompiledJail:
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


def _live_members(pgid: int) -> list[int]:
    """Non-zombie pids in `pgid`, from `/bin/ps` (alias-proof, decision-026)."""
    table = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid=,stat="], capture_output=True, text=True, check=True
    ).stdout
    return [
        int(pid)
        for pid, group, state in (line.split() for line in table.splitlines() if line.strip())
        if int(group) == pgid and not state.startswith("Z")
    ]


def _args(pid: int) -> str:
    """`pid`'s whole command line, from `/bin/ps` (no truncation)."""
    return subprocess.run(
        ["/bin/ps", "-ww", "-o", "args=", "-p", str(pid)], capture_output=True, text=True
    ).stdout


def _wait_for(predicate: Callable[[], bool], seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def _kill_group(pgid: int) -> None:
    """End `pgid` with the suite's own verified helper, never the code under test."""
    teardown_pgid(pgid)


@pytest.fixture
def jail_dir() -> Iterator[str]:
    path = _new_jail_dir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC1: create starts nothing; each start its own records, wrapper and watcher.
# ---------------------------------------------------------------------------


def test_create_starts_nothing_and_each_start_has_its_own_records_wrapper_and_watcher(
    run_id: str, jail_dir: str
) -> None:
    runtime = HostRuntime()
    read_end, write_end = os.pipe()
    record = runtime.create(
        _compiled_jail(), cwd=jail_dir, jail_id="records-ac1", jail_dir=jail_dir, tether=read_end
    )
    os.close(read_end)  # the jail holds its own duplicate (decision-181)
    started: list[int] = []
    try:
        assert os.path.isdir(jail_dir)
        assert not os.path.exists(_records.procs_dir(jail_dir)), "create started something"
        assert runtime.alive(record) is False
        assert runtime.destroy(record).items == ()

        supervisor = runtime.supervisor(record)
        one = supervisor.start(workload_argv(run_id, "sleep 100"), cwd=jail_dir, io=IoPolicy())
        started.append(one.pgid)
        two = supervisor.start(workload_argv(run_id, "sleep 100"), cwd=jail_dir, io=IoPolicy())
        started.append(two.pgid)

        assert one.id != two.id and _records.is_id(one.id) and _records.is_id(two.id)
        assert _records.scan(jail_dir).records == (one, two)
        for process in (one, two):
            directory = _records.process_dir(jail_dir, process.id)
            assert sorted(os.listdir(directory)) == ["record.json", "stderr.log", "stdout.log"]
            assert process.stdout_path == os.path.join(directory, "stdout.log")
            # Its pid is its own exit wrapper, which leads its own group...
            assert process.pgid == process.pid
            assert "brig exit wrapper" in _args(process.pid)
            # ...and in that group, a tether watcher of its own.
            assert _wait_for(
                lambda p=process: any(
                    "os.killpg(0, signal.SIGKILL)" in _args(member)
                    for member in _live_members(p.pgid)
                )
            ), f"no tether watcher in process group {process.pgid}"
        assert runtime.alive(record) is True

        os.close(write_end)
        write_end = -1
        for process in (one, two):
            assert _wait_for(lambda p=process: not _live_members(p.pgid)), (
                f"process group {process.pgid} outlived the tether"
            )
    finally:
        if write_end != -1:
            os.close(write_end)
        for pgid in started:
            _kill_group(pgid)


def test_a_start_on_a_tether_that_has_ended_is_refused_and_makes_nothing(
    run_id: str, jail_dir: str
) -> None:
    """Decided for TASK-0079.25 (point 2): refuse, rather than start a process
    its watcher would kill at once. The control: the same jail starts while the
    tether lives. The tether has ended when every write end is closed
    (`tether_has_ended`), and the control's own watcher, which ends its group
    then, has a moment to: the test waits for that, as a group left to it
    reads as a leak."""
    runtime = HostRuntime()
    read_end, write_end = os.pipe()
    record = runtime.create(
        _compiled_jail(), cwd=jail_dir, jail_id="records-eof", jail_dir=jail_dir, tether=read_end
    )
    ours = os.dup(read_end)  # to see when every write end is closed
    os.close(read_end)
    try:
        supervisor = runtime.supervisor(record)
        control = supervisor.start(["/usr/bin/true"], cwd=jail_dir, io=IoPolicy())
        assert supervisor.wait(control, 10.0) == 0

        os.close(write_end)
        assert tether_has_ended(ours), "a copy of the tether's write end stayed open"
        with pytest.raises(TetherClosed, match="tether has ended"):
            supervisor.start(workload_argv(run_id, "sleep 100"), cwd=jail_dir, io=IoPolicy())
        assert [r.id for r in _records.scan(jail_dir).records] == [control.id]
        assert _wait_for(lambda: not _live_members(control.pgid)), (
            f"the control's group {control.pgid} outlived the tether"
        )
    finally:
        os.close(ours)


def test_a_tether_has_not_ended_while_any_copy_of_its_write_end_is_open(
    run_id: str, jail_dir: str
) -> None:
    """What `TetherClosed` promises and what it does not (SPEC.md section 8): the tether has
    ended when every write end is closed, so a copy that a forked child still holds, between its
    fork and its exec, keeps it open and a start is not refused; the start goes ahead and its
    watcher ends it once the copy is gone. The control: with the copy closed too, the same
    start is refused."""
    runtime = HostRuntime()
    read_end, write_end = os.pipe()
    record = runtime.create(
        _compiled_jail(), cwd=jail_dir, jail_id="records-copy", jail_dir=jail_dir, tether=read_end
    )
    ours = os.dup(read_end)
    os.close(read_end)
    copy = os.dup(write_end)  # the child that another thread forked, still before its exec
    supervisor = runtime.supervisor(record)
    started = []
    try:
        os.close(write_end)
        assert not tether_has_ended(ours, timeout=0.2)  # a copy remains
        started.append(
            supervisor.start(workload_argv(run_id, "sleep 100"), cwd=jail_dir, io=IoPolicy())
        )  # not refused
        os.close(copy)
        copy = -1
        assert tether_has_ended(ours)
        assert _wait_for(lambda: not _live_members(started[0].pgid)), "its watcher did not end it"
        with pytest.raises(TetherClosed):  # the control
            supervisor.start(workload_argv(f"{run_id}b", "sleep 100"), cwd=jail_dir, io=IoPolicy())
    finally:
        os.close(ours)
        if copy != -1:
            os.close(copy)
        for process in started:
            _kill_group(process.pgid)


def test_each_process_has_its_own_exit_record_read_by_any_supervisor(jail_dir: str) -> None:
    runtime = HostRuntime()
    record = runtime.create(
        _compiled_jail(), cwd=jail_dir, jail_id="records-exit", jail_dir=jail_dir, tether=None
    )
    supervisor = runtime.supervisor(record)
    three = supervisor.start(["/bin/sh", "-c", "exit 3"], cwd=jail_dir, io=IoPolicy())
    five = supervisor.start(["/bin/sh", "-c", "exit 5"], cwd=jail_dir, io=IoPolicy())
    assert supervisor.wait(three, 10.0) == 3
    assert supervisor.wait(five, 10.0) == 5

    for process, status in ((three, 3), (five, 5)):
        with open(_records.exit_path(jail_dir, process.id), encoding="utf-8") as recorded:
            assert recorded.read().strip() == str(status)
        _waiters.forget(process.pid)
    # A supervisor over a record with nothing held in memory, as in a later
    # process: the exit records alone answer.
    elsewhere = HostRuntime().supervisor(dataclasses.replace(record, held=None))
    assert elsewhere.wait(three, 1.0) == 3
    assert elsewhere.wait(five, 1.0) == 5


def test_a_record_that_cannot_be_written_ends_its_process_and_raises(
    run_id: str, jail_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decided for TASK-0079.25 (point 5): a process whose record could not be
    written runs unrecorded, so the start ends it through the ladder, removes
    its records directory, and re-raises with a note saying so."""
    runtime = HostRuntime()
    record = runtime.create(
        _compiled_jail(), cwd=jail_dir, jail_id="records-unwritten", jail_dir=jail_dir, tether=None
    )
    spawned: list[int] = []

    def failing_write(directory: str, process: _records.ProcessRecord) -> str:
        del directory
        spawned.append(process.pgid)
        assert _live_members(process.pgid), "CONTROL failed: the process never ran"
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(_records, "write", failing_write)
    try:
        with pytest.raises(OSError, match="No space left") as raised:
            runtime.supervisor(record).start(
                workload_argv(run_id, "sleep 100"), cwd=jail_dir, io=IoPolicy()
            )
        assert any("was ended" in note for note in raised.value.__notes__), raised.value.__notes__
        (pgid,) = spawned
        assert _live_members(pgid) == []
        assert os.listdir(_records.procs_dir(jail_dir)) == []
    finally:
        for pgid in spawned:
            _kill_group(pgid)


# ---------------------------------------------------------------------------
# AC7: a record outlives wait.
# ---------------------------------------------------------------------------


def test_destroy_after_a_waited_sibling_ends_what_it_left_in_its_group(
    run_id: str, jail_dir: str
) -> None:
    """The sibling's shell backgrounds a `sleep` and exits 0, so `wait()`
    answers while its group still holds the `sleep`. Before decision-181 that
    wait deregistered the sibling and `kill()` never looked at its group again:
    the `sleep` escaped (seen on the tree before TASK-0079.25). Now its record
    outlives the wait and `kill()` ends it."""
    os.makedirs(jail_dir, exist_ok=True)
    jail, process = launch(
        _compiled_jail(),
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="records-ac7",
        jail_dir=jail_dir,
    )
    left = shlex.join(workload_argv(run_id, "sleep 100"))
    groups = [process._record.pgid]
    try:
        sibling = jail.start(["/bin/sh", "-c", f"{left} &\nexit 0"])
        groups.append(sibling.pid)
        assert sibling.wait(timeout=10.0) == 0
        assert _wait_for(lambda: bool(_live_members(sibling.pid))), (
            "CONTROL failed: the sibling left nothing running in its group"
        )

        report = jail.destroy()

        assert _live_members(sibling.pid) == [], f"the left-behind process escaped ({report})"
        by_identity = {item.identity: item for item in report.items}
        assert by_identity[str(sibling.pid)].kind == "exec_sibling"
        assert by_identity[str(sibling.pid)].outcome is KillOutcome.ENDED, report
    finally:
        for pgid in groups:
            _kill_group(pgid)


# ---------------------------------------------------------------------------
# AC6: create over a used jail_dir.
# ---------------------------------------------------------------------------


def _listing(root: str) -> list[str]:
    """Every path under `root`, relative, links not followed."""
    found: list[str] = []
    for directory, dirs, files in os.walk(root):
        found.extend(os.path.relpath(os.path.join(directory, n), root) for n in (*dirs, *files))
    return sorted(found)


def _plant(jail_dir: str, record: dict[str, object], process_id: str | None = None) -> str:
    """Write a record by hand under `<jail_dir>/procs/`; returns its directory."""
    process_id = process_id or _records.new_id()
    directory = os.path.join(_records.procs_dir(jail_dir), process_id)
    os.makedirs(directory)
    body = {
        "id": process_id,
        "order": 1,
        "pid": 5,
        "pgid": 5,
        "start_time": "x",
        "argv": [],
        "stdout_path": "",
        "stderr_path": "",
        "channel": None,
        "bound_path": None,
        **record,
    }
    with open(os.path.join(directory, "record.json"), "w", encoding="utf-8") as f:
        json.dump(body, f)
    return directory


def _gone_pid() -> tuple[int, str]:
    """A pid that held a process a moment ago, with that process's stamp."""
    proc = subprocess.Popen(["/bin/sh", "-c", "sleep 0.2"], start_new_session=True)
    stamp = _identity.start_stamp(proc.pid)
    proc.wait()
    return proc.pid, stamp


def _launch_live(run_id: str, jail_dir: str) -> tuple[Jail, Process]:
    os.makedirs(jail_dir, exist_ok=True)
    return launch(
        _compiled_jail(),
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="records-live",
        jail_dir=jail_dir,
    )


def _create(jail_dir: str) -> JailRecord:
    return HostRuntime().create(
        _compiled_jail(), cwd=jail_dir, jail_id="records-again", jail_dir=jail_dir, tether=None
    )


def test_create_over_a_live_jail_refuses_and_removes_nothing(run_id: str, jail_dir: str) -> None:
    jail, process = _launch_live(run_id, jail_dir)
    try:
        before = _listing(jail_dir)
        with pytest.raises(_records.JailDirInUse) as refused:
            _create(jail_dir)
        message = str(refused.value)
        assert jail_dir in message and "still runs" in message and "Destroy" in message
        assert _listing(jail_dir) == before
        assert jail.alive() is True

        # The control: once that jail is destroyed, the same create proceeds and
        # removes its records.
        jail.destroy()
        record = _create(jail_dir)
        assert not os.path.exists(_records.procs_dir(jail_dir))
        assert record.processes == ()
    finally:
        teardown_group(process)


def test_a_planted_record_naming_a_recycled_pid_holds_nothing_but_never_frees_a_live_jail(
    run_id: str, jail_dir: str
) -> None:
    """A record whose leader's pid now names another process (here: this test
    process, under a stamp it never had) no longer holds that group, whatever
    the group's liveness says (this process's own group lives): alone, it is
    removed. Beside a live jail's records it is refused with them, and nothing
    is removed."""
    _plant(jail_dir, {"pid": os.getpid(), "pgid": os.getpgrp(), "start_time": "planted-stamp"})
    _create(jail_dir)
    assert not os.path.exists(_records.procs_dir(jail_dir))

    jail, process = _launch_live(run_id, jail_dir)
    try:
        planted = _plant(
            jail_dir, {"pid": os.getpid(), "pgid": os.getpgrp(), "start_time": "planted-stamp"}
        )
        before = _listing(jail_dir)
        with pytest.raises(_records.JailDirInUse, match="still runs"):
            _create(jail_dir)
        assert _listing(jail_dir) == before
        assert os.path.isdir(planted)
        assert jail.alive() is True
    finally:
        teardown_group(process)


def _doubt(jail_dir: str, kind: str, outside: str) -> None:
    """Plant one doubt under `<jail_dir>/procs/`."""
    pid, stamp = _gone_pid()
    procs = _records.procs_dir(jail_dir)
    match kind:
        case "unreadable-record":
            directory = _plant(jail_dir, {})
            with open(os.path.join(directory, "record.json"), "w", encoding="utf-8") as f:
                f.write("{ not json")
        case "unknown-stamp":
            _plant(jail_dir, {"pid": pid, "pgid": pid, "start_time": ""})
        case "id-out-of-range":
            _plant(jail_dir, {"pid": pid, "pgid": 0, "start_time": stamp})
        case "link":
            os.makedirs(procs)
            os.symlink(outside, os.path.join(procs, _records.new_id()))
        case "file":
            os.makedirs(procs)
            with open(os.path.join(procs, _records.new_id()), "w", encoding="utf-8") as f:
                f.write("{}")
        case "no-record":
            os.makedirs(os.path.join(procs, _records.new_id()))
        case "procs-is-a-link":
            os.makedirs(jail_dir)
            os.symlink(outside, procs)
        case _:
            raise AssertionError(kind)
    # Beside every doubt, a gone jail's genuine record: alone, it would go.
    if kind != "procs-is-a-link":
        _plant(jail_dir, {"pid": pid, "pgid": pid, "start_time": stamp})


_DOUBTS = (
    "unreadable-record",
    "unknown-stamp",
    "id-out-of-range",
    "link",
    "file",
    "no-record",
    "procs-is-a-link",
)


@pytest.fixture
def outside() -> Iterator[str]:
    """A directory a planted link points at, with a file in it that must survive."""
    path = tempfile.mkdtemp(prefix="bg-outside-")
    with open(os.path.join(path, "keep"), "w", encoding="utf-8") as f:
        f.write("keep")
    try:
        yield path
    finally:
        shutil.rmtree(path)


@pytest.mark.parametrize("kind", _DOUBTS)
def test_create_refuses_on_any_doubt_and_removes_nothing(
    jail_dir: str, outside: str, kind: str
) -> None:
    _doubt(jail_dir, kind, outside)
    before = _listing(jail_dir)
    with pytest.raises(_records.JailDirInUse) as refused:
        _create(jail_dir)
    assert "nothing was removed" in str(refused.value)
    assert _listing(jail_dir) == before
    assert os.listdir(outside) == ["keep"]


def test_create_refuses_when_the_process_table_cannot_be_read(jail_dir: str) -> None:
    pid, stamp = _gone_pid()
    _plant(jail_dir, {"pid": pid, "pgid": pid, "start_time": stamp})
    before = _listing(jail_dir)

    def unreadable() -> str:
        raise OSError("no /bin/ps here")

    with pytest.raises(_records.JailDirInUse, match="process table can't be read"):
        _clear_earlier_records(jail_dir, read_table=unreadable)
    assert _listing(jail_dir) == before
    # The control: with the table readable, the same gone record is removed.
    _clear_earlier_records(jail_dir)
    assert not os.path.exists(_records.procs_dir(jail_dir))


def test_a_gone_jails_records_are_removed_following_no_links(jail_dir: str, outside: str) -> None:
    """A jail that ran and ended: its records, exit record and stdio go, and a
    link planted inside a record's directory is removed, never followed (the
    directory it points at keeps its file)."""
    os.makedirs(jail_dir)
    jail, process = launch(
        _compiled_jail(),
        argv=["/bin/sh", "-c", "exit 4"],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="records-gone",
        jail_dir=jail_dir,
    )
    assert process.wait(timeout=10.0) == 4
    directory = os.path.dirname(process.stdout_path)
    assert os.path.isfile(os.path.join(directory, "exit"))
    os.symlink(outside, os.path.join(directory, "planted-link"))

    _create(jail_dir)

    assert not os.path.exists(_records.procs_dir(jail_dir))
    assert os.listdir(outside) == ["keep"]
