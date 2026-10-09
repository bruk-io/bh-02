"""Auto memory: how the model is told to keep it, its index as it is told, read once a
conversation through no link, and the row that adds it to the system prompt."""

import os
from pathlib import Path

from cordis.testing import drive
from memory_cordis_plugin import AutoMemory, Memory, MemoryConfig, auto, auto_section, indexed, listing


def test_the_index_is_told_to_200_lines_or_25kb_whichever_ends_first() -> None:
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


async def test_the_row_adds_the_section_and_adds_nothing_without_a_directory(tmp_path: Path) -> None:
    prompt = _Prompt()
    effects = await drive(auto(system=prompt, host=_Host(str(tmp_path)), transcript=object()))
    assert [(e.name, e.args[0]) for e in effects] == [("acquire", prompt.add)]
    assert effects[0].args[1] == "memory: auto" and isinstance(effects[0].args[2], AutoMemory)
    assert await drive(auto(system=prompt, host=_Host(""), transcript=object())) == []


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
