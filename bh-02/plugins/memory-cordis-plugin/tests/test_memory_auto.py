"""Auto memory: how the model is told to keep it, its index as it is told, read once a
conversation through no link, and the row that adds it to the system prompt."""

import os
from pathlib import Path

import pytest

from cordis.testing import drive
from memory_cordis_plugin import (
    MEMORY,
    AutoMemory,
    Memory,
    MemoryConfig,
    auto,
    auto_section,
    indexed,
    listing,
)


def test_the_index_is_told_to_200_lines_or_25_kb_whichever_ends_first() -> None:
    short = "\n".join(f"- line {n}" for n in range(10))
    assert indexed(short) == (short, False)
    long = "\n".join(f"- line {n}" for n in range(300))
    told, cut = indexed(long)
    assert cut and told.splitlines()[-1] == "- line 199" and len(told.splitlines()) == 200
    wide = "\n".join("x" * 1_000 for _ in range(100))
    told, cut = indexed(wide)
    assert cut and len(told.encode()) <= 25 * 1024 and all(len(line) == 1_000 for line in told.splitlines())


def test_the_model_is_told_how_to_keep_it_and_where() -> None:
    said = auto_section("~/.local/state/bh-02/projects/-p/memory", None, False)
    assert said.startswith("Auto memory: ~/.local/state/bh-02/projects/-p/memory is a directory of your own")
    assert "`user`" in said and "`feedback`" in said and "`project`" in said and "`reference`" in said
    assert said.endswith("MEMORY.md is not there yet.")
    told = auto_section("/m", "- [Testing](testing.md): run the suite with -x", True)
    assert "Contents of /m/MEMORY.md (your auto memory index):\n\n- [Testing](testing.md)" in told
    assert told.endswith("one line per memory, the detail in topic files.)")


@pytest.mark.parametrize(
    "phrase",
    [
        pytest.param("with the `memory` tool, not by writing files there", id="keep-it-with-the-tool"),
        pytest.param("`save` writes one memory by name", id="save"),
        pytest.param("`read` and `delete` take the name", id="read-and-delete"),
        pytest.param(
            "save under its name to update it rather than add a duplicate", id="check-for-existing-first"
        ),
        pytest.param("**Why:** line", id="feedback-and-project-why"),
        pytest.param("**How to apply:** line", id="feedback-and-project-how-to-apply"),
        pytest.param("absolute ones (2026-10-14)", id="absolute-dates"),
        pytest.param("one specific line", id="specific-description"),
        pytest.param("only matters to this conversation", id="not-this-conversation"),
        pytest.param("what was non-obvious about it", id="asked-for-what-is-not-recorded"),
        pytest.param("against the code or git log before you recommend it", id="check-against-the-code"),
        pytest.param("under 200 lines and 4 KB", id="short-memory-files"),
        pytest.param(
            "organised by topic: split or summarise one that outgrows that", id="organised-by-topic"
        ),
    ],
)
def test_the_model_is_told_each_rule_for_keeping_memories(phrase: str) -> None:
    assert phrase in auto_section("/m", None, False)


def test_the_rule_about_what_other_places_record_is_said_once_and_the_cap_is_spelled_one_way() -> None:
    said = auto_section("/m", None, False)
    assert said.count("the code, its history or CLAUDE.md already records") == 1
    assert said.count("its history") == 1
    assert "KB" in said and "KB)" not in said and "25KB" not in said and "4KB" not in said


def test_the_model_is_not_told_to_write_the_files_itself() -> None:
    """Saves go through the tool, which makes the file and its line in the index: the prompt no
    longer describes the file layout for the model to follow."""
    said = auto_section("/m", None, False)
    assert "frontmatter" not in said and "topic file" not in said


def test_the_index_is_read_once_a_conversation(tmp_path: Path) -> None:
    """Read at the first reading of the prompt and kept: the model's own write to it later in the
    conversation is not told back to it as a change in its instructions."""
    (tmp_path / "MEMORY.md").write_text("- first")
    section = AutoMemory(tmp_path, "/m")
    assert "- first" in section()
    (tmp_path / "MEMORY.md").write_text("- second")
    assert "- first" in section() and "- second" not in section()
    assert "- second" in AutoMemory(tmp_path, "/m")()  # a new conversation's row reads it afresh


def test_an_index_the_model_made_a_link_or_a_second_name_is_not_read(tmp_path: Path) -> None:
    """The model writes the directory, so the index is read from it through no link."""
    directory, secret = tmp_path / "memory", tmp_path / "id_test"
    directory.mkdir()
    secret.write_text("FAKE-KEY")
    (directory / "MEMORY.md").symlink_to(secret)
    said = AutoMemory(directory, "/m")()
    assert "FAKE" not in said and "(bh-02 did not read MEMORY.md:" in said
    (directory / "MEMORY.md").unlink()
    os.link(secret, directory / "MEMORY.md")
    assert "FAKE" not in AutoMemory(directory, "/m")()


class _Host:
    def __init__(self, auto_memory: str) -> None:
        self.auto_memory = auto_memory


class _Prompt:
    def add(self, name: str, section: object) -> object:
        return lambda: None


class _Tools:
    def register(self, spec: object, run: object, *, runs: str) -> object:
        return lambda: None


async def test_the_row_adds_the_section_and_the_tool_and_nothing_without_a_directory(tmp_path: Path) -> None:
    prompt, tools = _Prompt(), _Tools()
    effects = await drive(auto(system=prompt, host=_Host(str(tmp_path)), transcript=object(), tools=tools))
    assert [(e.name, e.args[0]) for e in effects] == [("acquire", prompt.add), ("acquire", tools.register)]
    assert effects[0].args[1] == "memory: auto" and isinstance(effects[0].args[2], AutoMemory)
    assert effects[1].args[1] is MEMORY and effects[1].kwargs == {"runs": "memory"}
    assert await drive(auto(system=prompt, host=_Host(""), transcript=object(), tools=tools)) == []


async def test_the_tool_the_row_registers_keeps_the_directory_the_host_names(tmp_path: Path) -> None:
    effects = await drive(
        auto(system=_Prompt(), host=_Host(str(tmp_path)), transcript=object(), tools=_Tools())
    )
    run = effects[1].args[2]
    said = await run({"action": "save", "name": "a-fact", "type": "user", "description": "d", "body": "b"})
    assert str(said["content"]).startswith("saved the memory 'a-fact'")
    assert (tmp_path / "a-fact.md").is_file() and (tmp_path / "MEMORY.md").is_file()
    read = await run({"action": "read", "name": "a-fact"})
    assert str(read["content"]).endswith("b\n")


def test_memory_lists_the_index(tmp_path: Path) -> None:
    root, home, directory = tmp_path / "project", tmp_path / "home", tmp_path / "memory"
    for d in (root, home, directory):
        d.mkdir()
    found = Memory(
        MemoryConfig(root=str(root), home=str(home), managed=str(tmp_path / "none")), str(directory)
    )
    said = listing(found.listed(), root.resolve(), home.resolve(), "claude-md-or-agents-md")
    assert f"  · {directory}/MEMORY.md: the model's auto memory index" in said
    (directory / "MEMORY.md").write_text("- one")
    assert found.text() == ""  # the memory-auto row's section, not this one's
    assert f"  ✓ {directory}/MEMORY.md" in listing(
        found.listed(), root.resolve(), home.resolve(), "claude-md"
    )
