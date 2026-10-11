"""Teardown is total (TASK-0079.14, decision-175).

An exec registration brig cannot read (not JSON, a missing key, a wrong type)
used to make `_execs.live` raise, so `kill_jail` stopped after the workload
group and left every exec sibling and every helper running. Now the file is its
own `FAILED` item, saying which file and what to do, and every other item is
torn down.

The plant is made from the HOST side, as a file written beside the genuine
registrations: no jail can write its `jail_dir` any more (decision-173,
decision-174), so what produces such a file is tampering on the host or a
broken disk. Every observation of a process goes through `/bin/ps`, never
through the module under test, and a genuine sibling registered BEFORE the plant
is the control: it must be `ENDED`, so a surviving process is the bug and not a
teardown that ran nothing.

The last test is the other half of the story: a genuine registration whose
leader was reaped, with its group still holding a live member, is still ended.
"""

import dataclasses
import itertools
import os
import subprocess
import time

import pytest

from brig.core import Spec
from brig.run import IoPolicy, SubprocessLauncher, _execs, _identity
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


_UNREADABLE = {
    "not-json": b"{ this is not json",
    "empty": b"",
    "not-utf8": b"\xff\xfe\x00",
    "not-an-object": b"[1, 2, 3]",
    "missing-keys": b'{"pid": 1}',
    "wrong-types": b'{"pid": "1", "pgid": 1, "start_time": ""}',
    "stamp-not-str": b'{"pid": 1, "pgid": 1, "start_time": 5}',
    "absurd-pid": b'{"pid": 1180591620717411303424, "pgid": 7, "start_time": "x"}',
    "absurd-pgid": b'{"pid": 5, "pgid": 1180591620717411303424, "start_time": "x"}',
    "pgid-zero": b'{"pid": 5, "pgid": 0, "start_time": "x"}',
    "pgid-one": b'{"pid": 5, "pgid": 1, "start_time": "x"}',
    "pgid-negative": b'{"pid": 5, "pgid": -5, "start_time": "x"}',
    "pgid-past-pid-max": b'{"pid": 5, "pgid": 2147483648, "start_time": "x"}',
}


@pytest.mark.parametrize("content", _UNREADABLE.values(), ids=_UNREADABLE.keys())
def test_an_unreadable_registration_is_its_own_failed_item_and_the_rest_is_torn_down(
    run_id: str, content: bytes
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

        plant = os.path.join(_execs.execs_dir(handle.jail_dir), "99999.json")
        with open(plant, "wb") as record:
            record.write(content)

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
    finally:
        teardown_group(handle)
        subprocess.run(["/bin/kill", "-KILL", "--", f"-{helper.pid}"], check=False)
        helper.wait()


def test_a_record_naming_the_trusted_process_s_own_group_is_refused_and_nothing_is_signalled(
    run_id: str,
) -> None:
    """A registration naming the group pytest itself runs in (a genuine-looking
    one: in range, a stamp present) must not be signalled, and neither must a
    workload group of 0, which `killpg` reads as the caller's own."""
    handle = _launch(run_id)
    own = os.getpgrp()
    try:
        _wait_for_members(handle.pgid)
        _execs.register(handle.jail_dir, os.getpid(), own, _identity.start_stamp(os.getpid()))
        zero = dataclasses.replace(handle, pgid=0)

        report = handle.kill()
        zero_report = zero.kill()

        assert os.getpgrp() == own  # reaching here: pytest was not signalled
        (own_item,) = [i for i in report.items if i.identity == str(own)]
        assert own_item.outcome is KillOutcome.FAILED, own_item
        assert "nothing was signalled" in own_item.detail, own_item.detail
        assert report.items[0].outcome is KillOutcome.ENDED, report
        (zero_item,) = [i for i in zero_report.items if i.kind == "workload_group"]
        assert zero_item.outcome is KillOutcome.FAILED, zero_item
        assert "nothing was signalled" in zero_item.detail, zero_item.detail
    finally:
        teardown_group(handle)


def test_an_exception_from_one_item_is_that_item_s_failure_and_stops_no_other(
    run_id: str,
) -> None:
    """A helper whose pid the OS rejects (`waitpid` raises `OverflowError`) is
    its own `FAILED` item, and the genuine sibling after the workload is still
    ended."""
    handle = _launch(run_id)
    sibling = exec_in_jail(handle, workload_argv(run_id, "sleep 100"))
    handle = dataclasses.replace(handle, helper_pids=(2**70,), helper_stamps=("x",))
    try:
        _wait_for_members(sibling.pid)
        report = handle.kill()  # must not raise

        assert _live_members(sibling.pid) == [], report
        (bad,) = [i for i in report.items if i.kind == "helper"]
        assert bad.outcome is KillOutcome.FAILED, bad
        assert "OverflowError" in bad.detail, bad.detail
    finally:
        teardown_group(handle)


def test_teardown_still_ends_the_group_of_a_genuine_registration_whose_leader_was_reaped(
    run_id: str,
) -> None:
    """The leader exits and is reaped, so its pid names nothing; a member of its
    group lives on. The registration is genuine (a real stamp taken while the
    leader lived), so the ladder signals the group and ends it."""
    handle = _launch(run_id)
    body = f": {run_id}; sleep 100 & sleep 1"
    leader = subprocess.Popen(["/bin/bash", "-c", body], start_new_session=True)
    try:
        stamp = _identity.start_stamp(leader.pid)
        assert stamp != _identity.UNKNOWN, "CONTROL failed: the leader's stamp was not readable"
        _execs.register(handle.jail_dir, leader.pid, leader.pid, stamp)
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
