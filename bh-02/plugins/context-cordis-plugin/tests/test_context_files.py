"""The context files: their sections, whom they trust, and the project context they make."""

import os
import sys
from pathlib import Path

import pytest

from context_cordis_plugin import ContextConfig, ContextFiles, ProjectContext, parse

_NAMED = "context_cordis_plugin.sections:named"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _context(tmp_path: Path, **config: object) -> tuple[ProjectContext, Path, Path]:
    home, root = tmp_path / "home", tmp_path / "project"
    home.mkdir(exist_ok=True)
    root.mkdir(exist_ok=True)
    return ProjectContext(ContextConfig(root=str(root), home=str(home), **config)), root, home  # type: ignore[arg-type]


def test_a_section_is_files_and_a_function() -> None:
    sections, replace = parse(
        '[[section]]\nfiles = ["A.md", "**/A.md"]\nfunction = "context_cordis_plugin.sections:place"\n'
        f'[[section]]\nfunction = "{_NAMED}"\n',
        "f.toml",
        trusted=False,
    )
    assert [(s.files, s.function) for s in sections] == [
        (("A.md", "**/A.md"), "context_cordis_plugin.sections:place"),
        ((), "context_cordis_plugin.sections:named"),
    ]
    assert replace is False and parse("replace = true", "f", trusted=True) == ((), True)
    with pytest.raises(ValueError, match=r"is `files` \(patterns from the project's root\) and `function`"):
        parse('[[section]]\nfiles = ["A.md"]\nuse = "place"\n', "f.toml", trusted=True)
    with pytest.raises(ValueError, match="may hold only"):
        parse("order = 1", "f.toml", trusted=True)


def test_the_project_s_file_may_name_only_bh_02_s_own_functions() -> None:
    """The model can write the project's file, and its functions run in bh-02, outside the jail."""
    with pytest.raises(ValueError, match="may name only bh-02's own functions") as raised:
        parse('[[section]]\nfunction = "os:system"\n', ".bh-02/context.toml", trusted=False)
    assert "~/.config/bh-02/context.toml" in str(raised.value)  # says where one of yours goes
    assert (
        parse('[[section]]\nfunction = "os:system"\n', "mine.toml", trusted=True)[0][0].function
        == "os:system"
    )


def test_bh_02_s_own_file_reads_the_guidance_and_the_rules(tmp_path: Path) -> None:
    context, root, home = _context(tmp_path)
    _write(home / "AGENTS.md", "Mine.")
    _write(root / "CLAUDE.md", "The project's.")
    _write(root / "src/engine/CLAUDE.md", "Engine.")
    _write(root / "node_modules/pkg/CLAUDE.md", "Theirs.")  # where tools keep things: not searched
    _write(root / ".claude/rules/testing.md", "Run pytest -q.")  # a pattern naming a hidden directory
    text = context.text()
    assert (
        text.index("Working directory:")
        < text.index("From ~/AGENTS.md:\n\nMine.")
        < text.index("From CLAUDE.md")
    )
    assert "src/engine/CLAUDE.md" in text and "node_modules" not in text
    assert "From .claude/rules/testing.md:\n\nRun pytest -q." in text


def test_your_file_adds_a_section_of_your_own_and_an_edit_reaches_the_next_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, root, home = _context(tmp_path)
    _write(
        tmp_path / "lib" / "mine.py",
        "def shout(files, *, root, home):\n    return 'SHOUT: ' + ', '.join(f.name for f in files)\n",
    )
    monkeypatch.syspath_prepend(str(tmp_path / "lib"))
    _write(root / "NOTES.md", "n")
    assert "SHOUT" not in context.text()
    mine = _write(
        home / ".config/bh-02/context.toml", '[[section]]\nfiles = ["NOTES.md"]\nfunction = "mine:shout"\n'
    )
    assert context.text().endswith("SHOUT: NOTES.md")  # read again, now that it is there
    mine.write_text(f'replace = true\n[[section]]\nfiles = ["NOTES.md"]\nfunction = "{_NAMED}"\n')
    text = context.text()
    assert "SHOUT" not in text and text.endswith("Files to read when they bear on your work: NOTES.md.")
    sys.modules.pop("mine", None)


def test_a_project_file_naming_another_function_is_refused_and_says_so(tmp_path: Path) -> None:
    context, root, _ = _context(tmp_path)
    _write(root / ".bh-02/context.toml", '[[section]]\nfiles = ["x"]\nfunction = "shutil:rmtree"\n')
    text = context.text()
    assert "(bh-02 could not read the context file" in text and "may name only bh-02's own functions" in text


def test_a_section_that_fails_says_so_and_the_rest_still_say_theirs(tmp_path: Path) -> None:
    context, root, home = _context(tmp_path)
    _write(root / "AGENTS.md", "Still here.")
    _write(
        home / ".config/bh-02/context.toml",
        '[[section]]\nfunction = "context_cordis_plugin.sections:nothing"\n',
    )
    text = context.text()
    assert "(bh-02 could not make the section context_cordis_plugin.sections:nothing:" in text
    assert "From AGENTS.md:\n\nStill here." in text


def test_a_file_a_wildcard_matches_is_found_at_the_next_reading_added_or_removed(tmp_path: Path) -> None:
    files, root = ContextFiles((".bh-02/context.toml",), 20_000), tmp_path
    _write(
        root / ".bh-02/context.toml",
        'replace = true\n[[section]]\nfiles = ["docs/**/*.md", ".claude/rules/*.md"]\n'
        f'function = "{_NAMED}"\n',
    )
    _write(root / "docs/a.md", "a")
    assert files.text(root, tmp_path).endswith("docs/a.md.")
    _write(root / "docs/b.md", "b")
    _write(root / "docs/deep/c.md", "c")  # in a directory that was not there to look in
    assert files.text(root, tmp_path).endswith("docs/a.md, docs/b.md, docs/deep/c.md.")
    (root / "docs/a.md").unlink()
    assert files.text(root, tmp_path).endswith("docs/b.md, docs/deep/c.md.")
    _write(root / ".claude/rules/new.md", "r")  # under directories that were not there at all
    assert ".claude/rules/new.md" in files.text(root, tmp_path)


def test_a_search_looks_again_only_when_a_directory_it_looked_in_changed(tmp_path: Path) -> None:
    """Each reading costs a `stat` of each directory looked in, not a walk: shown by a file whose
    directory's time is put back, which the search does not see."""
    files, root = ContextFiles((".bh-02/context.toml",), 20_000), tmp_path
    _write(
        root / ".bh-02/context.toml",
        f'replace = true\n[[section]]\nfiles = ["docs/*.md"]\nfunction = "{_NAMED}"\n',
    )
    _write(root / "docs/a.md", "a")
    files.text(root, tmp_path)
    was = (root / "docs").stat()
    _write(root / "docs/hidden.md", "h")
    os.utime(root / "docs", ns=(was.st_atime_ns, was.st_mtime_ns))
    assert "hidden.md" not in files.text(root, tmp_path)


def test_the_context_files_say_at_most_max_chars(tmp_path: Path) -> None:
    context, root, _ = _context(tmp_path, max_chars=40)
    _write(root / "AGENTS.md", "x" * 500)
    assert "more chars of project context]" in context.text()
