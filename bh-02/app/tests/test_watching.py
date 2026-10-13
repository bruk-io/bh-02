"""`bh-02 watch SESSION AGENT`: one sub-agent's event log rendered, read-only, for names bh-02
made and no others."""

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from agents_cordis_plugin import EventLog, ended_record, started_record
from bh_02.cli import main
from bh_02.watching import Refused, refused, rendered, watched

_SESSION = "20261012-091500-ab12"


def _log(root: Path, *events: dict[str, object], session: str = _SESSION, agent: str = "general-1") -> Path:
    """A log as the agents row writes it (its own `EventLog`), under `root`."""
    place = root / session / "agents" / agent
    place.mkdir(parents=True, mode=0o700)
    log = EventLog.open(str(place / "events.jsonl"))

    async def write() -> None:
        for event in events:
            await log.write(event)
        await log.close()

    asyncio.run(write())
    return place / "events.jsonl"


_EVENTS = (
    started_record("general-1", "general", "count the files", False),
    {"type": "text", "text": "Counting "},
    {"type": "text", "text": "now."},
    {"type": "tool_call", "id": "c1", "name": "python", "input": {"code": "len(list(Path('.').glob('*')))"}},
    {"type": "tool_result", "call_id": "c1", "content": "3", "is_error": False},
    {"type": "usage", "input_tokens": 10, "output_tokens": 2},
    {"type": "stop", "reason": "answered"},
    ended_record("Report from agent general-1: three"),
)


def test_a_log_is_rendered_a_line_an_event_with_streamed_text_run_together(tmp_path: Path) -> None:
    _log(tmp_path, *_EVENTS)
    out = "".join(watched(tmp_path, _SESSION, "general-1", follow=False))
    assert "agent general-1 (general, foreground) was asked: count the files" in out
    assert "\nCounting now.\n" in out  # the chunks of one answer are one line
    assert "-> python" in out and "<- 3" in out and "used 10 input, 2 output tokens" in out
    assert "step ended: answered" in out and "ended. Its report to its parent: Report from agent" in out


def test_what_the_model_said_reaches_the_terminal_without_an_escape_sequence() -> None:
    line = json.dumps(
        {"at": "2026-10-12T09:15:00.000+00:00", "event": {"type": "text", "text": "a\x1b[31mred\x07\x9b"}}
    )
    text, inline, last = rendered(line.encode(), False)
    assert text == "a[31mred" and inline and not last


def test_a_line_that_is_not_a_record_is_said_so_and_skipped(tmp_path: Path) -> None:
    text, _, _ = rendered(b"not json", False)
    assert text.startswith("? a line of the log that is not a record")


@pytest.mark.parametrize(
    ("session", "agent"),
    [
        ("..", "general-1"),
        (_SESSION, ".."),
        (_SESSION, "../general-1"),
        (f"../{_SESSION}", "general-1"),
        (f"{_SESSION}/agents/general-1", "x"),
        ("/etc", "general-1"),
        (_SESSION, "/etc/passwd"),
        (_SESSION, "general-1/../../../x"),
        (_SESSION, "General-1"),
        (_SESSION, "general"),
        ("", "general-1"),
        (_SESSION, ""),
        (_SESSION[:-1], "general-1"),
        (f"{_SESSION}\n", "general-1"),
    ],
)
def test_a_name_bh_02_did_not_make_is_refused_before_any_path_is_made(
    tmp_path: Path, session: str, agent: str
) -> None:
    assert refused(session, agent) is not None
    with pytest.raises(Refused):
        next(watched(tmp_path, session, agent, follow=False))


def test_the_cli_refuses_traversal_and_reads_nothing_outside_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    outside = tmp_path / "bh-02" / "secret"
    outside.mkdir(parents=True)
    (outside / "events.jsonl").write_text(
        json.dumps({"at": "x" * 20, "event": {"type": "text", "text": "SECRET"}}) + "\n"
    )
    runner = CliRunner()
    for session, agent in (("..", "secret"), (_SESSION, "../../secret"), ("/", "etc")):
        result = runner.invoke(main, ["watch", session, agent])
        assert result.exit_code == 1 and "not a" in result.output, result.output
        assert "SECRET" not in result.output


def test_a_missing_log_is_said_with_where_it_looked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    result = CliRunner().invoke(main, ["watch", _SESSION, "general-1"])
    assert result.exit_code == 1
    assert (
        f"no event log at {tmp_path}/bh-02/sessions/{_SESSION}/agents/general-1/events.jsonl" in result.output
    )


def test_a_log_that_is_a_link_is_not_read(tmp_path: Path) -> None:
    place = tmp_path / _SESSION / "agents" / "general-1"
    place.mkdir(parents=True)
    target = tmp_path / "elsewhere.jsonl"
    target.write_text("SECRET\n")
    (place / "events.jsonl").symlink_to(target)
    with pytest.raises(Refused, match="is a link"):
        list(watched(tmp_path, _SESSION, "general-1", follow=False))


def test_watching_opens_nothing_for_writing_and_leaves_the_log_and_its_directory_as_they_were(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _log(tmp_path, *_EVENTS)
    before = (log.read_bytes(), os.stat(log), sorted(p.name for p in log.parent.iterdir()))
    os.chmod(log, 0o400)  # read-only on disk too
    opened: list[int] = []
    real = os.open

    def spy(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(flags)
        return real(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", spy)
    "".join(watched(tmp_path, _SESSION, "general-1", follow=False))
    monkeypatch.undo()
    writing = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert opened and not any(flags & writing for flags in opened)
    after = os.stat(log)
    assert log.read_bytes() == before[0] and sorted(p.name for p in log.parent.iterdir()) == before[2]
    assert (after.st_mtime_ns, after.st_size, after.st_ino) == (
        before[1].st_mtime_ns,
        before[1].st_size,
        before[1].st_ino,
    )
    assert stat.S_IMODE(after.st_mode) == 0o400


def test_following_stops_at_the_agent_s_end_and_picks_up_what_is_added(tmp_path: Path) -> None:
    log = _log(tmp_path, *_EVENTS[:2])
    polls = 0

    def sleep(seconds: float) -> None:
        nonlocal polls
        polls += 1
        if polls == 1:  # the agent goes on: a whole line, and half of the next
            with log.open("ab") as file:
                file.write(
                    json.dumps(
                        {"at": "2026-10-12T09:15:01.000+00:00", "event": {"type": "text", "text": "more"}}
                    ).encode()
                    + b"\n"
                )
                file.write(b'{"at": "2026-10-12T09:15:02')
        elif polls == 2:  # the half is finished, and the agent ends
            with log.open("ab") as file:
                file.write(b'.000+00:00", "event": {"type": "agent_end", "report": "done"}}\n')

    out = "".join(watched(tmp_path, _SESSION, "general-1", follow=True, sleep=sleep))
    assert "Counting more" in out and "ended. Its report to its parent: done" in out
    assert polls == 2
