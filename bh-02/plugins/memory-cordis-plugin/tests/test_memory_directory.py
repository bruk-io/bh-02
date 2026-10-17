"""The `memory` tool against a real directory: saved, read and deleted by name, MEMORY.md kept for
the tool's own lines and a person's left alone, and nothing outside the directory touched however
the model has left it (a link to a file outside among the cases)."""

import os
import threading
from pathlib import Path
from typing import Any

import pytest

from memory_cordis_plugin import AutoMemory, call, frontmatter, keep, understood

_DIRECTORY_SAVE: dict[str, Any] = {
    "action": "save",
    "name": "prefers-tabs",
    "type": "feedback",
    "description": "Tabs, not spaces",
    "body": "Use tabs.\n\n**Why:** the person said so.\n**How to apply:** every edit.",
}
_LINE = "- [prefers-tabs](prefers-tabs.md): Tabs, not spaces\n"


def _kept(directory: Path, **input: Any) -> str:
    """One call of the tool: understood, then kept; a refusal is its text."""
    asked = understood(input)
    return asked if isinstance(asked, str) else keep(directory, asked)


def _save(directory: Path, **changes: Any) -> str:
    return _kept(directory, **{**_DIRECTORY_SAVE, **changes})


@pytest.fixture
def memory(tmp_path: Path) -> Path:
    directory = tmp_path / "state" / "memory"
    directory.mkdir(parents=True)
    return directory


@pytest.fixture
def secret(tmp_path: Path) -> Path:
    """A file outside the memory directory that a link in it could lead to."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "id_test").write_text("FAKE-KEY")
    return outside / "id_test"


def test_a_save_writes_the_topic_file_and_its_line_in_the_index(memory: Path) -> None:
    said = _save(memory)
    assert said.startswith("saved the memory 'prefers-tabs'") and "MEMORY.md" in said
    said_front, body = frontmatter((memory / "prefers-tabs.md").read_text())
    assert said_front == {"name": "prefers-tabs", "description": "Tabs, not spaces", "type": "feedback"}
    assert body.strip() == _DIRECTORY_SAVE["body"]
    assert (memory / "MEMORY.md").read_text() == _LINE
    assert sorted(os.listdir(memory)) == ["MEMORY.md", "prefers-tabs.md"]  # no half-written file


def test_a_read_gives_the_memory_as_it_was_saved(memory: Path) -> None:
    _save(memory)
    said = _kept(memory, action="read", name="prefers-tabs")
    assert said == (memory / "prefers-tabs.md").read_text() and "**Why:**" in said
    assert _kept(memory, action="read", name="not-there").startswith("error: there is no memory named")


def test_a_save_under_a_name_that_exists_updates_that_memory_never_a_second_file(memory: Path) -> None:
    _save(memory)
    _save(memory, name="other", description="Another", body="x")
    said = _save(memory, description="Tabs, always", body="Changed.")
    assert said.startswith("updated the memory 'prefers-tabs'")
    assert sorted(os.listdir(memory)) == ["MEMORY.md", "other.md", "prefers-tabs.md"]
    assert (memory / "MEMORY.md").read_text() == (
        "- [prefers-tabs](prefers-tabs.md): Tabs, always\n- [other](other.md): Another\n"
    )
    assert frontmatter((memory / "prefers-tabs.md").read_text())[1].strip() == "Changed."


def test_a_delete_takes_out_the_topic_file_and_its_line(memory: Path) -> None:
    _save(memory)
    _save(memory, name="other", description="Another", body="x")
    said = _kept(memory, action="delete", name="prefers-tabs")
    assert said.startswith("deleted the memory 'prefers-tabs'")
    assert sorted(os.listdir(memory)) == ["MEMORY.md", "other.md"]
    assert (memory / "MEMORY.md").read_text() == "- [other](other.md): Another\n"
    assert _kept(memory, action="delete", name="prefers-tabs").startswith("error: there is no memory named")


def test_a_delete_of_a_memory_whose_file_is_gone_still_takes_its_line_out(memory: Path) -> None:
    _save(memory)
    (memory / "prefers-tabs.md").unlink()  # removed by hand, its line left behind
    said = _kept(memory, action="delete", name="prefers-tabs")
    assert said.startswith("deleted") and "no file" in said
    assert (memory / "MEMORY.md").read_text() == ""


def test_the_index_a_person_wrote_keeps_its_lines_through_a_save_and_a_delete(memory: Path) -> None:
    by_hand = (
        "# Notes\n"
        "Read these first.\n"
        "- [A page](https://example.com/page): points at no topic file\n"
        "- [Old](old.md): by hand, and old.md is not there\n"
    )
    (memory / "MEMORY.md").write_text(by_hand)
    _save(memory)
    assert (memory / "MEMORY.md").read_text() == by_hand + _LINE
    _kept(memory, action="delete", name="prefers-tabs")
    assert (memory / "MEMORY.md").read_text() == by_hand


def test_an_index_with_bytes_that_are_not_utf8_comes_back_as_it_was(memory: Path) -> None:
    (memory / "MEMORY.md").write_bytes(b"- caf\xe9 by hand\r\n")
    _save(memory)
    assert (memory / "MEMORY.md").read_bytes() == b"- caf\xe9 by hand\r\n" + _LINE.encode()


def test_a_refused_save_writes_nothing(memory: Path) -> None:
    for bad in ({"name": "Not A Slug"}, {"type": "note"}, {"description": "two\nlines"}, {"body": ""}):
        assert _save(memory, **bad).startswith("error: ")
    assert os.listdir(memory) == []


def test_a_memory_directory_that_is_not_there_is_an_error_the_model_reads(tmp_path: Path) -> None:
    gone = tmp_path / "gone"
    for said in (_save(gone), _kept(gone, action="read", name="x"), _kept(gone, action="delete", name="x")):
        assert said.startswith("error: ") and str(gone) in said
    assert not gone.exists()


def test_a_link_in_place_of_the_index_is_refused_before_anything_is_written(
    memory: Path, secret: Path
) -> None:
    (memory / "MEMORY.md").symlink_to(secret)
    said = _save(memory)
    assert said.startswith("error: ") and "MEMORY.md" in said and "link" in said
    assert secret.read_text() == "FAKE-KEY" and "FAKE" not in said
    assert (memory / "MEMORY.md").is_symlink() and os.listdir(memory) == ["MEMORY.md"]  # no topic file either
    assert _kept(memory, action="delete", name="x").startswith("error: ")
    assert secret.read_text() == "FAKE-KEY"


def test_a_second_name_for_the_index_is_refused(memory: Path, secret: Path) -> None:
    os.link(secret, memory / "MEMORY.md")
    said = _save(memory)
    assert said.startswith("error: ") and "MEMORY.md" in said and "one name" in said
    assert secret.read_text() == "FAKE-KEY" and os.listdir(memory) == ["MEMORY.md"]


def test_a_link_in_place_of_a_topic_file_is_neither_written_through_read_nor_removed(
    memory: Path, secret: Path
) -> None:
    (memory / "prefers-tabs.md").symlink_to(secret)
    said = _save(memory)
    assert said.startswith("error: ") and "prefers-tabs.md" in said and "link" in said
    assert secret.read_text() == "FAKE-KEY"
    assert not (memory / "MEMORY.md").exists()  # no line for a memory that was not saved
    read = _kept(memory, action="read", name="prefers-tabs")
    assert read.startswith("error: ") and "FAKE" not in read
    assert _kept(memory, action="delete", name="prefers-tabs").startswith("error: ")
    assert (memory / "prefers-tabs.md").is_symlink() and secret.read_text() == "FAKE-KEY"


def test_a_link_to_a_file_that_is_not_there_yet_is_not_created_through(memory: Path, tmp_path: Path) -> None:
    planted = tmp_path / "outside" / "planted"
    planted.parent.mkdir()
    (memory / "prefers-tabs.md").symlink_to(planted)
    assert _save(memory).startswith("error: ")
    assert not planted.exists()


def test_a_second_name_for_a_topic_file_is_refused_and_not_read(memory: Path, secret: Path) -> None:
    os.link(secret, memory / "prefers-tabs.md")
    assert _save(memory).startswith("error: ")
    read = _kept(memory, action="read", name="prefers-tabs")
    assert read.startswith("error: ") and "FAKE" not in read
    assert secret.read_text() == "FAKE-KEY"


def test_a_directory_in_place_of_a_topic_file_is_refused(memory: Path) -> None:
    (memory / "prefers-tabs.md").mkdir()
    assert _save(memory).startswith("error: ")
    assert _kept(memory, action="read", name="prefers-tabs").startswith("error: ")


def test_a_link_in_place_of_the_memory_directory_s_parent_is_the_caller_s_to_trust(
    tmp_path: Path, memory: Path
) -> None:
    """The directory is bh-02's own, made by the command line and named as it is: only what is
    beneath it is judged."""
    (tmp_path / "named").symlink_to(memory)
    _save(tmp_path / "named")
    assert (memory / "prefers-tabs.md").exists()


async def test_the_tool_answers_a_call_off_the_event_loop_with_its_text_as_the_content(memory: Path) -> None:
    saved = await call(memory, _DIRECTORY_SAVE)
    assert set(saved) == {"content"} and str(saved["content"]).startswith("saved the memory")
    refused = await call(memory, {**_DIRECTORY_SAVE, "name": "Bad Name"})
    assert str(refused["content"]).startswith("error: ")
    assert sorted(os.listdir(memory)) == ["MEMORY.md", "prefers-tabs.md"]
    read = await call(memory, {"action": "read", "name": "prefers-tabs"})
    assert "Use tabs." in str(read["content"])


async def test_the_next_conversation_s_prompt_lists_a_saved_memory_in_the_index(memory: Path) -> None:
    before = AutoMemory(memory, "/m")()
    assert "MEMORY.md is not there yet" in before
    await call(memory, _DIRECTORY_SAVE)
    assert _LINE.strip() not in before  # this conversation's prompt is fixed
    assert _LINE.strip() in AutoMemory(memory, "/m")()  # the next one reads the index afresh
    await call(memory, {"action": "delete", "name": "prefers-tabs"})
    assert "prefers-tabs" not in AutoMemory(memory, "/m")()


async def test_the_tool_works_in_a_thread_of_its_own_so_a_save_never_blocks_the_event_loop(
    memory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where: list[int] = []
    real = keep

    def spy(directory: Path, asked: Any) -> str:
        where.append(threading.get_ident())
        return real(directory, asked)

    monkeypatch.setattr("memory_cordis_plugin.directory.keep", spy)
    await call(memory, _DIRECTORY_SAVE)
    assert where and where != [threading.get_ident()]
