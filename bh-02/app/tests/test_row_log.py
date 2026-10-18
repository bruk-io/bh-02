"""A session's `rows.jsonl`: a line that marks each run's start, then the lifecycle events that count,
queued from the event loop to a thread and kept at 0600, for `bh-02 trajectory` to lay out
(decision-0009, Row reloads)."""

import asyncio
import datetime
import errno
import json
import os
import re
import stat
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from bh_02 import layers, run
from bh_02.bootstrap import NotStarted
from bh_02.trajectory import rendered, trajectory
from cordis import Row

type Record = dict[str, str]

# UTC to the millisecond with a Z, as the transcript's `at` is, so it sorts as text
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z")
CHAT = Row("chat", config={"prompt": "hi"})


@pytest.fixture
def open_umask() -> Iterator[None]:
    """A umask that takes nothing away, so the mode a file has is the mode it was made with."""
    before = os.umask(0)
    try:
        yield
    finally:
        os.umask(before)


def records(log: Path) -> list[Record]:
    return [json.loads(line) for line in log.read_text().splitlines()]


def rows_of(log: Path) -> list[Record]:
    """The lines of one run's `rows.jsonl` after the line that marks its start, which is the first."""
    marker, *kept = records(log)
    assert set(marker) == {"at", "kind"} and marker["kind"] == "run" and STAMP.fullmatch(marker["at"])
    assert all(record["kind"] != "run" for record in kept)
    return kept


def patch(composition: Callable[..., Path], more: str = "") -> Path:
    return composition('[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n' + more, one_reply=True)


@pytest.mark.usefixtures("open_umask")
async def test_each_reload_is_a_line_with_its_time_kind_and_row_in_a_file_for_its_owner_alone(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    log, heard = tmp_path / "rows.jsonl", []
    await asyncio.wait_for(run([*layers(), patch(composition)], [CHAT], trace=heard.append, row_log=log), 10)
    kept = rows_of(log)
    assert stat.S_IMODE(log.stat().st_mode) == 0o600  # under a umask that takes nothing away
    assert all(set(record) == {"at", "kind", "row"} and STAMP.fullmatch(record["at"]) for record in kept)
    assert [record["at"] for record in records(log)] == sorted(record["at"] for record in records(log))
    # only the events that count: a row's setup beginning, or failing; not bind, active, unloading, ...
    assert {record["kind"] for record in kept} == {"reload"}
    assert {"loop", "transcript", "chat", "python", "host", "session"} <= {record["row"] for record in kept}
    # the same events `--trace` hears, which is as it was: a line each, whatever the row log keeps
    traced = [line.split("#")[0].removeprefix("reload ") for line in heard if line.startswith("reload ")]
    assert sorted(record["row"] for record in kept) == sorted(traced)
    assert any(line.startswith("active chat#") for line in heard)
    assert any(line.startswith("bind ") for line in heard) and any(
        line.startswith("unbind ") for line in heard
    )


async def test_a_row_restarted_by_a_command_is_kept_as_the_reload_of_its_new_fiber(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """cordis emits no `restart`: the old fiber is `unloading` then `inactive`, and the new one begins
    with a `reload`, which is what /clear leaves of the rows it restarts."""
    import fragile

    log = tmp_path / "rows.jsonl"
    fragile.script("/clear", "after")
    ui = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:scripted_ui"\n'
    )
    await asyncio.wait_for(run([*layers(), ui], row_log=log), 10)
    kept = rows_of(log)
    assert {record["kind"] for record in kept} == {"reload"}
    for restarted in ("loop", "transcript", "python"):  # up once, and again for /clear
        assert sum(record["row"] == restarted for record in kept) >= 2
    assert sum(record["row"] == "ui" for record in kept) == 1  # the ui depends on nothing: no restart


async def test_the_trajectory_of_the_rows_written_is_the_boot_as_one_line_and_each_restart_as_reloads(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """cordis has no first-load event, so the log records a row's first load as a reload; the trajectory
    tells it by the row id, from the file as the shell writes it."""
    import fragile

    log = tmp_path / "rows.jsonl"
    fragile.script("/clear", "after")
    ui = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:scripted_ui"\n'
    )
    await asyncio.wait_for(run([*layers(), ui], row_log=log), 10)
    seen: set[str] = set()
    firsts: list[str] = []
    again: list[str] = []
    for record in rows_of(log):
        (again if record["row"] in seen else firsts).append(record["row"])
        seen.add(record["row"])
    assert len(firsts) > 20 and {"loop", "transcript", "python"} <= set(
        again
    )  # a boot, and what /clear restarted
    lines = [line.text for line in rendered(trajectory([], log.read_bytes()), datetime.UTC)]
    assert re.fullmatch(rf"row first load  [0-9:.-]+ [0-9:.]+  {len(firsts)} rows in [0-9.]+s", lines[0])
    assert [line.split()[2] for line in lines[1:]] == again
    assert all(line.startswith("row reload ") for line in lines[1:])


async def test_a_row_that_fails_is_kept_with_its_error_though_the_run_stops_for_it(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    log = tmp_path / "rows.jsonl"
    broken = patch(composition, '[[plugin]]\nid = "broken"\nuse = "fragile:broken_on_purpose"\n')
    with pytest.raises(NotStarted):
        await asyncio.wait_for(run([*layers(), broken], [CHAT], row_log=log), 10)
    (failed,) = [record for record in rows_of(log) if record["kind"] == "failed"]
    assert failed == {
        "at": failed["at"],
        "kind": "failed",
        "row": "broken",
        "error": "RuntimeError('broken on purpose')",
    }
    assert STAMP.fullmatch(failed["at"])


async def test_a_sub_agents_rows_are_kept_like_any_other(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    log = tmp_path / "rows.jsonl"
    child = patch(composition, '[[plugin]]\nid = "agents/general-1/heart"\nuse = "fragile:heartbeat"\n')
    await asyncio.wait_for(run([*layers(), child], [CHAT], row_log=log), 10)
    (kept,) = [record for record in rows_of(log) if record["row"].startswith("agents/")]
    assert (kept["kind"], kept["row"]) == ("reload", "agents/general-1/heart")


async def test_the_listener_only_queues_a_line_the_file_is_opened_and_written_off_the_event_loop(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "rows.jsonl"
    loop_thread, fds, touched = threading.get_ident(), set[int](), list[int]()
    real_open, real_write = os.open, os.write

    def spy_open(path: str, flags: int, *args: int, **kwargs: int) -> int:
        fd = real_open(path, flags, *args, **kwargs)
        if str(path) == str(log):
            fds.add(fd)
            touched.append(threading.get_ident())
        return fd

    def spy_write(fd: int, data: bytes | memoryview) -> int:
        if fd in fds:
            touched.append(threading.get_ident())
        return real_write(fd, data)

    monkeypatch.setattr(os, "open", spy_open)
    monkeypatch.setattr(os, "write", spy_write)
    await asyncio.wait_for(run([*layers(), patch(composition)], [CHAT], row_log=log), 10)
    monkeypatch.undo()
    assert len(touched) > 10 and loop_thread not in touched  # an open, then a write for each line
    assert len(records(log)) == len(touched) - 1


async def test_a_log_that_cannot_be_written_ends_and_the_run_goes_on(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log is for the person, not the run: its directory is gone (a session being removed), the first
    write fails on its thread, and the listener stops without taking down the row that was emitting. The
    person is told once, after the rows have unwound, through `report`: the file, when that write failed
    (the appender's time, on its thread), and the error. The shell hears of the failure only after the
    loop has been held for 0.2 s, so a stamp taken when the shell heard of it would miss by that much."""
    log = tmp_path / "gone" / "rows.jsonl"
    attempted, failed = threading.Event(), threading.Event()
    failed_at: list[datetime.datetime] = []  # when the open of the log failed, on the writer's thread
    real_open, held = os.open, False

    def spy_open(path: str, flags: int, *args: int, **kwargs: int) -> int:
        if str(path) != str(log):
            return real_open(path, flags, *args, **kwargs)
        attempted.set()
        try:
            return real_open(path, flags, *args, **kwargs)
        except OSError:
            failed_at.append(datetime.datetime.now(datetime.UTC))
            failed.set()
            raise

    def hold(_: str) -> None:
        """The shell's trace, called for each event before the shell hears it: once the log's write has
        been tried, wait for it to fail, then hold the loop 0.2 s before the next event."""
        nonlocal held
        if attempted.is_set() and not held:
            held = True
            failed.wait(10)
            time.sleep(0.2)

    monkeypatch.setattr(os, "open", spy_open)
    told: list[str] = []
    await asyncio.wait_for(
        run([*layers(), patch(composition)], [CHAT], trace=hold, report=told.append, row_log=log), 10
    )
    assert not log.exists()
    (line,) = told
    assert line.startswith(f"{log} stopped being written (a write failed at ")
    stamp = STAMP.search(line)
    assert stamp
    (failed_when,) = failed_at
    # the stamp is the failure's to the millisecond; the shell heard of it 200 ms later
    gap = abs(datetime.datetime.fromisoformat(stamp.group()) - failed_when)
    assert gap < datetime.timedelta(milliseconds=50)
    assert line.endswith(f"{os.strerror(errno.ENOENT)}; the row reloads from that write on are not in it")


async def test_a_log_that_was_written_to_the_end_tells_nobody_anything(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    log, told = tmp_path / "rows.jsonl", []
    await asyncio.wait_for(run([*layers(), patch(composition)], [CHAT], report=told.append, row_log=log), 10)
    assert records(log) and told == []


async def test_no_log_is_kept_unless_one_is_asked_for(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    await asyncio.wait_for(run([*layers(), patch(composition)], [CHAT]), 10)
    assert not list(tmp_path.rglob("rows.jsonl"))


async def test_a_second_run_goes_on_in_the_same_file_after_a_marker_of_its_own_and_its_boot_is_one_line(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """A session resumed appends to its `rows.jsonl`: the rows of the second run were all seen in the
    first, and without the marker between them each would be a `row reload` line."""
    log = tmp_path / "rows.jsonl"
    for _ in range(2):
        await asyncio.wait_for(run([*layers(), patch(composition)], [CHAT], row_log=log), 10)
    kept = records(log)
    starts = [number for number, record in enumerate(kept) if record["kind"] == "run"]
    assert len(starts) == 2 and starts[0] == 0  # one marker for each run, the first line of its part
    boots = [kept[1 : starts[1]], kept[starts[1] + 1 :]]
    assert all(record["kind"] == "reload" for boot in boots for record in boot)
    assert {record["row"] for record in boots[0]} == {record["row"] for record in boots[1]}
    assert all(len({record["row"] for record in boot}) == len(boot) for boot in boots)  # no row twice
    shown = [line.text for line in rendered(trajectory([], log.read_bytes()), datetime.UTC)]
    assert len(shown) == 2  # a boot each, and no reload of a row that came up again
    for boot, line in zip(boots, shown, strict=True):
        assert re.fullmatch(rf"row first load  [0-9:.-]+ [0-9:.]+  {len(boot)} rows in [0-9.]+s", line)
