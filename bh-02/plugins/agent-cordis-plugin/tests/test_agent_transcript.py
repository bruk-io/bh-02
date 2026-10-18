"""The transcript in a file: `append` commits in memory and queues the write (it never writes on
the event loop), `flush` waits for it, the file and what `rewrite` makes are the person's alone
(0600), and a line that can't be written is raised rather than lost."""

import asyncio
import errno
import json
import os
import stat
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_cordis_plugin import FileTranscript, TranscriptReplaced, rewrite, seeded

# a compacted conversation, as a rewrite is given one
SEED = seeded("x holds 42", "", {"at": "2026-10-18T03:47:12.345Z"})


@pytest.fixture
def open_umask() -> Iterator[None]:
    """A umask that takes nothing away, so the mode a file has is the mode it was made with."""
    before = os.umask(0)
    try:
        yield
    finally:
        os.umask(before)


def _mode(path: Path | str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


async def test_append_returns_before_a_held_write_finishes_and_flush_waits_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry is in memory at once; its line is on the writing thread, held. Nothing on the
    event loop waits for the disk, and `flush` returns only when the line is in the file."""
    path = tmp_path / "transcript.jsonl"
    reached, released = threading.Event(), threading.Event()
    real, writers = os.write, set()

    def held(fd: int, data: bytes | memoryview) -> int:
        writers.add(threading.get_ident())
        reached.set()
        released.wait(10)
        return real(fd, data)

    monkeypatch.setattr(os, "write", held)
    transcript = FileTranscript(str(path))
    try:
        transcript.append({"role": "user", "content": "hi"})  # returned: the write is not done
        assert transcript.messages == ({"role": "user", "content": "hi"},)
        async with asyncio.timeout(10):
            await asyncio.to_thread(reached.wait, 10)
        flushing = asyncio.ensure_future(transcript.flush())
        await asyncio.sleep(0.2)
        assert not flushing.done() and path.read_bytes() == b""
    finally:
        released.set()
    async with asyncio.timeout(10):
        await flushing
        assert [json.loads(line) for line in path.read_text().splitlines()] == [
            {"role": "user", "content": "hi"}
        ]
    async with transcript:  # entered after the fact, to leave: it closes the file
        pass
    assert writers and threading.get_ident() not in writers  # not the event loop's thread


async def test_entries_are_written_in_the_order_they_were_appended_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    async with FileTranscript(str(path)) as transcript:
        for n in range(50):
            transcript.append({"role": "user", "content": f"message {n}"})
        await transcript.flush()
        assert FileTranscript(str(path)).messages == transcript.messages


async def test_leaving_writes_what_is_queued_and_closes_the_file(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    async with FileTranscript(str(path)) as transcript:
        transcript.append({"role": "user", "content": "queued, never flushed"})
    assert FileTranscript(str(path)).messages == ({"role": "user", "content": "queued, never flushed"},)
    with pytest.raises(ValueError, match="is closed"):
        transcript.append({"role": "user", "content": "too late"})


async def test_a_transcript_only_read_makes_no_file_and_holds_none_open(tmp_path: Path) -> None:
    """`/compact` reads the session's file through one, in a thread, and never writes it."""
    path = tmp_path / "transcript.jsonl"
    async with FileTranscript(str(path)) as transcript:
        assert transcript.messages == ()
    assert not path.exists()


@pytest.mark.usefixtures("open_umask")
async def test_the_file_is_made_readable_by_its_owner_alone(tmp_path: Path) -> None:
    """Under a umask that takes nothing away: the mode the file is made with, not one the
    umask narrowed (a plain `open()` would make it 0666)."""
    path = tmp_path / "transcript.jsonl"
    async with FileTranscript(str(path)) as transcript:
        transcript.append({"role": "user", "content": "hi"})
        await transcript.flush()
        assert _mode(path) == 0o600


async def test_a_line_that_can_t_be_written_is_raised_by_the_next_append_and_flush(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not lost silently: the entry stays in memory (the conversation goes on in it), and the
    person is told; nothing after the failed line reaches the file."""
    path = tmp_path / "transcript.jsonl"
    transcript = FileTranscript(str(path))
    transcript.append({"role": "user", "content": "one"})
    await transcript.flush()
    real = os.write

    def full(fd: int, data: bytes | memoryview) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "write", full)
    transcript.append({"role": "user", "content": "two"})
    with pytest.raises(OSError, match="No space left"):
        await transcript.flush()
    with pytest.raises(OSError, match="No space left"):
        transcript.append({"role": "user", "content": "three"})
    monkeypatch.setattr(os, "write", real)  # room again: the failure stands, nothing is written after it
    with pytest.raises(OSError, match="No space left"):
        await transcript.flush()
    assert [m["content"] for m in transcript.messages] == ["one", "two"]
    assert FileTranscript(str(path)).messages == ({"role": "user", "content": "one"},)


async def test_a_file_replaced_under_the_transcript_is_refused_naming_the_restart(tmp_path: Path) -> None:
    """What `/clear` does to the file under a transcript whose row it then fails to restart: the
    entries after it are not written to the old inode or the new file, the person is told which
    command begins the new conversation, and the row's leaving says so too (and still closes)."""
    path = tmp_path / "transcript.jsonl"
    transcript = FileTranscript(str(path))
    transcript.append({"role": "user", "content": "one"})
    await transcript.flush()
    backup = rewrite(str(path), SEED)  # the new conversation, the old one kept beside it
    new = path.read_bytes()
    transcript.append({"role": "user", "content": "two"})  # queued: the thread has yet to look
    with pytest.raises(TranscriptReplaced, match="/restart transcript") as refused:
        await transcript.flush()
    assert (refused.value.kind, str(path) in refused.value.message) == ("transcript_replaced", True)
    assert isinstance(refused.value, OSError) and refused.value.message == str(refused.value)
    with pytest.raises(TranscriptReplaced, match="/restart transcript"):
        transcript.append({"role": "user", "content": "three"})  # refused, so not kept either
    assert [m["content"] for m in transcript.messages] == ["one", "two"]
    with pytest.raises(TranscriptReplaced, match="/restart transcript"):
        async with transcript:
            pass
    assert path.read_bytes() == new and FileTranscript(str(path)).messages == tuple(SEED)
    assert [json.loads(line)["content"] for line in Path(backup).read_text().splitlines()] == ["one"]


def _line(content: str) -> str:
    return json.dumps({"role": "user", "content": content}) + "\n"


async def test_a_torn_last_line_is_set_aside_and_the_next_entry_is_written_on_a_line_of_its_own(
    tmp_path: Path,
) -> None:
    """A process killed mid-write leaves a last line with no newline that is not JSON: an entry that
    was never finished. The session resumes without it, the next entry does not glue onto it, and
    the bytes cut are kept beside the file."""
    path = tmp_path / "transcript.jsonl"
    torn = '{"role": "assistant", "content": [{"type": "te'
    path.write_text(_line("one") + _line("two") + torn)
    async with FileTranscript(str(path)) as transcript:
        assert [m["content"] for m in transcript.messages] == ["one", "two"]
        assert path.read_text() == _line("one") + _line("two")  # cut before any write
        transcript.append({"role": "user", "content": "three"})
        await transcript.flush()
    assert path.read_text() == _line("one") + _line("two") + _line("three")
    assert [m["content"] for m in FileTranscript(str(path)).messages] == ["one", "two", "three"]
    assert (tmp_path / "transcript.jsonl.torn").read_text() == torn


@pytest.mark.usefixtures("open_umask")
async def test_the_bytes_cut_off_are_kept_readable_by_their_owner_alone_and_an_earlier_set_is_not_replaced(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transcript.jsonl"
    path.write_text(_line("one") + '{"first')
    FileTranscript(str(path))
    path.write_text(_line("one") + '{"second')  # killed again, later
    FileTranscript(str(path))
    first, second = tmp_path / "transcript.jsonl.torn", tmp_path / "transcript.jsonl.torn.2"
    assert (first.read_text(), second.read_text()) == ('{"first', '{"second')
    assert (_mode(first), _mode(second)) == (0o600, 0o600)
    assert path.read_text() == _line("one")


async def test_nothing_is_cut_until_the_bytes_are_kept(tmp_path: Path) -> None:
    """The torn line is the only copy: if it can't be set aside (a link stands where it would
    go, never followed) the transcript stops with the reason and the file is as it was."""
    path = tmp_path / "transcript.jsonl"
    path.write_text(_line("one") + '{"role": "us')
    elsewhere = tmp_path / "elsewhere"
    (tmp_path / "transcript.jsonl.torn").symlink_to(elsewhere)
    with pytest.raises(OSError, match="torn") as refused:
        FileTranscript(str(path))
    assert "transcript.jsonl.torn" in "".join(refused.value.__notes__)
    assert path.read_text() == _line("one") + '{"role": "us' and not elsewhere.exists()


async def test_a_whole_last_line_with_no_newline_is_kept_and_ended(tmp_path: Path) -> None:
    """Cut short at the last byte: the entry is whole, so it is read, and the next one starts a
    line of its own instead of making a line that is two objects."""
    path = tmp_path / "transcript.jsonl"
    path.write_text(_line("one") + _line("two").rstrip("\n"))
    async with FileTranscript(str(path)) as transcript:
        assert [m["content"] for m in transcript.messages] == ["one", "two"]
        transcript.append({"role": "user", "content": "three"})
    assert [m["content"] for m in FileTranscript(str(path)).messages] == ["one", "two", "three"]
    assert not (tmp_path / "transcript.jsonl.torn").exists()


@pytest.mark.parametrize("tail", ["", "\n", "  "])
def test_a_file_ending_whole_is_left_as_it_is(tmp_path: Path, tail: str) -> None:
    path = tmp_path / "transcript.jsonl"
    path.write_text(_line("one") + tail)
    assert [m["content"] for m in FileTranscript(str(path)).messages] == ["one"]
    assert path.read_text() == _line("one") + tail and not (tmp_path / "transcript.jsonl.torn").exists()


@pytest.mark.parametrize(
    ("text", "number"),
    [
        pytest.param("not json\n" + _line("two"), 1, id="first"),
        pytest.param(_line("one") + "not json\n" + _line("three"), 2, id="middle"),
        pytest.param(_line("one") + "not json\n", 2, id="last, ended by a newline"),
        pytest.param(_line("one") + "\n" + "{oops\n" + _line("four"), 3, id="after a blank line"),
        pytest.param(_line("one") + "not json\n" + '{"role": "us', 2, id="damaged, then torn"),
    ],
)
def test_a_line_that_is_not_json_before_the_end_stops_the_transcript_naming_where_and_what_to_do(
    tmp_path: Path, text: str, number: int
) -> None:
    """Only an unfinished last line (no newline) is a write cut short; any other is damage the
    person must see, and nothing is cut or set aside."""
    path = tmp_path / "transcript.jsonl"
    path.write_text(text)
    with pytest.raises(ValueError, match=rf"transcript\.jsonl line {number} is not JSON") as stopped:
        FileTranscript(str(path))
    assert str(path) in str(stopped.value) and "--resume" in str(stopped.value)
    assert path.read_text() == text and [p.name for p in tmp_path.iterdir()] == ["transcript.jsonl"]


def test_a_last_line_that_is_not_utf_8_is_torn_too(tmp_path: Path) -> None:
    """What a crash leaves can be any bytes (zeros where the write never landed)."""
    path = tmp_path / "transcript.jsonl"
    path.write_bytes(_line("one").encode() + b'{"role": "us\xff\x00\x00')
    assert [m["content"] for m in FileTranscript(str(path)).messages] == ["one"]
    assert (tmp_path / "transcript.jsonl.torn").read_bytes() == b'{"role": "us\xff\x00\x00'


@pytest.mark.usefixtures("open_umask")
def test_rewrite_makes_the_new_file_and_the_backup_readable_by_their_owner_alone(tmp_path: Path) -> None:
    """Whatever mode the file had (an older session's, 0644), what `rewrite` makes is 0600, the
    new conversation and the old one kept beside it."""
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"role": "user", "content": "old"}) + "\n")
    path.chmod(0o644)
    backup = rewrite(str(path), SEED)
    assert (_mode(path), _mode(backup)) == (0o600, 0o600)
    assert Path(backup).read_text() == json.dumps({"role": "user", "content": "old"}) + "\n"
    again = rewrite(str(path), [])  # /clear: an empty conversation, the same
    assert (_mode(path), _mode(again)) == (0o600, 0o600) and path.read_text() == ""


@pytest.mark.usefixtures("open_umask")
def test_rewrite_narrows_a_new_file_a_crashed_rewrite_left_wider(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    path.write_text("{}\n")
    stale = tmp_path / "transcript.jsonl.new"
    stale.write_text("half of a conversation")
    stale.chmod(0o666)
    rewrite(str(path), SEED)
    assert _mode(path) == 0o600 and not stale.exists()  # the stale file was the one replaced


def test_rewrite_does_not_write_through_a_link_left_at_its_new_file(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    path.write_text("{}\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("not yours\n")
    (tmp_path / "transcript.jsonl.new").symlink_to(elsewhere)
    with pytest.raises(OSError):
        rewrite(str(path), SEED)
    assert elsewhere.read_text() == "not yours\n" and path.read_text() == "{}\n"
    assert not Path(f"{path}.bak").exists()
