"""The pure half of per-process records (decision-181, TASK-0079.25).

`brig/run/_records.py`'s reading and judging of a record, the stdio names a
process may not take, and the sentinel `create` derives `wrap_prefix` from.
No I/O: what reads the host is the integration tier's (`test_host_records.py`).
"""

from __future__ import annotations

import json

import pytest

from brig.core.runtime import PROCS_DIRNAME, channel_dir
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
        "channel": None,
        "bound_path": None,
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
        # decision-184: a channel and its socket come together, or not at all.
        (_raw(channel="ctl"), "'channel' and 'bound_path'"),
        (_raw(bound_path=f"{_JAIL}/chan/x.sock"), "'channel' and 'bound_path'"),
        (_raw(channel="", bound_path=""), "'channel' and 'bound_path'"),
        (_raw(channel="ctl", bound_path=5), "'channel' and 'bound_path'"),
    ],
)
def test_what_is_not_a_record_brig_wrote_is_named(text: str, reason: str) -> None:
    parsed = _records.parse(text, _ID)
    assert isinstance(parsed, str) and reason in parsed, parsed


@pytest.mark.unit
def test_a_record_carries_its_channel_and_the_socket_it_binds() -> None:
    """decision-184: `channel` and `bound_path` read back as written."""
    socket_path = f"{_JAIL}/chan/0123456789abcdef.sock"
    record = _record(channel="ctl", bound_path=socket_path)
    assert (record.channel, record.bound_path) == ("ctl", socket_path)
    assert _records.from_json(_records.to_json(record), _ID) == record


@pytest.mark.unit
def test_an_id_is_sixteen_lowercase_hex_and_nothing_traverses() -> None:
    """Decided for TASK-0079.25 (point 4)."""
    assert _records.is_id(_records.new_id())
    assert _records.is_id(_ID)
    for name in ("", "..", "../etc", "0123456789ABCDEF", "0123456789abcde", f"{_ID}0", f"{_ID}/"):
        assert not _records.is_id(name), name
    with pytest.raises(ValueError, match="not a process id"):
        _records.process_dir(_JAIL, "../x")


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
def test_the_channel_directory_is_a_sibling_of_the_records() -> None:
    """decision-181, restated by decision-186: a channel's one grant is the
    channel directory, so no grant reaches the records only while the two are
    siblings in the jail directory, neither at, under or above the other, and
    neither the jail directory itself. Pure: the names brig keeps."""

    def at_or_under(path: str, root: str) -> bool:
        return path == root or path.startswith(root + "/")

    for jail in (_JAIL, f"{_JAIL}/"):
        chan = channel_dir(jail)
        records = f"{jail.rstrip('/')}/{PROCS_DIRNAME}"
        assert chan.rsplit("/", 1)[0] == records.rsplit("/", 1)[0] == jail.rstrip("/")
        assert not at_or_under(chan, records) and not at_or_under(records, chan)
        assert chan != jail.rstrip("/")


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


@pytest.mark.unit
def test_a_disk_copy_disagrees_on_any_field_but_order() -> None:
    """decision-181, TASK-0079.26's settled point 3: `order` only sorts (a
    `Jail` names its first process with 0), every other field is identity."""
    held = _record()
    assert not _records.disagrees(held, _record(order=0))
    for change in ({"pid": 101}, {"pgid": 101}, {"start_time": "x"}, {"argv": ["sh"]}):
        assert _records.disagrees(held, _record(**change)), change


@pytest.mark.unit
def test_a_record_round_trips_through_json_data() -> None:
    held = _record()
    assert _records.from_json(_records.to_json(held), _ID) == held
    assert _records.from_json([], _ID) == "holds a JSON list, not an object"
