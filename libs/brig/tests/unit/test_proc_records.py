"""The pure half of per-process records (decision-181, TASK-0079.25).

`brig/run/_records.py`'s reading and judging of a record, the stdio names a
process may not take, and the sentinel `create` derives `wrap_prefix` from.
No I/O: what reads the host is the integration tier's (`test_host_records.py`).
"""

from __future__ import annotations

import json

import pytest

from brig.core.runtime import ChannelOnRecords, refuse_channel_on_records
from brig.run import _records
from brig.run._identity import UNKNOWN
from brig.run.host import _WRAP_SENTINEL, _chosen_status, _derive_wrap_prefix
from brig.run.runtime import IoPolicy

_ID = "0123456789abcdef"
_JAIL = "/run/brig/jail0"


def _raw(**fields: object) -> str:
    base: dict[str, object] = {
        "id": _ID,
        "order": 7,
        "pid": 100,
        "pgid": 100,
        "start_time": "linux-starttime:5",
        "argv": ["sleep", "1"],
        "stdout_path": f"{_JAIL}/procs/{_ID}/stdout.log",
        "stderr_path": f"{_JAIL}/procs/{_ID}/stderr.log",
    }
    base.update(fields)
    return json.dumps(base)


def _record(**fields: object) -> _records.ProcessRecord:
    parsed = _records.parse(_raw(**fields), _ID)
    assert isinstance(parsed, _records.ProcessRecord), parsed
    return parsed


@pytest.mark.unit
def test_a_record_reads_back_as_written() -> None:
    record = _record()
    assert record == _records.ProcessRecord(
        id=_ID,
        order=7,
        pid=100,
        pgid=100,
        start_time="linux-starttime:5",
        argv=("sleep", "1"),
        stdout_path=f"{_JAIL}/procs/{_ID}/stdout.log",
        stderr_path=f"{_JAIL}/procs/{_ID}/stderr.log",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("{ not json", "is not JSON"),
        ("[1]", "not an object"),
        ('{"id": "0123456789abcdef"}', "missing key"),
        (_raw(extra=1), "unknown key"),
        (_raw(id="fedcba9876543210"), "not its directory's"),
        (_raw(pgid=0), "'pid'/'pgid'"),
        (_raw(pgid=1), "'pid'/'pgid'"),
        (_raw(pid=2**31), "'pid'/'pgid'"),
        (_raw(pid=True), "'pid'/'pgid'"),
        (_raw(order=-1), "'order'"),
        (_raw(start_time=5), "must be strs"),
        (_raw(argv="sleep"), "'argv'"),
    ],
)
def test_what_is_not_a_record_brig_wrote_is_named(text: str, reason: str) -> None:
    parsed = _records.parse(text, _ID)
    assert isinstance(parsed, str) and reason in parsed, parsed


@pytest.mark.unit
def test_an_id_is_sixteen_lowercase_hex_and_nothing_traverses() -> None:
    """Decided for TASK-0079.25 (point 4)."""
    assert _records.is_id(_records.new_id())
    assert _records.is_id(_ID)
    for name in ("", "..", "../etc", "0123456789ABCDEF", "0123456789abcde", f"{_ID}0", f"{_ID}/"):
        assert not _records.is_id(name), name
    with pytest.raises(ValueError, match="not a process id"):
        _records.process_dir(_JAIL, "../x")
    assert _records.id_of(_JAIL, f"{_JAIL}/procs/{_ID}/stdout.log") == _ID
    assert _records.id_of(_JAIL, f"{_JAIL}/stdout.log") is None
    assert _records.id_of(_JAIL, f"{_JAIL}/procs/../stdout.log") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stamp", "now", "zombie", "group_live", "expected"),
    [
        # The leader holds its identity: it runs, whatever the table says.
        ("s1", "s1", False, False, _records.Standing.RUNS),
        # The leader's pid names another process: a recycled leader means an
        # empty group, so nothing holds, even with a live group of that number.
        ("s1", "s2", False, True, _records.Standing.GONE),
        # The leader is gone (or a zombie): it runs while its group has a member.
        ("s1", UNKNOWN, False, True, _records.Standing.RUNS),
        ("s1", UNKNOWN, False, False, _records.Standing.GONE),
        ("s1", "s1", True, True, _records.Standing.RUNS),
        ("s1", "s1", True, False, _records.Standing.GONE),
        # No stamp: nothing shows it is gone.
        (UNKNOWN, UNKNOWN, False, False, _records.Standing.UNKNOWN_STAMP),
    ],
)
def test_standing_reads_the_stamp_before_the_group(
    stamp: str, now: str, zombie: bool, group_live: bool, expected: _records.Standing
) -> None:
    record = _record(start_time=stamp)
    assert (
        _records.standing(record, current_stamp=now, leader_zombie=zombie, group_live=group_live)
        is expected
    )


@pytest.mark.unit
def test_every_doubt_holds_the_directory() -> None:
    gone = _record()
    other_id = "fedcba9876543210"
    no_stamp = _records.parse(_raw(id=other_id, start_time=""), other_id)
    assert isinstance(no_stamp, _records.ProcessRecord)
    unreadable = _records.Unreadable(f"{_JAIL}/procs/x", "is not named by a process id brig makes")
    scanned = _records.Scan((gone, no_stamp), (unreadable,))

    held = _records.held_by(_JAIL, scanned, stamps={}, zombies=frozenset(), live_groups=frozenset())
    assert [item.path for item in held] == [unreadable.path, f"{_JAIL}/procs/{other_id}"]
    assert "no start time" in held[1].reason

    table_unreadable = _records.held_by(
        _JAIL, _records.Scan((gone,), ()), stamps={}, zombies=frozenset(), live_groups=None
    )
    assert len(table_unreadable) == 1 and "can't be read" in table_unreadable[0].reason

    # The control: a gone record alone holds nothing.
    assert (
        _records.held_by(
            _JAIL,
            _records.Scan((gone,), ()),
            stamps={},
            zombies=frozenset(),
            live_groups=frozenset(),
        )
        == ()
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "name", ["record.json", "exit", "exit.partial", "record.json.partial", "a/b", "..", ""]
)
def test_stdio_may_not_take_a_records_name_or_leave_its_directory(name: str) -> None:
    with pytest.raises(ValueError, match="not a stdio file name"):
        IoPolicy(stdout_name=name)
    with pytest.raises(ValueError, match="name two files"):
        IoPolicy(stdout_name="out", stderr_name="out")
    IoPolicy(stdout_name="out.log", stderr_name="err.log")


@pytest.mark.unit
def test_the_records_refusal_reads_both_forms_of_the_endpoint() -> None:
    def refused(endpoint: str, resolved: str) -> bool:
        try:
            refuse_channel_on_records(
                name="ctl", endpoint=endpoint, resolved_endpoint=resolved, jail_dir=_JAIL
            )
        except ChannelOnRecords:
            return True
        return False

    assert refused(f"{_JAIL}/procs/k.sock", f"{_JAIL}/procs/k.sock")
    assert refused(f"{_JAIL}/procs", f"{_JAIL}/procs")
    assert refused(f"{_JAIL}/execs/a/k.sock", f"{_JAIL}/execs/a/k.sock")
    assert refused(f"{_JAIL}/chan/k.sock", f"{_JAIL}/procs/k.sock")
    assert refused(f"{_JAIL}/procs/k.sock", "/elsewhere/k.sock")
    # Controls: a directory of its own, a name that only starts like `procs`,
    # and a socket outside the jail directory.
    assert not refused(f"{_JAIL}/chan/k.sock", f"{_JAIL}/chan/k.sock")
    assert not refused(f"{_JAIL}/procs2/k.sock", f"{_JAIL}/procs2/k.sock")
    assert not refused("/elsewhere/k.sock", "/elsewhere/k.sock")


@pytest.mark.unit
def test_the_wrap_sentinel_is_no_real_argv_and_a_rewriting_wrap_derives_no_prefix() -> None:
    """Decided for TASK-0079.25 (point 1): every sentinel token holds a NUL,
    which no argv `execve` takes can; a prefixing wrap derives its prefix from
    it, and a wrap that rewrites any argument derives none."""
    assert len(_WRAP_SENTINEL) == 2 and all("\x00" in token for token in _WRAP_SENTINEL)
    prefix = ("/usr/bin/env", "-i")
    assert _derive_wrap_prefix((*prefix, *_WRAP_SENTINEL), _WRAP_SENTINEL) == prefix
    first, second = _WRAP_SENTINEL
    assert _derive_wrap_prefix((*prefix, first.upper(), second), _WRAP_SENTINEL) is None
    assert _derive_wrap_prefix((*prefix, first, second, "--tail"), _WRAP_SENTINEL) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("waited", "recorded", "expected"),
    [(0, 0, 0), (-9, 7, 7), (-9, None, -9), (3, None, 3)],
)
def test_a_recorded_exit_wins_over_the_waiters_status(
    waited: int, recorded: int | None, expected: int
) -> None:
    """decision-182: the exit record is the workload's status; the waiter's is
    the wrapper's, used only where nothing was recorded."""
    assert _chosen_status(waited, recorded) == expected


@pytest.mark.unit
def test_jail_dir_in_use_names_the_pid_and_group_it_holds() -> None:
    record = _records.ProcessRecord(
        id="0123456789abcdef",
        order=1,
        pid=4242,
        pgid=4242,
        start_time="stamp",
        argv=("x",),
        stdout_path="o",
        stderr_path="e",
    )
    scanned = _records.Scan(records=(record,), unreadable=())
    held = _records.held_by(
        "/jail", scanned, stamps={4242: "stamp"}, zombies=frozenset(), live_groups=frozenset({4242})
    )
    assert "pid 4242" in held[0].reason
    assert "process group 4242" in held[0].reason
    assert "wait a moment and retry" in str(_records.JailDirInUse("/jail", held))
