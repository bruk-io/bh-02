"""The context files: their sections, whom they trust, and the project context they make."""

import os
import sys
from pathlib import Path

import pytest

from context_cordis_plugin import ContextConfig, ContextFiles, ProjectContext, parse

_NAMED = "context_cordis_plugin.sections:named"
_WHOLE = "context_cordis_plugin.sections:whole"


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
    # says where one of yours goes, as the models file's docs do
    assert "$XDG_CONFIG_HOME/bh-02/context.toml (else ~/.config/bh-02/context.toml)" in str(raised.value)
    assert (
        parse('[[section]]\nfunction = "os:system"\n', "mine.toml", trusted=True)[0][0].function
        == "os:system"
    )


def test_the_project_s_file_may_name_only_files_in_it_and_only_add() -> None:
    """Whatever the project's file names, bh-02 reads outside the jail, so it names no file the
    jail keeps from the model: none outside the project, none hidden; and it cannot drop yours."""
    for pattern in ("../local.env", "~/.ssh/id_rsa", "/etc/passwd", ".git/config", "docs/.private/*.md"):
        toml = f'[[section]]\nfiles = ["{pattern}"]\nfunction = "{_NAMED}"\n'
        with pytest.raises(ValueError, match="may name only files in the project that are not hidden"):
            parse(toml, ".bh-02/context.toml", trusted=False)
        assert parse(toml, "mine.toml", trusted=True)[0][0].files == (pattern,)
    with pytest.raises(ValueError, match="may only add sections, not `replace` yours"):
        parse("replace = true", ".bh-02/context.toml", trusted=False)


def test_nothing_is_read_through_a_section_that_the_model_could_not_read(tmp_path: Path) -> None:
    """A link the model makes in the project, or a secret's name, reads nothing; a link from one
    guidance file to another, or one of the person's own outside the project, still reads."""
    context, root, home = _context(tmp_path)
    _write(tmp_path / "local.env", "FAKE-BESIDE")
    _write(home / ".ssh/id_test", "FAKE-KEY")
    _write(root / "local.env", "FAKE-INSIDE")
    (root / "CLAUDE.local.md").symlink_to("../local.env")
    (root / "AGENTS.local.md").symlink_to(home / ".ssh/id_test")
    _write(root / "src/AGENTS.md", "x")
    (root / "src/CLAUDE.md").symlink_to(home / ".ssh/id_test")  # where the search finds it
    _write(root / "AGENTS.md", "The project's.")
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    _write(home / "dotfiles/AGENTS.md", "Mine, kept in my dotfiles.")
    (home / "AGENTS.md").symlink_to(home / "dotfiles/AGENTS.md")
    _write(
        home / ".config/bh-02/context.toml", f'[[section]]\nfiles = ["local.env"]\nfunction = "{_WHOLE}"\n'
    )
    text = context.text()
    assert "FAKE" not in text
    assert "src/CLAUDE.md" not in text and "src/AGENTS.md" in text
    assert "From AGENTS.md:\n\nThe project's." in text and "Mine, kept in my dotfiles." in text


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


def _yours_and_the_other(root: Path, xdg: Path, dot_config: Path) -> None:
    """A context file of yours in each place it could be, each saying which it is."""
    _write(root / "XDG.md", "The one in XDG_CONFIG_HOME.")
    _write(root / "DOT.md", "The one in ~/.config.")
    _write(xdg / "bh-02/context.toml", f'[[section]]\nfiles = ["XDG.md"]\nfunction = "{_WHOLE}"\n')
    _write(dot_config / "bh-02/context.toml", f'[[section]]\nfiles = ["DOT.md"]\nfunction = "{_WHOLE}"\n')


def test_your_file_is_in_xdg_config_home_when_it_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As the models file is: `$XDG_CONFIG_HOME/bh-02/context.toml`, and then not ~/.config's."""
    context, root, home = _context(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _yours_and_the_other(root, tmp_path / "xdg", home / ".config")
    text = context.text()
    assert "From XDG.md:\n\nThe one in XDG_CONFIG_HOME." in text and "DOT.md" not in text


@pytest.mark.parametrize("xdg", [None, ""], ids=["unset", "empty"])
def test_your_file_is_in_your_home_s_config_when_xdg_config_home_is_unset_or_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, xdg: str | None
) -> None:
    context, root, home = _context(tmp_path)
    if xdg is not None:
        monkeypatch.setenv("XDG_CONFIG_HOME", xdg)
    _yours_and_the_other(root, tmp_path / "xdg", home / ".config")
    text = context.text()
    assert "From DOT.md:\n\nThe one in ~/.config." in text and "XDG.md" not in text


def test_your_file_in_an_xdg_config_home_inside_the_project_is_the_project_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model can write anywhere in the project, so a config directory there puts your file on
    the project's terms, as a home there does: wherever its name came from, where it is decides."""
    context, root, _ = _context(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "config"))
    _write(root / "AGENTS.md", "Still here.")
    _write(root / "config/bh-02/context.toml", '[[section]]\nfiles = ["x"]\nfunction = "os:system"\n')
    text = context.text()
    assert "(bh-02 could not read the context file" in text and "may name only bh-02's own functions" in text
    assert "From AGENTS.md:\n\nStill here." in text  # the rest still say theirs


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
    files, root, home = ContextFiles(("~/mine.toml",), 20_000), tmp_path / "p", tmp_path
    _write(
        home / "mine.toml",
        'replace = true\n[[section]]\nfiles = ["docs/**/*.md", ".claude/rules/*.md"]\n'
        f'function = "{_NAMED}"\n',
    )
    _write(root / "docs/a.md", "a")
    assert files.text(root, home).endswith("docs/a.md.")
    _write(root / "docs/b.md", "b")
    _write(root / "docs/deep/c.md", "c")  # in a directory that was not there to look in
    assert files.text(root, home).endswith("docs/a.md, docs/b.md, docs/deep/c.md.")
    (root / "docs/a.md").unlink()
    assert files.text(root, home).endswith("docs/b.md, docs/deep/c.md.")
    _write(root / ".claude/rules/new.md", "r")  # under directories that were not there at all
    assert ".claude/rules/new.md" in files.text(root, home)


def test_a_search_looks_again_only_when_a_directory_it_looked_in_changed(tmp_path: Path) -> None:
    """Each reading costs a `stat` of each directory looked in, not a walk: shown by a file whose
    directory's time is put back, which the search does not see."""
    files, root, home = ContextFiles(("~/mine.toml",), 20_000), tmp_path / "p", tmp_path
    _write(
        home / "mine.toml",
        f'replace = true\n[[section]]\nfiles = ["docs/*.md"]\nfunction = "{_NAMED}"\n',
    )
    _write(root / "docs/a.md", "a")
    files.text(root, home)
    was = (root / "docs").stat()
    _write(root / "docs/hidden.md", "h")
    os.utime(root / "docs", ns=(was.st_atime_ns, was.st_mtime_ns))
    assert "hidden.md" not in files.text(root, home)


def test_the_context_files_say_at_most_max_chars(tmp_path: Path) -> None:
    context, root, _ = _context(tmp_path, max_chars=40)
    _write(root / "AGENTS.md", "x" * 500)
    assert "more chars of project context]" in context.text()


def test_your_file_inside_the_project_is_the_project_s(tmp_path: Path) -> None:
    """Run in your home, the model can write your file too, so it is held to the project's terms."""
    files, home = ContextFiles(("~/.config/bh-02/context.toml",), 20_000), tmp_path
    _write(home / ".config/bh-02/context.toml", '[[section]]\nfunction = "os:system"\n')
    assert "may name only bh-02's own functions" in files.text(home, home)


def test_a_link_in_the_project_to_a_file_outside_it_is_still_the_project_s(tmp_path: Path) -> None:
    """The model may write outside the project too (the jail's scratch directory): a context file
    it links into the project, or the `.bh-02` directory it links out, is held to the project's
    terms all the same, so it can name no file outside the project and no function of its own."""
    context, root, home = _context(tmp_path)
    _write(home / ".ssh/id_test", "FAKE-KEY")
    scratch = _write(
        tmp_path / "scratch/evil.toml",
        f'[[section]]\nfiles = ["~/.ssh/id_test"]\nfunction = "{_WHOLE}"\n',
    )
    (root / ".bh-02").mkdir()
    (root / ".bh-02/context.toml").symlink_to(scratch)
    text = context.text()
    assert "FAKE" not in text and "may name only files in the project" in text
    (root / ".bh-02/context.toml").unlink()
    (root / ".bh-02").rmdir()
    (scratch.parent / "context.toml").write_text(scratch.read_text())
    (root / ".bh-02").symlink_to(scratch.parent)
    text = ContextFiles((".bh-02/context.toml",), 20_000).text(root.resolve(), home)
    assert "FAKE" not in text and "may name only files in the project" in text


def test_a_hard_link_in_the_project_is_not_read(tmp_path: Path) -> None:
    """A second name in the project may be one the model gave a file the jail hides from it."""
    context, root, _ = _context(tmp_path)
    secret = _write(tmp_path / "hidden-from-the-jail.txt", "FAKE-HIDDEN")
    os.link(secret, root / "CLAUDE.local.md")
    _write(root / "AGENTS.md", "Read me.")
    text = context.text()
    assert "FAKE" not in text and "Read me." in text
