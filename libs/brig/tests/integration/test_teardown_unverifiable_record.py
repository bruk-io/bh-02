"""A record brig cannot verify is not kill authority (TASK-0078, decision-172).

Process records are files under `<jail_dir>/procs/<id>/` (decision-181; a registration file
per exec sibling before it), and a stack with no
`fs_write` mechanism leaves the `jail_dir` writable from inside the jail. A
record whose start-time stamp is empty (`_identity.UNKNOWN`) names a pid
and a pgid with nothing to show either is the jail's, and before decision-172
teardown ran the ladder against it anyway: `recycled()` reads an empty stamp as
"not recycled", so a forged registration could aim `SIGTERM` and `SIGKILL` at
any group the trusted process may signal.

The plant here is exactly that forgery: a decoy process group that is not the
jail's, started by the test in a session of its own, and a registration that
names it with an empty stamp, written as a file the way a jail that can write
its `jail_dir` would write it, never through brig's own `write`.

Every observation of the decoy goes through `/bin/ps`, never through the module
under test, and the control is in the same test: the same `kill()` ends the
jail's own workload group (`ENDED`), so a decoy that survives is the refusal
and not a teardown that ran nothing.
"""

import json
import os
import subprocess
import time

import pytest

from brig.core import Spec
from brig.run import IoPolicy
from brig.run.teardown import KillOutcome
from brig.stack import Stack
from tests.conftest import launch, teardown_group, teardown_pgid, workload_argv

pytestmark = pytest.mark.integration


def _live_members(pgid: int) -> list[int]:
    """Every non-zombie pid in `pgid`, per a fresh `/bin/ps` scan (alias-proof
    per decision-026), made without the code under test."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid=,stat="], capture_output=True, text=True, check=True
    )
    return [
        int(parts[0])
        for parts in (line.split() for line in proc.stdout.splitlines())
        if len(parts) == 3 and int(parts[1]) == pgid and not parts[2].startswith("Z")
    ]


def _wait_for_members(pgid: int, timeout: float = 30.0) -> None:
    """Block until `pgid` has a live member: a START wait, so the controls
    below have something there to observe."""
    deadline = time.monotonic() + timeout
    while not _live_members(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)


def _forge_registration(jail_dir: str, pid: int, pgid: int) -> None:
    """Write `<jail_dir>/procs/<id>/record.json` with an empty stamp, as a jail
    that can write its own `jail_dir` could, by hand rather than through brig."""
    process_id = "f0f0f0f0f0f0f0f0"
    directory = os.path.join(jail_dir, "procs", process_id)
    os.makedirs(directory)
    with open(os.path.join(directory, "record.json"), "w", encoding="utf-8") as record:
        json.dump(
            {
                "id": process_id,
                "order": time.time_ns(),
                "pid": pid,
                "pgid": pgid,
                "start_time": "",
                "argv": [],
                "stdout_path": "",
                "stderr_path": "",
                "channel": None,
                "bound_path": None,
                "namespaces": False,
            },
            record,
        )


def test_kill_signals_no_group_a_record_with_an_empty_stamp_names(
    run_id: str, jail_dir: str
) -> None:
    """The decoy group survives the jail's `kill()`, the forged item reports
    `FAILED` with a detail saying nothing was signalled and why, and the same
    `kill()` ends the jail's own workload group (the control)."""
    jail, process = launch(
        Stack([]).compile(Spec()),
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"unverifiable-{os.path.basename(jail_dir)}",
        jail_dir=jail_dir,
    )
    decoy = subprocess.Popen(workload_argv(run_id, "sleep 100"), start_new_session=True)

    try:
        _wait_for_members(process._record.pgid)
        _wait_for_members(decoy.pid)
        assert _live_members(process._record.pgid), "CONTROL failed: the jail's group is empty"
        before = _live_members(decoy.pid)
        assert before, "CONTROL failed: the decoy group is empty"

        _forge_registration(jail_dir, decoy.pid, decoy.pid)
        report = jail.destroy()

        assert set(before) <= set(_live_members(decoy.pid)), (
            f"a member of the decoy group is gone: teardown signalled a group named by a "
            f"record whose identity it could not verify ({report})"
        )
        assert report.items[0].kind == "workload_group"
        assert report.items[0].outcome is KillOutcome.ENDED, report
        (forged,) = [item for item in report.items if item.kind == "exec_sibling"]
        assert forged.identity == str(decoy.pid)
        assert forged.outcome is KillOutcome.FAILED, forged
        assert "no start time" in forged.detail and "nothing was signalled" in forged.detail, (
            forged.detail
        )
    finally:
        teardown_pgid(decoy.pid, wait=decoy.wait)
        teardown_group(process)


def test_a_record_with_an_empty_stamp_whose_group_has_ended_reads_already_gone(
    run_id: str,
    jail_dir: str,
) -> None:
    """An unverifiable record naming a group with no live member is not a
    failure: nothing of it runs, so `ALREADY_GONE`, and nothing is signalled
    either way."""
    jail, process = launch(
        Stack([]).compile(Spec()),
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"unverifiable-{os.path.basename(jail_dir)}",
        jail_dir=jail_dir,
    )
    ended = subprocess.Popen(["/usr/bin/true"], start_new_session=True)
    ended.wait()
    try:
        _wait_for_members(process._record.pgid)
        assert not _live_members(ended.pid), "CONTROL failed: the ended group still runs"
        _forge_registration(jail_dir, ended.pid, ended.pid)

        report = jail.destroy()

        (forged,) = [item for item in report.items if item.kind == "exec_sibling"]
        assert forged.outcome is KillOutcome.ALREADY_GONE, forged
        assert report.items[0].outcome is KillOutcome.ENDED, report
    finally:
        teardown_group(process)
