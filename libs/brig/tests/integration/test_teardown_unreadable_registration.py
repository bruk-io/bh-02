"""Teardown is total (TASK-0079.14, decision-175).

An exec registration brig cannot read (not JSON, a missing key, a wrong type)
used to make `_execs.live` raise, so `kill_jail` stopped after the workload
group and left every exec sibling and every helper running. Now the entry is its
own `FAILED` item, saying which entry and what to do, and every other item is
torn down. Since decision-181 the records are directories under
`<jail_dir>/procs/` (`brig/run/_records.py`), and the plants moved there: a
`record.json` brig can't read, and an entry that is no record at all (a link,
a file, a name that is no id, a directory with no `record.json`).

The plant is made from the HOST side, beside the genuine records: no grant
reaches `procs/` (decision-173, decision-174, decision-181), so what produces
such an entry is tampering on the host or a broken disk. Every observation of a process goes through `/bin/ps`, never
through the module under test, and a genuine sibling registered BEFORE the plant
is the control: it must be `ENDED`, so a surviving process is the bug and not a
teardown that ran nothing.

The last test is the other half of the story: a genuine record whose
leader was reaped, with its group still holding a live member, is still ended.
"""

import dataclasses
import itertools
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from brig.core import Spec
from brig.run import IoPolicy, SubprocessLauncher, _identity, _records
from brig.run.exec_ import exec_in_jail
from brig.run.handle import Handle
from brig.run.teardown import KillOutcome
from brig.stack import Stack
from tests.conftest import teardown_group, workload_argv

pytestmark = pytest.mark.integration

_jail_counter = itertools.count()


def _launch(run_id: str) -> Handle:
    jail_dir = f"/tmp/bg{os.getpid()}ur{next(_jail_counter)}"
    os.makedirs(jail_dir, exist_ok=True)
    return SubprocessLauncher().launch(
        Stack([]).compile(Spec()),
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"unreadable-{os.path.basename(jail_dir)}",
        jail_dir=jail_dir,
    )


def _live_members(pgid: int) -> list[int]:
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid=,stat="], capture_output=True, text=True, check=True
    )
    return [
        int(parts[0])
        for parts in (line.split() for line in proc.stdout.splitlines())
        if len(parts) == 3 and int(parts[1]) == pgid and not parts[2].startswith("Z")
    ]


def _wait_for_members(pgid: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not _live_members(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)


def _plant_record(jail_dir: str, pid: int, pgid: int, stamp: str) -> str:
    """Write a well-formed record under `<jail_dir>/procs/`, as brig would;
    returns its directory."""
    process_id = _records.new_id()
    directory = _records.make_dir(jail_dir, process_id)
    _records.write(
        jail_dir,
        _records.ProcessRecord(
            id=process_id,
            order=time.time_ns(),
            pid=pid,
            pgid=pgid,
            start_time=stamp,
            argv=("planted",),
            stdout_path=os.path.join(directory, "stdout.log"),
            stderr_path=os.path.join(directory, "stderr.log"),
        ),
    )
    return directory


def _record(**fields: object) -> dict[str, object]:
    """A `record.json`'s content: `fields` over a well-formed record's, with
    `id` left for `_plant` to fill in."""
    base: dict[str, object] = {
        "order": 1,
        "pid": 5,
        "pgid": 5,
        "start_time": "x",
        "argv": [],
        "stdout_path": "",
        "stderr_path": "",
    }
    base.update(fields)
    return base


_UNREADABLE: dict[str, bytes | dict[str, object]] = {
    "not-json": b"{ this is not json",
    "empty": b"",
    "not-utf8": b"\xff\xfe\x00",
    "not-an-object": b"[1, 2, 3]",
    "missing-keys": b'{"pid": 1}',
    "wrong-types": _record(pid="1"),
    "stamp-not-str": _record(start_time=5),
    "absurd-pid": _record(pid=1180591620717411303424, pgid=7),
    "absurd-pgid": _record(pgid=1180591620717411303424),
    "pgid-zero": _record(pgid=0),
    "pgid-one": _record(pgid=1),
    "pgid-negative": _record(pgid=-5),
    "pgid-past-pid-max": _record(pgid=2147483648),
    "another-id": _record(id="fedcba9876543210"),
    "unknown-key": _record(extra=1),
}

#: Entries under `procs/` that are no record brig made, by what they are.
_NOT_RECORDS = ("link", "file", "bad-name", "no-record")


def _plant(procs: str, kind: str, content: bytes | dict[str, object] = b"") -> str:
    """Plant one unreadable entry under `procs`; returns its path."""
    match kind:
        case "record":
            process_id = _records.new_id()
            path = os.path.join(procs, process_id)
            os.mkdir(path)
            if isinstance(content, dict):
                content = json.dumps({"id": process_id, **content}).encode()
            with open(os.path.join(path, "record.json"), "wb") as record:
                record.write(content)
            return path
        case "link":
            path = os.path.join(procs, _records.new_id())
            os.symlink("/tmp", path)
            return path
        case "file":
            path = os.path.join(procs, _records.new_id())
            with open(path, "wb") as record:
                record.write(b"{}")
            return path
        case "bad-name":
            path = os.path.join(procs, "..notanid")
            os.mkdir(path)
            return path
        case "no-record":
            path = os.path.join(procs, _records.new_id())
            os.mkdir(path)
            return path
    raise AssertionError(kind)


_PLANTS: list[tuple[str, bytes | dict[str, object]]] = [
    ("record", content) for content in _UNREADABLE.values()
] + [(kind, b"") for kind in _NOT_RECORDS]
_PLANT_IDS = [*_UNREADABLE, *_NOT_RECORDS]


@pytest.mark.parametrize(("kind", "content"), _PLANTS, ids=_PLANT_IDS)
def test_an_unreadable_record_is_its_own_failed_item_and_the_rest_is_torn_down(
    run_id: str, kind: str, content: bytes | dict[str, object]
) -> None:
    handle = _launch(run_id)
    sibling = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
    helper = subprocess.Popen(workload_argv(run_id, "sleep 100"), start_new_session=True)
    handle = dataclasses.replace(
        handle, helper_pids=(helper.pid,), helper_stamps=(_identity.start_stamp(helper.pid),)
    )
    try:
        _wait_for_members(handle.pgid)
        _wait_for_members(sibling.pid)
        _wait_for_members(helper.pid)
        assert _live_members(helper.pid), "CONTROL failed: the helper group is empty"
        assert _live_members(handle.pgid), "CONTROL failed: the workload group is empty"
        assert _live_members(sibling.pid), "CONTROL failed: the sibling group is empty"

        plant = _plant(_records.procs_dir(handle.jail_dir), kind, content)

        report = handle.kill()  # must not raise

        assert _live_members(handle.pgid) == [], report
        assert _live_members(sibling.pid) == [], f"the sibling outlived teardown ({report})"
        assert _live_members(helper.pid) == [], f"the helper outlived teardown ({report})"
        assert {i.kind: i.outcome for i in report.items if i.kind == "helper"} == {
            "helper": KillOutcome.ENDED
        }, report
        by_identity = {item.identity: item for item in report.items}
        assert by_identity[str(handle.pgid)].outcome is KillOutcome.ENDED, report
        assert by_identity[str(sibling.pid)].outcome is KillOutcome.ENDED, report
        (bad,) = [item for item in report.items if item.identity == plant]
        assert bad.kind == "exec_sibling"
        assert bad.outcome is KillOutcome.FAILED, bad
        assert plant in bad.detail, bad.detail
        assert "nothing it names was signalled" in bad.detail, bad.detail
        assert "inspect" in bad.detail.lower(), bad.detail
        assert os.path.lexists(plant), "teardown removed the entry it could not read"
    finally:
        teardown_group(handle)
        subprocess.run(["/bin/kill", "-KILL", "--", f"-{helper.pid}"], check=False)
        helper.wait()


_OWN_GROUP_CHILD = """
import dataclasses, json, os, sys
from brig.core import Spec
from brig.run import IoPolicy, SubprocessLauncher, _identity, _records
from brig.stack import Stack

jail_dir = sys.argv[1]
os.makedirs(jail_dir, exist_ok=True)
handle = SubprocessLauncher().launch(
    Stack([]).compile(Spec()),
    argv=["/bin/sh", "-c", "sleep 100 & wait"],
    cwd=jail_dir,
    io=IoPolicy(),
    jail_id="own-group-child",
    jail_dir=jail_dir,
)
own = os.getpgrp()
process_id = _records.new_id()
directory = _records.make_dir(jail_dir, process_id)
_records.write(jail_dir, _records.ProcessRecord(
    id=process_id, order=0, pid=os.getpid(), pgid=own,
    start_time=_identity.start_stamp(os.getpid()), argv=(),
    stdout_path=os.path.join(directory, "o"), stderr_path=os.path.join(directory, "e"),
))
report = handle.kill()
zero_report = dataclasses.replace(handle, pgid=0).kill()
print(json.dumps({
    "own": own,
    "items": [[i.kind, i.identity, i.outcome.name, i.detail] for i in report.items],
    "zero": [[i.kind, i.identity, i.outcome.name, i.detail] for i in zero_report.items],
}))
"""


def test_a_record_naming_the_trusted_process_s_own_group_is_refused_and_nothing_is_signalled(
    run_id: str,
) -> None:
    """A record naming the group the trusted process itself runs in (in
    range, a stamp present) must not be signalled, and neither must a workload
    group of 0, which `killpg` reads as the caller's own.

    The kill runs in a child Python in its own session, registering the child's
    OWN pid, stamp and group, so a regressed guard signals only the child: it
    dies by a signal and this test fails with a message, never taking pytest's
    group with it."""
    jail_dir = f"/tmp/bg{os.getpid()}og{next(_jail_counter)}"
    child = subprocess.run(
        [sys.executable, "-c", _OWN_GROUP_CHILD, jail_dir],
        capture_output=True,
        text=True,
        start_new_session=True,
        timeout=120,
    )
    try:
        assert child.returncode == 0, (
            f"the child running handle.kill() exited with {child.returncode} (negative: killed by "
            f"that signal), so the own-group guard regressed and teardown signalled its own "
            f"group; stderr: {child.stderr}"
        )
        said = json.loads(child.stdout)
        own = str(said["own"])
        (own_item,) = [i for i in said["items"] if i[1] == own]
        assert own_item[2] == "FAILED", own_item
        assert "nothing was signalled" in own_item[3], own_item
        assert said["items"][0][2] == "ENDED", said
        # By identity: the handle's group 0 now disagrees with the first
        # process's record on disk, whose copy is its own FAILED workload_group
        # item since TASK-0079.26 (identity the record's path).
        (zero_item,) = [i for i in said["zero"] if i[0] == "workload_group" and i[1] == "0"]
        assert zero_item[2] == "FAILED", zero_item
        assert "nothing was signalled" in zero_item[3], zero_item
    finally:
        shutil.rmtree(jail_dir, ignore_errors=True)


def test_an_exception_from_one_item_is_that_item_s_failure_and_a_later_item_still_ends(
    run_id: str,
) -> None:
    """A helper whose pid the OS rejects (`waitpid` raises `OverflowError`) is
    its own `FAILED` item, and the items after it (a second, genuine helper)
    and before it (the workload, the sibling) are still ended."""
    handle = _launch(run_id)
    sibling = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
    later = subprocess.Popen(workload_argv(run_id, "sleep 100"), start_new_session=True)
    handle = dataclasses.replace(
        handle,
        helper_pids=(2**70, later.pid),
        helper_stamps=("x", _identity.start_stamp(later.pid)),
    )
    try:
        _wait_for_members(sibling.pid)
        _wait_for_members(later.pid)
        assert _live_members(later.pid), "CONTROL failed: the later helper group is empty"
        report = handle.kill()  # must not raise

        assert _live_members(sibling.pid) == [], report
        assert _live_members(later.pid) == [], f"the later helper outlived teardown ({report})"
        helpers = [i for i in report.items if i.kind == "helper"]
        assert [h.outcome for h in helpers] == [KillOutcome.FAILED, KillOutcome.ENDED], report
        assert "OverflowError" in helpers[0].detail, helpers[0].detail
    finally:
        teardown_group(handle)
        subprocess.run(["/bin/kill", "-KILL", "--", f"-{later.pid}"], check=False)
        later.wait()


def test_teardown_still_ends_the_group_of_a_genuine_record_whose_leader_was_reaped(
    run_id: str,
) -> None:
    """The leader exits and is reaped, so its pid names nothing; a member of its
    group lives on. The record is genuine (a real stamp taken while the
    leader lived), so the ladder signals the group and ends it."""
    handle = _launch(run_id)
    body = f": {run_id}; sleep 100 & sleep 1"
    leader = subprocess.Popen(["/bin/bash", "-c", body], start_new_session=True)
    try:
        stamp = _identity.start_stamp(leader.pid)
        assert stamp != _identity.UNKNOWN, "CONTROL failed: the leader's stamp was not readable"
        _plant_record(handle.jail_dir, leader.pid, leader.pid, stamp)
        _wait_for_members(leader.pid)
        leader.wait()  # reaped: the pid names nothing, the backgrounded sleep remains
        assert _live_members(leader.pid), "CONTROL failed: the group has no member left"
        assert _identity.start_stamp(leader.pid) == _identity.UNKNOWN

        report = handle.kill()

        assert _live_members(leader.pid) == [], f"the group outlived teardown ({report})"
        (item,) = [i for i in report.items if i.identity == str(leader.pid)]
        assert item.outcome is KillOutcome.ENDED, item
    finally:
        teardown_group(handle)
        subprocess.run(["/bin/kill", "-KILL", "--", f"-{leader.pid}"], check=False)
