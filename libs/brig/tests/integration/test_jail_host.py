"""`Jail` and `Process` over `HostRuntime` (decision-181, TASK-0079.26).

Each claim is observed from outside the code under test where a process is
concerned (`/bin/ps`, a second interpreter):

- a launch is `Jail.create` then `jail.start`, an exec sibling a second
  `start`, and `destroy` ends both (AC1);
- a jail rehydrated in another interpreter reads each process's record and
  exit record, a start made after `to_dict` included (AC2);
- `start` and `probe` are absent there while the creator holds the tether
  (AC7);
- when a record on disk disagrees with the one the holder knows, `destroy`
  ends the known identity and reports the disk copy as its own `FAILED` item,
  signalling nothing it names (AC8; seen failing with the item removed);
- a refused first start leaves the jail to its caller, and `destroy` ends
  the helpers `create` started (AC9; the launcher did this itself until
  decision-183);
- probes are processes the jail starts, each kept for `destroy` (AC4).
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable

import pytest

from brig.core import Axis, ProbeShape, Spec, Verdict, unenforced_report
from brig.core.probes import Battery as CoreBattery
from brig.core.probes import BatteryVerdict
from brig.mech import Helper, HelperLifetime
from brig.probe.battery import Battery, Expectation, Probe
from brig.run import (
    ExecFidelity,
    ExecWrapNotAPrefix,
    HostRuntime,
    Jail,
    KillOutcome,
    RuntimeKind,
    _identity,
    _records,
)
from brig.stack import CompiledJail
from tests.conftest import NewJailDir, teardown_pgid, workload_argv

pytestmark = pytest.mark.integration

_jail_counter = itertools.count()


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _appending_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Not a pure prefix: it appends, so `create` derives no prefix and every
    start is refused."""
    return (*argv, "--appended")


def _compiled(
    *,
    wrap: Callable[[tuple[str, ...]], tuple[str, ...]] = _identity_wrap,
    helpers: tuple[Helper, ...] = (),
) -> CompiledJail:
    return CompiledJail(
        spec=Spec(),
        report=unenforced_report(),
        wrap=wrap,
        env={},
        staged=(),
        helpers=helpers,
        requires=frozenset(),
        mechanism_names=(),
        matrix_version=1,
    )


def _ps() -> list[tuple[int, int, str, str]]:
    """Every process as (pid, pgid, state, args), from `/bin/ps` (alias-proof,
    decision-026), command lines untruncated."""
    table = subprocess.run(
        ["/bin/ps", "-ww", "-Ao", "pid=,pgid=,stat=,args="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = []
    for line in table.splitlines():
        if line.strip():
            pid, pgid, state, *args = line.split(None, 3)
            rows.append((int(pid), int(pgid), state, args[0] if args else ""))
    return rows


def _live_members(pgid: int) -> list[int]:
    return [pid for pid, group, state, _ in _ps() if group == pgid and not state.startswith("Z")]


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


def _create(jail_dir: str, *, tether: int | None = None) -> Jail:
    return Jail.create(
        _compiled(),
        runtime=HostRuntime(),
        cwd=jail_dir,
        jail_id="jail-host",
        jail_dir=jail_dir,
        tether=tether,
    )


_ELSEWHERE = """
import json, sys
from brig.run import HostRuntime, Jail, RuntimeKind
with open(sys.argv[1], encoding="utf-8") as f:
    jail = Jail.from_dict(json.load(f), runtimes={RuntimeKind.HOST: HostRuntime()})
processes = jail.processes()
print(json.dumps({
    "has_start": hasattr(jail, "start"),
    "has_probe": hasattr(jail, "probe"),
    "ids": [p.id for p in processes],
    "pids": [p.pid for p in processes],
    "has_wait": [hasattr(p, "wait") for p in processes],
    "statuses": [p.wait(5.0) for p in processes] if sys.argv[2] == "wait" else [],
}))
"""


def _elsewhere(jail: Jail, scratch: str, mode: str) -> dict[str, object]:
    """Rehydrate `jail` from its dict alone in a second interpreter and report
    what it sees (`mode` "wait" also waits for every process there)."""
    path = os.path.join(scratch, "jail.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jail.to_dict(), f)
    done = subprocess.run(
        [sys.executable, "-I", "-c", _ELSEWHERE, path, mode],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    result: dict[str, object] = json.loads(done.stdout)
    return result


@pytest.fixture
def scratch(new_jail_dir: NewJailDir) -> str:
    """A second directory beside the test's `jail_dir`: where the dict is written for another
    interpreter to read."""
    return new_jail_dir()


# ---------------------------------------------------------------------------
# AC1: create, then start; a sibling is a second start.
# ---------------------------------------------------------------------------


def test_a_launch_is_create_then_start_and_destroy_ends_both(run_id: str, jail_dir: str) -> None:
    jail = _create(jail_dir)
    assert jail.processes() == () and jail.alive() is False
    first = jail.start(workload_argv(run_id, "sleep 100"))
    groups = [first.pid]
    try:
        sibling = jail.start(["/bin/sh", "-c", "exit 3"])
        groups.append(sibling.pid)
        assert sibling.wait(timeout=10.0) == 3
        assert [p.id for p in jail.processes()] == [first.id, sibling.id]
        assert first.fidelity is ExecFidelity.PLAIN
        assert first.alive() and not sibling.alive() and jail.alive()
        assert _live_members(first.pid), "CONTROL failed: the first process never ran"

        report = jail.destroy()

        assert [(item.kind, item.identity, item.outcome) for item in report.items] == [
            ("workload_group", str(first.pid), KillOutcome.ENDED),
            ("exec_sibling", str(sibling.pid), KillOutcome.ALREADY_GONE),
        ]
        assert _live_members(first.pid) == []
    finally:
        for pgid in groups:
            _kill_group(pgid)


# ---------------------------------------------------------------------------
# AC2: rehydrated in another interpreter, every record and exit record read.
# ---------------------------------------------------------------------------


def test_a_jail_rehydrated_elsewhere_reads_each_record_and_exit_record(
    jail_dir: str, scratch: str
) -> None:
    jail = _create(jail_dir)
    three = jail.start(["/bin/sh", "-c", "exit 3"])
    five = jail.start(["/bin/sh", "-c", "exit 5"])
    assert (three.wait(timeout=10.0), five.wait(timeout=10.0)) == (3, 5)
    seen = _elsewhere(jail, scratch, "wait")
    assert seen["ids"] == [three.id, five.id]
    assert seen["statuses"] == [3, 5]

    # A start made after the dict was taken is a record on disk the dict does
    # not name: read like any other.
    path = os.path.join(scratch, "jail.json")
    with open(path, encoding="utf-8") as f:
        earlier = json.load(f)
    seven = jail.start(["/bin/sh", "-c", "exit 7"])
    assert seven.wait(timeout=10.0) == 7
    later = Jail.from_dict(earlier, runtimes={RuntimeKind.HOST: HostRuntime()})
    assert [p.id for p in later.processes()] == [three.id, five.id, seven.id]
    assert jail.destroy().items[-1].outcome is KillOutcome.ALREADY_GONE


# ---------------------------------------------------------------------------
# AC7: start absent where the creator holds the tether.
# ---------------------------------------------------------------------------


def test_start_is_absent_on_a_tethered_jail_rehydrated_elsewhere(
    run_id: str, jail_dir: str, scratch: str
) -> None:
    """In the creating process the tethered jail starts; in another
    interpreter, rehydrated from its dict, it has no `start` and no `probe`,
    while its process can still be waited for. The control: an untethered
    jail rehydrated the same way has a `start`."""
    read_end, write_end = os.pipe()
    jail = _create(jail_dir, tether=read_end)
    os.close(read_end)
    groups: list[int] = []
    try:
        assert hasattr(jail, "start")
        process = jail.start(workload_argv(run_id, "sleep 100"))
        groups.append(process.pid)

        seen = _elsewhere(jail, scratch, "look")
        assert seen["has_start"] is False and seen["has_probe"] is False
        assert seen["ids"] == [process.id] and seen["has_wait"] == [True]
        assert _live_members(process.pid), "the rehydration ended the process"

        untethered = _create(f"{jail_dir}u")
        try:
            assert _elsewhere(untethered, scratch, "look")["has_start"] is True
        finally:
            shutil.rmtree(f"{jail_dir}u", ignore_errors=True)
    finally:
        os.close(write_end)
        for pgid in groups:
            _kill_group(pgid)


def test_a_hand_edited_dict_does_not_give_a_tethered_jail_its_start_back(
    run_id: str, jail_dir: str, scratch: str
) -> None:
    """Review 1 of TASK-0079.26. A tethered jail's dict hand-edited to say
    untethered is rehydrated in a second interpreter: `start` and `probe`
    stay absent, because `<jail_dir>/jail.json`, which `create` wrote, says
    tethered. So is a jail whose `jail.json` is gone. The control: the honest
    untethered jail starts there.

    Planted on 2026-10-12 (scratch copy of `jail.py`, sha256-restored): with
    `_cannot_start` reading the dict alone, the edited jail had `start`."""
    read_end, write_end = os.pipe()
    tethered = _create(jail_dir, tether=read_end)
    os.close(read_end)
    groups: list[int] = []
    try:
        process = tethered.start(workload_argv(run_id, "sleep 100"))
        groups.append(process.pid)
        edited = {**tethered.to_dict(), "tethered": False}
        path = os.path.join(scratch, "jail.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(edited, f)
        done = subprocess.run(
            [sys.executable, "-I", "-c", _ELSEWHERE, path, "look"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        seen = json.loads(done.stdout)
        assert seen["has_start"] is False and seen["has_probe"] is False

        untethered = _create(f"{jail_dir}u")
        try:
            assert _elsewhere(untethered, scratch, "look")["has_start"] is True
            os.unlink(os.path.join(f"{jail_dir}u", _records.JAIL_RECORD_FILENAME))
            assert _elsewhere(untethered, scratch, "look")["has_start"] is False
        finally:
            shutil.rmtree(f"{jail_dir}u", ignore_errors=True)
    finally:
        os.close(write_end)
        for pgid in groups:
            _kill_group(pgid)


# ---------------------------------------------------------------------------
# AC8: a disk record that disagrees with the one the holder knows.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("holder", ["creator", "rehydrated"])
def test_a_disagreeing_disk_record_is_its_own_failed_item_and_the_known_process_ends(
    run_id: str, jail_dir: str, holder: str
) -> None:
    """The jail starts P; a decoy D runs in a group of its own. P's
    `record.json` is then rewritten on disk to name D (the shape a forged
    record has where nothing seals the jail directory). `destroy` must still
    end P, by the identity the holder knows, leave D alone, and report the disk
    copy as its own FAILED item whose identity is the file's path.

    Planted on 2026-10-12 (scratch copy of `teardown.py`, sha256-restored):
    with the disagreeing item removed from `kill_named`, both parametrizations
    failed (no item for the record's path); with the disk copy used in place
    of the known record, both failed too (no item for P: the ladder ran
    against D's group).
    """
    jail = _create(jail_dir)
    process = jail.start(workload_argv(run_id, "sleep 100"))
    decoy = subprocess.Popen(workload_argv(run_id, "sleep 100"), start_new_session=True)
    groups = [process.pid, decoy.pid]
    try:
        holding = (
            jail
            if holder == "creator"
            else Jail.from_dict(jail.to_dict(), runtimes={RuntimeKind.HOST: HostRuntime()})
        )
        path = os.path.join(_records.process_dir(jail_dir, process.id), _records.RECORD_FILENAME)
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        on_disk.update(pid=decoy.pid, pgid=decoy.pid, start_time=_identity.start_stamp(decoy.pid))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(on_disk, f)
        assert _live_members(process.pid) and _live_members(decoy.pid), "CONTROL failed"
        assert [p.pid for p in holding.processes()] == [process.pid]

        report = holding.destroy()

        by_identity = {item.identity: item for item in report.items}
        assert by_identity[str(process.pid)].outcome is KillOutcome.ENDED, report
        assert _live_members(process.pid) == [], "the known process was not ended"
        assert _live_members(decoy.pid), "the disk copy's process was signalled"
        disagreeing = by_identity[path]
        assert disagreeing.outcome is KillOutcome.FAILED, report
        assert disagreeing.kind == "workload_group", "the first process's copy, by its kind"
        assert "disagrees" in disagreeing.detail and str(decoy.pid) in disagreeing.detail
        assert str(decoy.pid) not in by_identity
    finally:
        for pgid in groups:
            _kill_group(pgid)
        decoy.wait(timeout=10.0)


# ---------------------------------------------------------------------------
# AC9: a refused first start leaves the jail to its caller, and destroy ends
# what create started.
# ---------------------------------------------------------------------------


def _helper_groups(marker: str) -> list[int]:
    return sorted(
        {pgid for _, pgid, state, args in _ps() if marker in args and not state.startswith("Z")}
    )


@pytest.mark.parametrize("wrap", [_appending_wrap, _identity_wrap], ids=["refused", "control"])
def test_a_refused_first_start_leaves_the_jail_whose_destroy_ends_its_helpers(
    run_id: str, jail_dir: str, wrap: Callable[[tuple[str, ...]], tuple[str, ...]]
) -> None:
    """A jail with a `JAIL_LIFETIME` helper and a wrap that is not a pure
    prefix: `create` starts the helper, then the first start is refused
    (`ExecWrapNotAPrefix`). A refused start changes nothing (TASK-0079.26's
    settled point 6): the helper still runs and the jail is the caller's, and
    its `destroy` ends the helper even though no process ever started. The
    control: the same helper with a prefix wrap, whose first start succeeds.

    Until decision-183 the launcher destroyed the jail itself when its first
    start was refused (planted 2026-10-12: with that `destroy` removed, the
    helper outlived the refused launch). With the launcher gone that is the
    embedder's to do -- bh-02's runner does it, as `tests.conftest.launch`
    does -- and what brig guarantees is what this test holds: `destroy` on a
    jail with nothing started still ends its helpers."""
    marker = f"t26helper{run_id[:8]}{next(_jail_counter)}"
    helper = Helper(
        name="keeper",
        argv=tuple(workload_argv(run_id, f": {marker}; sleep 100")),
        lifetime=HelperLifetime.JAIL_LIFETIME,
    )
    groups: list[int] = []
    try:
        jail = Jail.create(
            _compiled(wrap=wrap, helpers=(helper,)),
            runtime=HostRuntime(),
            cwd=jail_dir,
            jail_id="jail-refused-first",
            jail_dir=jail_dir,
        )
        assert _wait_for(lambda: bool(_helper_groups(marker)), 5.0), "the helper never ran"
        if wrap is _appending_wrap:
            with pytest.raises(ExecWrapNotAPrefix):
                jail.start(workload_argv(run_id, "sleep 100"))
            assert _helper_groups(marker), "a refused start ended the helper: it changed something"
            assert jail.processes() == ()
        else:
            process = jail.start(workload_argv(run_id, "sleep 100"))
            groups.append(process._record.pgid)
        report = jail.destroy()
        assert _wait_for(lambda: not _helper_groups(marker), 5.0), (
            f"the helper outlived its jail's destroy: groups {_helper_groups(marker)}"
        )
        assert [item.kind for item in report.items][-1] == "helper", report
    finally:
        groups.extend(_helper_groups(marker))
        for pgid in groups:
            _kill_group(pgid)


# ---------------------------------------------------------------------------
# AC4: probes are processes the jail starts.
# ---------------------------------------------------------------------------


def test_a_probe_is_a_process_the_jail_starts_and_destroy_ends(jail_dir: str) -> None:
    battery = Battery(
        name="t26-probes-are-starts",
        axis=Axis.ENV,
        probes=(
            Probe(
                name="control",
                shape=ProbeShape.CONTROL,
                axis=Axis.ENV,
                argv=("/bin/sh", "-c", "echo t26ctrl"),
                expect=Expectation(token="t26ctrl"),
            ),
            Probe(
                name="absent",
                shape=ProbeShape.ABSENCE,
                axis=Axis.ENV,
                argv=("/bin/sh", "-c", "echo nothing-here"),
                expect=Expectation(token="t26secret"),
            ),
        ),
    )
    jail = _create(jail_dir)
    assert hasattr(jail, "probe")

    report = jail.probe(_cast_battery(battery))

    assert report.battery_verdict is BatteryVerdict.CONSISTENT, report
    assert [o.verdict for o in report.outcomes] == [Verdict.PASS, Verdict.PASS]
    processes = jail.processes()
    assert [p.argv for p in processes] == [probe.argv for probe in battery.probes]
    for process in processes:
        with open(process.stdout_path, encoding="utf-8") as f:
            assert f.read() in {"t26ctrl\n", "nothing-here\n"}
    items = jail.destroy().items
    assert [(item.identity, item.outcome) for item in items] == [
        (str(p.pid), KillOutcome.ALREADY_GONE) for p in processes
    ]


def _cast_battery(battery: Battery) -> CoreBattery:
    """A frozen `Battery` is a `core.probes.Battery` at runtime; mypy reads its
    fields as read-only and can't see it (`test_probe_runner.py`'s `_probe`)."""
    assert isinstance(battery, CoreBattery)
    return battery
