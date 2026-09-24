"""The history file: what to draw again (pure), and the file itself (a real one, in tmp_path)."""

import errno
import json
import os
from pathlib import Path

import pytest

from tui_cordis_plugin import History, frame, replayable
from tui_cordis_plugin.history import compacted


def test_a_streamed_run_is_merged_into_one_entry_per_block() -> None:
    entries = [
        {"type": "user", "text": "hi"},
        {"type": "thinking", "text": "hm"},
        {"type": "thinking", "text": "m"},
        {"type": "text", "text": "Hel"},
        {"type": "text", "text": "lo"},
        {"type": "turn_end"},
        {"type": "text", "text": "next turn"},
    ]
    replay = replayable(entries, 100)
    assert replay.skipped == 0
    assert list(replay.entries) == [
        {"type": "user", "text": "hi"},
        {"type": "thinking", "text": "hmm"},
        {"type": "text", "text": "Hello"},
        {"type": "turn_end"},
        {"type": "text", "text": "next turn"},  # a turn's end is never merged across
    ]
    assert entries[3] == {"type": "text", "text": "Hel"}  # the entries given are left alone


def test_a_long_history_is_cut_to_the_last_entries_starting_at_a_message() -> None:
    turn = [{"type": "user", "text": "q"}, {"type": "text", "text": "a"}, {"type": "turn_end"}]
    replay = replayable(turn * 10, 4)
    assert replay.skipped == 27  # the last 4 would start mid-turn: move on to the next message
    assert [e["type"] for e in replay.entries] == ["user", "text", "turn_end"]
    no_messages = replayable([{"type": "note", "text": str(n)} for n in range(10)], 3)
    assert no_messages.skipped == 7 and len(no_messages.entries) == 3


def test_entries_are_appended_a_line_each_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "session" / "events.jsonl"  # the directory is made on the first write
    history = History(str(path))
    assert history.read() == []
    history.record({"type": "user", "text": "hi"})
    history.record({"type": "text", "text": object()})  # not JSON: kept as its str
    assert len(path.read_text().splitlines()) == 2  # on disk already, before any close
    history.close()
    path.write_text(path.read_text() + "not json\n[1]\n")
    again = History(str(path)).read()
    assert again[0] == {"type": "user", "text": "hi"} and again[1]["text"].startswith("<object")
    assert len(again) == 2  # the lines it can't read are skipped


def test_emptied_underneath_the_next_entry_lands_at_the_new_end(tmp_path: Path) -> None:
    """`/clear` empties the session's history files while the app has this one open."""
    path = tmp_path / "events.jsonl"
    history = History(str(path))
    history.record({"type": "user", "text": "old"})
    path.write_text("")
    history.record({"type": "user", "text": "new"})
    history.close()
    forgot = {"type": "carried", "entries": 1, "input_tokens": 0, "output_tokens": 0}
    assert History(str(path)).read() == [forgot, {"type": "user", "text": "new"}]


async def test_clear_forgets_the_entries_but_not_the_session_s_usage(tmp_path: Path) -> None:
    """A resume after `/clear` adds up to the same usage the status bar showed live."""
    path = tmp_path / "events.jsonl"
    used = {"type": "usage", "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.25}
    path.write_text(json.dumps({"type": "user", "text": "before"}) + "\n" + json.dumps(used) + "\n")
    async with History(str(path)) as history:
        history.record({"type": "text", "text": "this run"})
        history.record(used)
        path.write_text("")  # /clear
        history.record({"type": "user", "text": "after"})
        history.record(used)
    again = History(str(path)).read()
    assert frame.total_usage(again) == frame.Usage(300, 30, 0.75)
    assert [e["type"] for e in again] == ["carried", "user", "usage"]
    replay = replayable(again, 400)
    assert replay.skipped == 4 and replay.entries[0] == {"type": "user", "text": "after"}


def test_a_replay_starts_after_the_last_clear_and_the_usage_before_it_still_counts() -> None:
    used = {"type": "usage", "input_tokens": 100, "output_tokens": 10}
    entries = [
        {"type": "user", "text": "first"},
        used,
        {"type": "cleared"},
        {"type": "note", "text": "cleared once"},
        {"type": "user", "text": "second"},
        used,
        {"type": "cleared"},
        {"type": "note", "text": "cleared twice"},
        {"type": "user", "text": "third"},
    ]
    replay = replayable(entries, 400)
    assert replay.skipped == 0
    assert list(replay.entries) == [
        {"type": "note", "text": "cleared twice"},
        {"type": "user", "text": "third"},
    ]
    assert frame.total_usage(entries) == frame.Usage(200, 20)  # the session's, not the conversation's


async def test_a_trim_that_fails_leaves_no_temporary_file_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps({"type": "user", "text": str(n)}) + "\n" for n in range(50)))

    def full_disk(source: str, target: str) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", full_disk)  # the temporary file is written, then this fails
    async with History(str(path), keep=10) as history:
        assert not (tmp_path / "events.jsonl.trim").exists()  # not left behind
        assert len(history.recorded) == 50  # read whole, as it is
        assert history.warning is not None and "history can't be trimmed" in history.warning
        history.record({"type": "user", "text": "still kept"})  # recording goes on
    assert history.failed is None and len(path.read_text().splitlines()) == 51


def test_a_history_that_cannot_be_written_says_why_and_stops_trying(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("")
    history = History(str(tmp_path / "file" / "events.jsonl"))  # its directory is a file
    history.record({"type": "user", "text": "hi"})
    assert history.failed is not None and "history is not being kept" in history.failed
    history.record({"type": "user", "text": "again"})  # quietly: it said so once


def test_a_file_grown_past_twice_what_is_kept_is_trimmed_and_carries_its_usage() -> None:
    turn = [
        {"type": "user", "text": "q"},
        {"type": "text", "text": "a"},
        {"type": "text", "text": "b"},  # merged with the one before: one entry
        {
            "type": "usage",
            "input_tokens": 10,
            "output_tokens": 1,
            "cost_usd": 0.5,
            "cache_read_input_tokens": 4,
        },
        {"type": "turn_end"},
    ]
    entries = turn * 10  # 40 entries once merged
    assert compacted(entries, 20) is None  # not yet past twice 20
    trimmed = compacted(entries, 10)
    assert trimmed is not None
    carried, *kept = trimmed
    assert kept[0] == {"type": "user", "text": "q"} and len(kept) <= 10  # cut at a message sent
    assert carried["type"] == "carried" and carried["entries"] == 40 - len(kept)
    assert frame.total_usage(trimmed) == frame.total_usage(entries) == frame.Usage(100, 10, 5.0, 40)
    again = compacted([*trimmed, *entries], 10)  # trimmed again: the counts carry on
    assert again is not None and frame.total_usage(again) == frame.Usage(200, 20, 10.0, 80)
    assert replayable(again, 10).skipped == again[0]["entries"] == 40 + 40 - (len(again) - 1)


async def test_entering_a_grown_history_trims_the_file_and_keeps_what_it_says(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lines = [{"type": "user", "text": str(n)} for n in range(50)]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    async with History(str(path), keep=10) as history:
        assert history.recorded[0]["type"] == "carried" and len(history.recorded) == 11
    assert len(path.read_text().splitlines()) == 11  # the file itself was trimmed
    assert replayable(history.recorded, 10).skipped == 40
