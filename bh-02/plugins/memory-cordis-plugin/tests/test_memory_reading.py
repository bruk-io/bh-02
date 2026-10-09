"""`read`: a memory file read so that nothing the model changed chooses what is read."""

import os
from pathlib import Path

import pytest

from memory_cordis_plugin import LIMIT, read


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_read_walks_from_the_project_s_root_through_no_link_but_one_to_another_memory_file(
    tmp_path: Path,
) -> None:
    """In the project, a regular file with one name reached through no link, or a link to another
    of the memory files given, read as that; outside it, the file as named. Anything else says why
    it was not read, and a pipe does so at once, never waiting for a writer."""
    root, home = tmp_path / "project", tmp_path / "home"
    agents = _write(root / "AGENTS.md", "Read me.")
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    (home / "dotfiles").mkdir(parents=True)
    (home / "CLAUDE.md").symlink_to(_write(home / "dotfiles/CLAUDE.md", "Mine."))
    assert read(root / "CLAUDE.md", [root / "CLAUDE.md", agents], root) == "Read me."
    assert read(home / "CLAUDE.md", [home / "CLAUDE.md"], root) == "Mine."  # yours, as named
    with pytest.raises(OSError, match="not another memory file"):
        read(root / "CLAUDE.md", [root / "CLAUDE.md"], root)
    _write(root / "real/x.md", "x")
    (root / "docs").symlink_to("real")
    with pytest.raises(OSError, match="reached through .*docs, which is a link"):
        read(root / "docs/x.md", [root / "docs/x.md"], root)
    os.link(agents, root / "SECOND.md")
    with pytest.raises(OSError, match="not a regular file with one name"):
        read(agents, [agents], root)
    os.mkfifo(root / "PIPE.md")
    with pytest.raises(OSError, match="not a regular file with one name"):
        read(root / "PIPE.md", [root / "PIPE.md"], root)


def test_a_link_out_of_the_project_to_a_secret_is_not_read(tmp_path: Path) -> None:
    """The model can make a link in the project at any moment; one to a file it may not read (a
    key in the person's home) reads nothing, and neither does a file named like a secret."""
    root, home = tmp_path / "project", tmp_path / "home"
    key = _write(home / ".ssh/id_test", "FAKE-KEY")
    root.mkdir()
    (root / "CLAUDE.md").symlink_to(key)
    with pytest.raises(OSError, match="not another memory file"):
        read(root / "CLAUDE.md", [root / "CLAUDE.md"], root)
    env = _write(root / "local.env", "FAKE")
    with pytest.raises(OSError, match="named like a secret"):
        read(env, [env], root)
    (root / "AGENTS.md").symlink_to("local.env")
    with pytest.raises(OSError, match="not another memory file"):
        read(root / "AGENTS.md", [root / "AGENTS.md", env], root)


def test_a_file_of_yours_linked_into_the_project_is_not_read_through_the_link(tmp_path: Path) -> None:
    """`~/.claude/CLAUDE.md` a link into ~/dotfiles, and bh-02 run there: the file it leads to is
    the project's, which the model can repoint, so yours is not read through it."""
    home = tmp_path / "home"
    root = home / "dotfiles"
    _write(root / "claude/CLAUDE.md", "Mine, kept in my dotfiles.")
    (home / ".claude").mkdir()
    (home / ".claude/CLAUDE.md").symlink_to(root / "claude/CLAUDE.md")
    with pytest.raises(OSError, match="reached through the project"):
        read(home / ".claude/CLAUDE.md", [home / ".claude/CLAUDE.md"], root)


def test_a_file_larger_than_claude_code_reads_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "project"
    big = _write(root / "CLAUDE.md", "x" * (LIMIT + 1))
    with pytest.raises(OSError, match="larger than 4 MiB"):
        read(big, [big], root)
    outside = _write(tmp_path / "CLAUDE.md", "x" * (LIMIT + 1))
    with pytest.raises(OSError, match="larger than 4 MiB"):
        read(outside, [outside], root)
