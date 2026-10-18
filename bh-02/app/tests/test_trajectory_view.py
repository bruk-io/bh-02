"""`bh-02 trajectory`: a session's files found, read through no link, and laid out; followed across a
`/clear` or `/compact` that replaces the live file (`bh_02.viewing`, `bh_02.cli`)."""

import datetime
import json
import os
import re
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent_cordis_plugin import rewrite, seeded
from bh_02 import sessions, viewing
from bh_02.cli import main
from bh_02.viewing import shown
from bh_02.watching import Refused

type Json = Mapping[str, object]

SESSION = "20261012-091500-ab12"
LOCAL = datetime.timezone(datetime.timedelta(hours=-7))
UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def line(entry: Json) -> bytes:
    return json.dumps(entry).encode() + b"\n"


def message(text: str, at: str) -> Json:
    return {"role": "user", "content": text, "at": at}


def answer(at: str, **record: object) -> Json:
    return {
        "role": "assistant",
        "content": "ok",
        "step": {"at": at, "first_chunk": 0.5, "took": 1.0} | record,
    }


def call_of(*ids: str, at: str = "2026-10-18T03:00:03.000Z") -> Json:
    calls = [{"id": id, "name": "python", "input": {}} for id in ids]
    return {"role": "assistant", "content": "", "tool_calls": calls, "step": {"at": at}}


def result(call_id: str, at: str) -> Json:
    return {
        "role": "tool",
        "content": "ok",
        "call_id": call_id,
        "call": {"at": at, "answer": "unasked", "took": 0.2},
    }


def put(path: Path, *entries: Json) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(line(entry) for entry in entries))
    return path


def pushed(path: Path, *entries: Json) -> None:
    """What the appender does: more whole lines on the end of the file."""
    with path.open("ab") as out:
        out.write(b"".join(line(entry) for entry in entries))


def lines_of(root: Path, session: str = SESSION, *, follow: bool = False) -> list[str]:
    return list(shown(root, session, follow=follow, tz=LOCAL))


ONE = (
    message("first", "2026-10-18T03:00:00.000Z"),
    answer("2026-10-18T03:00:01.000Z", model="claude-opus-5-5"),
)


def test_a_sessions_files_are_read_and_laid_out_with_its_sub_agents_and_nothing_else(tmp_path: Path) -> None:
    session = tmp_path / SESSION
    put(session / "transcript.jsonl.bak", message("older", "2026-10-18T02:00:00.000Z"))
    put(session / "transcript.jsonl", *ONE[:1], call_of("c1"), result("c1", "2026-10-18T03:00:04.000Z"))
    put(
        session / "transcript.jsonl.new", message("leftover of a crashed rewrite", "2026-10-18T09:00:00.000Z")
    )
    put(session / "events.jsonl", message("what the screen showed", "2026-10-18T09:00:00.000Z"))
    put(session / "agents" / "general-1" / "transcript.jsonl", message("count", "2026-10-18T03:00:05.000Z"))
    put(
        session / "agents" / "general-1" / "events.jsonl",
        message("its event log", "2026-10-18T09:00:00.000Z"),
    )
    out = lines_of(tmp_path)
    assert [text for text in out if text.strip().startswith(("conversation", "reply", "sub-agent"))] == [
        "conversation 1  transcript.jsonl.bak  2026-10-17 19:00:00.000",
        "  reply 1  2026-10-17 19:00:00.000  older",
        "conversation 2  transcript.jsonl  2026-10-17 20:00:00.000  begun by /clear",
        "  reply 1  2026-10-17 20:00:00.000  first",
        "sub-agent general-1  (no call that started it is recorded)",
        "  conversation 1  transcript.jsonl  2026-10-17 20:00:05.000",
        "    reply 1  2026-10-17 20:00:05.000  count",
    ]
    assert not any("leftover" in text or "screen" in text or "event log" in text for text in out)


def test_the_sessions_row_reloads_are_read_with_its_files_and_shown_among_the_lines(tmp_path: Path) -> None:
    session = tmp_path / SESSION
    put(session / "transcript.jsonl", *ONE)
    put(
        session / "rows.jsonl",
        {"at": "2026-10-18T02:59:00.000Z", "kind": "reload", "row": "loop"},
        {"at": "2026-10-18T03:00:00.500Z", "kind": "failed", "row": "model", "error": "RuntimeError('x')"},
    )
    assert lines_of(tmp_path) == [
        "row reload loop  19:59:00.000",
        "conversation 1  transcript.jsonl  2026-10-17 20:00:00.000",
        "  reply 1  2026-10-17 20:00:00.000  first",
        "    row failed model  20:00:00.500  RuntimeError('x')",
        "    step 1  20:00:01.000  claude-opus-5-5  first chunk 0.50s  generated in 0.50s",
    ]


def test_a_session_with_no_rows_file_is_shown_without_reloads(tmp_path: Path) -> None:
    put(tmp_path / SESSION / "transcript.jsonl", *ONE)  # a session from before they were kept
    assert not any("row " in text for text in lines_of(tmp_path))


def test_a_rows_file_that_is_a_link_or_has_a_second_name_or_is_too_large_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = put(
        tmp_path / "outside.jsonl", {"at": "2026-10-18T03:00:00.000Z", "kind": "reload", "row": "SECRET"}
    )
    session = tmp_path / "sessions" / SESSION
    put(session / "transcript.jsonl", *ONE)
    (session / "rows.jsonl").symlink_to(secret)
    with pytest.raises(Refused, match="rows.jsonl is a link") as linked:
        lines_of(tmp_path / "sessions")
    assert "SECRET" not in linked.value.message
    (session / "rows.jsonl").unlink()
    os.link(secret, session / "rows.jsonl")
    with pytest.raises(Refused, match="one name") as named:
        lines_of(tmp_path / "sessions")
    assert "SECRET" not in named.value.message
    (session / "rows.jsonl").unlink()
    put(
        session / "rows.jsonl",
        {"at": "2026-10-18T03:00:00.000Z", "kind": "failed", "row": "x", "error": "e" * 600},
    )
    monkeypatch.setattr(viewing, "_CAP", 500)  # the transcript is read; the rows file is over it
    with pytest.raises(Refused, match="rows.jsonl is larger than 500 bytes"):
        lines_of(tmp_path / "sessions")


def test_a_session_with_no_transcript_yet_is_refused_and_says_where_it_looked(tmp_path: Path) -> None:
    (tmp_path / SESSION).mkdir()
    with pytest.raises(Refused, match=f"session {SESSION} has no conversation yet"):
        lines_of(tmp_path)
    with pytest.raises(Refused, match="has no conversation yet"):
        lines_of(tmp_path, "20261012-091500-ffff")  # not there at all


@pytest.mark.parametrize(
    "session", ["..", "../x", "/etc", SESSION + "/agents", "", "20261012-091500", SESSION + "\n"]
)
def test_a_session_name_bh_02_did_not_make_is_refused_before_any_path_is_made(
    tmp_path: Path, session: str
) -> None:
    with pytest.raises(Refused, match="is not a session id bh-02 made"):
        lines_of(tmp_path, session)


# --- read through no link ---------------------------------------------------------------------------------


def test_files_are_opened_read_only_through_no_link_and_nothing_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = tmp_path / SESSION
    log = put(session / "transcript.jsonl", *ONE)
    put(session / "agents" / "general-1" / "transcript.jsonl", message("count", "2026-10-18T03:00:05.000Z"))
    os.chmod(log, 0o400)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    opened: list[tuple[str, int]] = []
    real = os.open

    def spy(path: str, flags: int, *args: object, **kwargs: object) -> int:
        opened.append((str(path), flags))
        return real(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    lines_of(tmp_path)
    monkeypatch.undo()
    writing = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert opened and not any(flags & writing for _, flags in opened)
    # every transcript was opened by the one opener that follows no link; only the root, which the
    # caller trusts, is opened as named
    transcripts = [flags for path, flags in opened if path == "transcript.jsonl"]
    assert len(transcripts) == 2 and all(flags & os.O_NOFOLLOW for flags in transcripts)
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == before


def test_a_transcript_that_is_a_link_is_not_read(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere.jsonl"
    put(outside, message("SECRET", "2026-10-18T03:00:00.000Z"))
    session = tmp_path / "sessions" / SESSION
    session.mkdir(parents=True)
    (session / "transcript.jsonl").symlink_to(outside)
    out: list[str] = []
    with pytest.raises(Refused, match="is a link") as refusal:
        out.extend(lines_of(tmp_path / "sessions"))
    assert "SECRET" not in "".join(out) + refusal.value.message


def test_a_session_directory_a_backup_or_the_agents_directory_that_is_a_link_is_not_followed(
    tmp_path: Path,
) -> None:
    elsewhere = tmp_path / "elsewhere"
    put(elsewhere / "transcript.jsonl", message("SECRET", "2026-10-18T03:00:00.000Z"))
    put(elsewhere / "general-1" / "transcript.jsonl", message("SECRET", "2026-10-18T03:00:00.000Z"))
    root = tmp_path / "sessions"
    root.mkdir()
    (root / SESSION).symlink_to(elsewhere)  # the session's own directory
    with pytest.raises(Refused, match="can't read") as linked:
        lines_of(root)
    assert "SECRET" not in linked.value.message

    root, other = tmp_path / "sessions2", "20261012-091500-cd34"
    put(root / other / "transcript.jsonl", *ONE)
    (root / other / "agents").symlink_to(elsewhere)  # the directory the sub-agents are in
    with pytest.raises(Refused, match="can't read"):
        lines_of(root, other)

    third = "20261012-091500-ef56"
    put(root / third / "transcript.jsonl", *ONE)
    (root / third / "agents").mkdir()
    (root / third / "agents" / "general-1").symlink_to(elsewhere / "general-1")  # one sub-agent's
    with pytest.raises(Refused, match="can't read"):
        lines_of(root, third)


def test_a_transcript_with_a_second_name_is_not_read(tmp_path: Path) -> None:
    """A hard link is another name for a file the jail may hide: refused, as every reader of one is."""
    secret = put(tmp_path / "outside.jsonl", message("SECRET", "2026-10-18T03:00:00.000Z"))
    (tmp_path / "sessions" / SESSION).mkdir(parents=True)
    os.link(secret, tmp_path / "sessions" / SESSION / "transcript.jsonl")
    with pytest.raises(Refused, match="one name") as refusal:
        lines_of(tmp_path / "sessions")
    assert "SECRET" not in refusal.value.message


def test_a_transcript_over_the_cap_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    put(tmp_path / SESSION / "transcript.jsonl", *ONE)
    monkeypatch.setattr(viewing, "_CAP", 10)
    with pytest.raises(Refused, match="larger than 10 bytes"):
        lines_of(tmp_path)


# --- a child's name is judged before a path is made of it ---------------------------------------------------


def test_a_sub_agent_is_a_name_in_the_agents_directory_that_bh_02_makes_and_no_other(tmp_path: Path) -> None:
    session = tmp_path / SESSION
    put(session / "transcript.jsonl", *ONE)
    put(session / "agents" / "general-1" / "transcript.jsonl", message("fine", "2026-10-18T03:00:05.000Z"))
    for name in (
        "General-1",
        "general",
        "x y-1",
        "-general-1",
        "general-1.bak",
        "general-1 ",
        "a" * 40 + "-1",
        "general-0001234567",
    ):
        put(
            session / "agents" / name / "transcript.jsonl",
            message(f"SECRET {name}", "2026-10-18T03:00:06.000Z"),
        )
    (session / "agents" / "stray-file").write_text("not a directory")
    out = "\n".join(lines_of(tmp_path))
    assert "fine" in out and "SECRET" not in out


def test_every_directory_walked_to_is_a_name_bh_02_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = tmp_path / SESSION
    put(session / "transcript.jsonl", *ONE)
    put(session / "agents" / "general-1" / "transcript.jsonl", message("fine", "2026-10-18T03:00:05.000Z"))
    put(session / "agents" / "Evil-1" / "transcript.jsonl", message("SECRET", "2026-10-18T03:00:06.000Z"))
    walked: list[tuple[str, ...]] = []
    real = viewing.directory_beneath

    def spy(root: Path | int, names: list[str]):
        walked.append(tuple(names))
        return real(root, names)

    monkeypatch.setattr(viewing, "directory_beneath", spy)
    lines_of(tmp_path)
    assert (SESSION, "agents", "general-1") in walked
    assert all(not any("Evil" in name for name in names) for names in walked)


def test_a_call_naming_a_child_that_is_no_name_of_bh_02s_is_shown_not_followed(tmp_path: Path) -> None:
    """The name in a transcript is only text: it is matched against the sub-agents found, and never made
    into a path, so a transcript can't send the reader outside the session."""
    put(tmp_path / "outside" / "transcript.jsonl", message("SECRET", "2026-10-18T03:00:00.000Z"))
    put(
        tmp_path / "outside" / "agents" / "x" / "transcript.jsonl",
        message("SECRET", "2026-10-18T03:00:00.000Z"),
    )
    hostile = "../../outside"
    started = result("c1", "2026-10-18T03:00:04.000Z") | {
        "call": {"at": "2026-10-18T03:00:04.000Z", "child": hostile}
    }
    put(tmp_path / "sessions" / SESSION / "transcript.jsonl", ONE[0], call_of("c1"), started)
    out = lines_of(tmp_path / "sessions")
    (called,) = [text for text in out if "started sub-agent" in text]
    assert called.endswith(f"started sub-agent {hostile} (its transcript was not found)")
    assert not any("SECRET" in text for text in out)


# --- what is shown --------------------------------------------------------------------------------------


def test_a_torn_last_line_is_skipped(tmp_path: Path) -> None:
    log = put(tmp_path / SESSION / "transcript.jsonl", *ONE)
    clean = lines_of(tmp_path)
    with log.open("ab") as out:
        out.write(b'{"role": "user", "content": "being writ')  # the appender is part way through a line
    assert lines_of(tmp_path) == clean


def test_a_call_with_no_result_shows_no_result_recorded(tmp_path: Path) -> None:
    put(
        tmp_path / SESSION / "transcript.jsonl",
        ONE[0],
        call_of("c1", "c2"),
        result("c1", "2026-10-18T03:00:04.000Z"),
    )
    out = lines_of(tmp_path)
    assert [text.strip() for text in out if "no result recorded" in text] == [
        "call python  no result recorded"
    ]


def test_control_characters_in_a_transcript_never_reach_what_is_shown(tmp_path: Path) -> None:
    hostile = "\x1b[2J\x1b]0;x\x07 words \u202etxt.exe\x9b"
    put(
        tmp_path / SESSION / "transcript.jsonl",
        message(hostile, "2026-10-18T03:00:00.000Z"),
        answer("2026-10-18T03:00:01.000Z", model=hostile),
    )
    put(
        tmp_path / SESSION / "agents" / "general-1" / "transcript.jsonl",
        message(hostile, "2026-10-18T03:00:05.000Z"),
    )
    out = lines_of(tmp_path)
    assert any("words" in text for text in out)
    assert not any(UNSAFE.search(text) or "\n" in text for text in out)


# --- following ---------------------------------------------------------------------------------------------


class Done(Exception):
    """The test's clock has nothing more to do: leave the follow loop."""


def following(root: Path, actions: list[Callable[[], None]]) -> tuple[list[str], list[float]]:
    """Follow session SESSION: after poll N, `actions[N-1]()` changes the files; once they are used
    up the loop is left. Returns every line printed, and the seconds it slept for between polls."""
    slept: list[float] = []
    todo = iter(actions)

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        if (action := next(todo, None)) is None:
            raise Done
        action()

    out: list[str] = []
    try:
        for text in shown(root, SESSION, follow=True, tz=LOCAL, sleep=sleep):
            out.append(text)
    except Done:
        pass
    return out, slept


def test_following_prints_what_is_new_every_second_across_a_clear_and_a_compact(tmp_path: Path) -> None:
    path = tmp_path / SESSION / "transcript.jsonl"
    put(path, *ONE)
    step = {"at": "2026-10-18T03:10:00.000Z", "first_chunk": 2.0, "took": 9.0, "model": "claude-opus-5-5"}

    def second() -> None:
        pushed(path, message("second", "2026-10-18T03:05:00.000Z"), answer("2026-10-18T03:05:01.000Z"))

    def compact() -> None:  # /compact: the old file kept as .bak, the new one the seed
        rewrite(str(path), seeded("the summary", "the todo list", step))

    def third() -> None:
        pushed(path, message("third", "2026-10-18T03:11:00.000Z"), answer("2026-10-18T03:11:01.000Z"))

    def clear() -> None:  # /clear: an empty file; the next message is its first entry
        rewrite(str(path), [])

    def fourth() -> None:
        pushed(path, message("fourth", "2026-10-18T03:20:00.000Z"))

    out, slept = following(tmp_path, [second, compact, third, clear, lambda: None, fourth])
    assert (
        slept == [1.0] * 7
    )  # re-read every second: after a poll that found a change, and one that found none
    # each line once, in the order it came, whichever file it was in: the old conversation is not printed
    # again when its file is renamed, and the new one is not mistaken for it
    assert out == [
        "conversation 1  transcript.jsonl  2026-10-17 20:00:00.000",
        "  reply 1  2026-10-17 20:00:00.000  first",
        "    step 1  20:00:01.000  claude-opus-5-5  first chunk 0.50s  generated in 0.50s",
        "  reply 2  2026-10-17 20:05:00.000  second",
        "    step 1  20:05:01.000  first chunk 0.50s  generated in 0.50s",
        "conversation 2  transcript.jsonl  2026-10-17 20:10:00.000"
        "  begun by /compact, asked to keep: the todo list",
        "  summary step  2026-10-17 20:10:00.000  claude-opus-5-5  first chunk 2.00s  generated in 7.00s",
        "  reply 1  2026-10-17 20:11:00.000  third",
        "    step 1  20:11:01.000  first chunk 0.50s  generated in 0.50s",
        "conversation 3  transcript.jsonl  2026-10-17 20:20:00.000  begun by /clear",
        "  reply 1  2026-10-17 20:20:00.000  fourth",
    ]
    # the files really were replaced: the conversations before are the backups
    assert sorted(p.name for p in path.parent.iterdir()) == [
        "transcript.jsonl",
        "transcript.jsonl.bak",
        "transcript.jsonl.bak.2",
    ]


def test_a_call_still_running_is_printed_once_when_its_result_is_in_not_before_and_not_twice(
    tmp_path: Path,
) -> None:
    path = tmp_path / SESSION / "transcript.jsonl"
    put(path, ONE[0], call_of("c1"))

    def finish() -> None:
        pushed(path, result("c1", "2026-10-18T03:00:04.000Z"))

    out, _ = following(tmp_path, [lambda: None, finish, lambda: None])
    assert [text.strip() for text in out if "call python" in text] == [
        "call python  20:00:04.000  answer unasked  ran 0.20s"
    ]
    assert not any("no result recorded" in text for text in out)


def test_a_sub_agent_printed_before_its_call_was_recorded_is_not_printed_again_under_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / SESSION / "transcript.jsonl"
    put(path, ONE[0], call_of("c1"))
    put(
        tmp_path / SESSION / "agents" / "general-1" / "transcript.jsonl",
        message("count", "2026-10-18T03:00:05.000Z"),
    )

    def recorded() -> None:
        started = result("c1", "2026-10-18T03:00:30.000Z") | {
            "call": {"at": "2026-10-18T03:00:04.000Z", "took": 26.0, "child": "general-1"}
        }
        pushed(path, started)

    out, _ = following(tmp_path, [recorded, lambda: None])
    assert len(out) == len(set(out))
    assert sum("count" in text for text in out) == 1
    assert any(
        text.strip().startswith("call python") and "started sub-agent general-1" in text for text in out
    )


def test_a_reload_that_comes_while_following_is_printed_once_where_it_belongs_and_not_again(
    tmp_path: Path,
) -> None:
    path, rows = tmp_path / SESSION / "transcript.jsonl", tmp_path / SESSION / "rows.jsonl"
    put(path, *ONE)
    put(rows, {"at": "2026-10-18T03:00:00.500Z", "kind": "reload", "row": "first"})

    def reloaded() -> None:  # the shell appended another, after the last line; the next poll finds it
        pushed(rows, {"at": "2026-10-18T03:00:02.000Z", "kind": "reload", "row": "second"})

    def replied() -> None:
        pushed(path, message("next", "2026-10-18T03:01:00.000Z"))

    out, _ = following(tmp_path, [lambda: None, reloaded, replied, lambda: None])
    assert [text.strip().split("  ")[0] for text in out] == [
        "conversation 1",
        "reply 1",
        "row reload first",
        "step 1",
        "row reload second",
        "reply 2",
    ]


def test_following_a_session_not_yet_started_waits_for_its_first_file(tmp_path: Path) -> None:
    (tmp_path / SESSION).mkdir()

    def started() -> None:
        put(tmp_path / SESSION / "transcript.jsonl", *ONE)

    out, _ = following(tmp_path, [started, lambda: None])
    assert [text for text in out if text.startswith("conversation")] == [
        "conversation 1  transcript.jsonl  2026-10-17 20:00:00.000"
    ]


# --- the command ------------------------------------------------------------------------------------------


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield tmp_path / "state" / "bh-02" / "sessions"


def started(*texts: str) -> sessions.Session:
    """A session in the working directory, as `bh-02` makes one, that has been said `texts`."""
    made = sessions.create(sessions.state_root(), str(Path.cwd()), model="work/opus", no_jail=True)
    entries = [message(text, f"2026-10-18T03:0{n}:00.000Z") for n, text in enumerate(texts)]
    if entries:
        put(made.dir / "transcript.jsonl", *entries)
    return made


def test_the_command_prints_the_newest_session_unless_one_is_named(state: Path) -> None:
    older, newer = started("in the older"), started("in the newer")
    runner = CliRunner()
    newest = runner.invoke(main, ["trajectory"])
    assert newest.exit_code == 0, newest.output
    assert "in the newer" in newest.output and "in the older" not in newest.output
    named = runner.invoke(main, ["trajectory", older.id])
    assert "in the older" in named.output and "in the newer" not in named.output
    short = runner.invoke(
        main, ["trajectory", older.id[-4:]]
    )  # the status bar's short id, as --resume takes it
    assert "in the older" in short.output
    assert newer.id != older.id


def test_the_command_prints_times_in_the_local_zone(state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started("hello")
    monkeypatch.setenv("TZ", "Pacific/Auckland")  # UTC+13 on the 18th of October
    time.tzset()
    try:
        result = CliRunner().invoke(main, ["trajectory"])
    finally:
        monkeypatch.undo()
        time.tzset()
    assert "reply 1  2026-10-18 16:00:00.000  hello" in result.output


def test_the_command_says_when_the_id_names_none_or_several_or_a_record_that_cannot_be_read(
    state: Path,
) -> None:
    runner = CliRunner()
    nothing = runner.invoke(main, ["trajectory"])
    assert nothing.exit_code == 2 and "no sessions in this directory yet" in nothing.output
    first, second = started("a"), started("b")
    unknown = runner.invoke(main, ["trajectory", "zzzz"])
    assert unknown.exit_code == 2 and "no session 'zzzz' in this directory" in unknown.output
    both = runner.invoke(main, ["trajectory", first.id[:8]])  # the day they started on
    assert both.exit_code == 2 and "matches 2 sessions' ids" in both.output
    (second.dir / "meta.json").write_text(json.dumps({"cwd": str(Path.cwd())}))
    broken = runner.invoke(main, ["trajectory", second.id])
    assert broken.exit_code == 2 and f"can't show {second.id}" in broken.output


def test_the_command_says_so_when_the_session_has_no_conversation_yet(state: Path) -> None:
    made = started()
    result = CliRunner().invoke(main, ["trajectory", made.id])
    assert result.exit_code == 1
    assert f"error: session {made.id} has no conversation yet" in result.output


def test_the_command_refuses_a_transcript_that_is_a_link(state: Path, tmp_path: Path) -> None:
    made = started()
    put(tmp_path / "elsewhere.jsonl", message("SECRET", "2026-10-18T03:00:00.000Z"))
    (made.dir / "transcript.jsonl").symlink_to(tmp_path / "elsewhere.jsonl")
    result = CliRunner().invoke(main, ["trajectory", made.id])
    assert result.exit_code == 1 and "is a link" in result.output and "SECRET" not in result.output


def test_the_command_has_a_follow_option_and_is_listed_with_the_others() -> None:
    runner = CliRunner()
    assert "--follow" in runner.invoke(main, ["trajectory", "--help"]).output
    assert "trajectory" in runner.invoke(main, ["--help"]).output
