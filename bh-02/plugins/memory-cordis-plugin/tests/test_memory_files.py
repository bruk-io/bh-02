"""The memory files, found and told as Claude Code finds and tells them, in a temporary home and
project, with a managed policy of the test's own."""

import os
from pathlib import Path

import pytest

from memory_cordis_plugin import Memory, MemoryConfig, listing


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _memory(tmp_path: Path, root: Path | None = None, **config: object) -> tuple[Memory, Path, Path]:
    home = tmp_path / "home"
    root = root or tmp_path / "project"
    home.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    managed = str(tmp_path / "managed" / "CLAUDE.md")
    found = Memory(MemoryConfig(root=str(root), home=str(home), managed=managed, **config))  # type: ignore[arg-type]
    return found, root.resolve(), home.resolve()


def _order(text: str) -> list[str]:
    """Each file the prompt's section tells, in order."""
    return [
        line.removeprefix("Contents of ").split(" (")[0]
        for line in text.splitlines()
        if line.startswith("Contents of ")
    ]


def test_launch_reads_broadest_first(tmp_path: Path) -> None:
    """The managed policy, yours (CLAUDE.md, then your rules), each directory from the top down to
    the project's (its CLAUDE.md, its .claude/CLAUDE.md, the project's rules, its CLAUDE.local.md)."""
    found, root, home = _memory(tmp_path, tmp_path / "work" / "project")
    _write(tmp_path / "managed/CLAUDE.md", "Policy.")
    _write(home / ".claude/CLAUDE.md", "Mine.")
    _write(home / ".claude/rules/style.md", "My style.")
    _write(tmp_path / "work/CLAUDE.md", "For all work.")
    _write(root / "CLAUDE.md", "Project.")
    _write(root / ".claude/CLAUDE.md", "Project, in .claude.")
    _write(root / ".claude/rules/testing.md", "Test first.")
    _write(root / "CLAUDE.local.md", "Mine, here.")
    text = found.text()
    work = str((tmp_path / "work").resolve())
    assert _order(text) == [
        str(tmp_path / "managed/CLAUDE.md"),
        "~/.claude/CLAUDE.md",
        "~/.claude/rules/style.md",
        f"{work}/CLAUDE.md",
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        ".claude/rules/testing.md",
        "CLAUDE.local.md",
    ]
    assert "Contents of CLAUDE.md (project instructions, checked into the codebase):\n\nProject." in text
    assert f"({'instructions for everything under ' + work}/)" in text
    assert text.startswith("Memory: what the person and the project keep") and "written for you" in text
    assert "Claude Code" not in text.split("\n\n")[0]  # the preface names no other harness


def test_nothing_to_tell_is_no_section(tmp_path: Path) -> None:
    found, _, _ = _memory(tmp_path)
    assert found.text() == ""


def test_agents_md_is_read_only_where_no_claude_md_is_by_default(tmp_path: Path) -> None:
    found, root, home = _memory(tmp_path)
    _write(root / "AGENTS.md", "For any agent.")
    _write(home / ".claude/CLAUDE.md", "Mine: does not count.")
    assert "For any agent." in found.text()
    _write(root / "CLAUDE.local.md", "Mine, here: counts.")
    assert "For any agent." not in found.text()
    skipped = [e for e in found.listed() if e.state == "skipped"]
    assert [e.source.path for e in skipped] == [root / "AGENTS.md"]


@pytest.mark.parametrize(
    ("instruction_files", "told"),
    [
        ("claude-md-or-agents-md", ["CLAUDE.md", ".claude/rules/r.md"]),
        ("claude-md-and-agents-md", ["CLAUDE.md", ".claude/rules/r.md", "AGENTS.md"]),
        ("claude-md", ["CLAUDE.md", ".claude/rules/r.md"]),
        ("managed-only", []),
    ],
)
def test_instruction_files_choose_what_loads(tmp_path: Path, instruction_files: str, told: list[str]) -> None:
    """As Claude Code's Project instructions setting: the managed policy always, the rest as named."""
    found, root, _ = _memory(tmp_path, instruction_files=instruction_files)
    _write(tmp_path / "managed/CLAUDE.md", "Policy.")
    _write(root / "CLAUDE.md", "C.")
    _write(root / "AGENTS.md", "A.")
    _write(root / ".claude/rules/r.md", "R.")
    assert _order(found.text()) == [str(tmp_path / "managed/CLAUDE.md"), *told]


def test_imports_follow_their_file_up_to_four_hops(tmp_path: Path) -> None:
    found, root, home = _memory(tmp_path)
    _write(root / "CLAUDE.md", "See @docs/one.md and `@docs/not.md`.")
    for n, name in enumerate(("one", "two", "three", "four", "five")):
        following = ("two", "three", "four", "five", "six")[n]
        _write(root / f"docs/{name}.md", f"{name.title()}. Next: @{following}.md")
    _write(root / "docs/six.md", "Six.")
    _write(root / "docs/not.md", "Not imported.")
    told = _order(found.text())
    assert told == ["CLAUDE.md", "docs/one.md", "docs/two.md", "docs/three.md", "docs/four.md"]
    _write(home / "mine.md", "Mine, from home.")
    _write(home / ".claude/CLAUDE.md", "Mine: @~/mine.md")
    assert "Mine, from home." in found.text()  # yours may import from anywhere


def test_an_import_that_loops_is_read_once(tmp_path: Path) -> None:
    found, root, _ = _memory(tmp_path)
    _write(root / "CLAUDE.md", "@a.md")
    _write(root / "a.md", "A. @CLAUDE.md @b.md")
    _write(root / "b.md", "B. @a.md")
    assert _order(found.text()) == ["CLAUDE.md", "a.md", "b.md"]


def test_a_project_file_imports_nothing_outside_the_project(tmp_path: Path) -> None:
    """The model can write the project's CLAUDE.md, and an import out of the project would hand it
    a file the jail hides. Claude Code asks; bh-02 does not follow it, and says why."""
    found, root, home = _memory(tmp_path)
    _write(home / ".ssh/id_test", "FAKE-KEY")
    _write(root / "CLAUDE.md", "@~/.ssh/id_test and @../outside.md")
    _write(tmp_path / "outside.md", "FAKE-OUTSIDE")
    text = found.text()
    assert "FAKE" not in text
    assert "(bh-02 did not import ~/.ssh/id_test: CLAUDE.md is in the project" in text
    _write(root / "local.env", "FAKE-ENV")
    _write(root / "CLAUDE.md", "@local.env")
    assert "FAKE" not in found.text()


def test_comments_are_taken_out(tmp_path: Path) -> None:
    found, root, _ = _memory(tmp_path)
    _write(root / "CLAUDE.md", "Keep.\n<!-- for maintainers: @secret.md -->\nAlso.")
    _write(root / "secret.md", "Never imported.")
    text = found.text()
    assert "Keep.\nAlso." in text and "maintainers" not in text and "Never imported" not in text


def test_excludes_leave_files_out_but_never_the_managed_policy(tmp_path: Path) -> None:
    found, root, _ = _memory(
        tmp_path, tmp_path / "mono" / "project", excludes=["**/mono/CLAUDE.md", "**/managed/*"]
    )
    _write(tmp_path / "managed/CLAUDE.md", "Policy.")
    _write(tmp_path / "mono/CLAUDE.md", "Another team's.")
    _write(root / "CLAUDE.md", "Ours.")
    text = found.text()
    assert "Another team's." not in text and "Ours." in text and "Policy." in text
    assert [
        e.state
        for e in found.listed()
        if e.source.path.name == "CLAUDE.md" and "mono/CLAUDE" in str(e.source.path)
    ] == ["excluded"]


def test_a_rule_with_paths_waits_for_a_file_it_matches(tmp_path: Path) -> None:
    found, root, _ = _memory(tmp_path)
    _write(root / ".claude/rules/db.md", "---\npaths: src/db/**\n---\nMigrations by hand.")
    assert found.text() == ""
    [entry] = [e for e in found.listed() if e.source.kind == "rule"]
    assert (entry.state, entry.why) == ("on demand", "src/db/**")


def test_a_link_the_model_made_reads_nothing(tmp_path: Path) -> None:
    """A link in the project to a secret, or a second name for one, reads nothing; a CLAUDE.md
    linking to the AGENTS.md beside it is read, once."""
    found, root, home = _memory(tmp_path, instruction_files="claude-md-and-agents-md")
    key = _write(home / ".ssh/id_test", "FAKE-KEY")
    (root / "CLAUDE.local.md").symlink_to(key)
    os.link(_write(tmp_path / "hidden.txt", "FAKE-HIDDEN"), root / ".claude.md")
    _write(root / ".claude/CLAUDE.md", "@../.claude.md")
    _write(root / "AGENTS.md", "The project's.")
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    text = found.text()
    assert "FAKE" not in text and text.count("The project's.") == 1


def test_a_subdirectory_s_memory_loads_when_an_input_opens_a_file_under_it(tmp_path: Path) -> None:
    """Broadest first: a subdirectory's CLAUDE.md and CLAUDE.local.md, its own `.claude/rules/`
    (one without `paths` for everything under it; one with them from that directory), then each
    rule whose `paths` match, yours and the project's."""
    found, root, home = _memory(tmp_path)
    _write(root / "src/CLAUDE.md", "Src.")
    _write(root / "src/db/CLAUDE.md", "Db. @notes.md")
    _write(root / "src/db/notes.md", "Db notes.")
    _write(root / "src/db/CLAUDE.local.md", "Mine, for db.")
    _write(root / "src/db/.claude/rules/all.md", "Every db file.")
    _write(root / "src/db/.claude/rules/models.md", "---\npaths: models.py\n---\nModels.")
    _write(root / ".claude/rules/db.md", "---\npaths: src/db/**\n---\nMigrations by hand.")
    _write(root / ".claude/rules/web.md", "---\npaths: web/**\n---\nNot this.")
    _write(root / ".claude/rules/always.md", "At launch, not here.")
    _write(home / ".claude/rules/py.md", "---\npaths: '*.py'\n---\nMy Python.")
    told = dict(found.touched([str(root / "src/db/models.py")]))
    assert list(told) == [
        str(root / "src/CLAUDE.md"),
        str(root / "src/db/CLAUDE.md"),
        str(root / "src/db/CLAUDE.local.md"),
        str(root / "src/db/.claude/rules/all.md"),
        str(root / "src/db/.claude/rules/models.md"),
        str(home / ".claude/rules/py.md"),
        str(root / ".claude/rules/db.md"),
    ]
    assert told[str(root / "src/db/CLAUDE.md")] == (
        "From src/db/CLAUDE.md, instructions for work under src/db/:\n\nDb. @notes.md\n\n"
        "From src/db/notes.md, imported by src/db/CLAUDE.md:\n\nDb notes."
    )
    assert (
        told[str(root / ".claude/rules/db.md")]
        == "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand."
    )
    assert told[str(root / "src/db/.claude/rules/all.md")].startswith(
        "From src/db/.claude/rules/all.md, a rule for work under src/db/:"
    )
    assert found.touched([str(tmp_path / "elsewhere.py"), str(root / "README.txt")]) == []


def test_a_subdirectory_s_agents_md_loads_where_it_has_no_claude_md(tmp_path: Path) -> None:
    found, root, _ = _memory(tmp_path)
    _write(root / "a/AGENTS.md", "A agents.")
    _write(root / "b/AGENTS.md", "B agents.")
    _write(root / "b/CLAUDE.md", "B claude.")
    told = dict(found.touched([str(root / "a/x.py"), str(root / "b/x.py")]))
    assert list(told) == [str(root / "a/AGENTS.md"), str(root / "b/CLAUDE.md")]
    _write(root / "CLAUDE.md", "The project's: AGENTS.md is not read anywhere now.")
    assert list(dict(found.touched([str(root / "a/x.py")]))) == []


def test_memory_lists_every_file_and_how_it_loads(tmp_path: Path) -> None:
    found, root, home = _memory(tmp_path)
    _write(root / "CLAUDE.md", "Project. @gone.md @~/far.md")
    _write(root / ".claude/rules/db.md", "---\npaths: src/db/**\n---\nx")
    _write(root / "AGENTS.md", "x")
    _write(home / "far.md", "far")
    said = listing(found.listed(), root, home, "claude-md-or-agents-md")
    assert said.startswith("Memory, as Claude Code reads it (instruction files: claude-md-or-agents-md):")
    assert "  · ~/.claude/CLAUDE.md: the person's own instructions, for every project (not there)" in said
    assert "  ✓ CLAUDE.md: project instructions, checked into the codebase" in said
    assert "  ✗ ~/far.md: imported by CLAUDE.md (not read: CLAUDE.md is in the project" in said
    assert "  … .claude/rules/db.md: a project rule for src/db/**, told when an input first opens one" in said
    assert "  – AGENTS.md: project instructions for any agent (not read: a CLAUDE.md is there" in said
    assert "managed" not in said  # none on this machine


def test_a_config_that_can_t_be_used_says_what_to_write() -> None:
    with pytest.raises(ValueError, match="`instruction_files` is one of claude-md-or-agents-md"):
        MemoryConfig(instruction_files="both")
    with pytest.raises(TypeError, match="`excludes` is a list of globs"):
        MemoryConfig(excludes="**/CLAUDE.md")
