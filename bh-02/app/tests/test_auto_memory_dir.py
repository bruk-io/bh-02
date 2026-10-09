"""Where auto memory is kept: the project's directory under bh-02's state, named as Claude Code
names its projects, and shared by a repository's worktrees."""

import subprocess
from pathlib import Path

from bh_02.bootstrap import memory_directory, project_of


def test_the_directory_is_under_the_state_home_named_as_claude_code_names_a_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert memory_directory(Path("/home/me/my.app"), {}, home) == str(
        home / ".local/state/bh-02/projects/-home-me-my-app/memory"
    )
    assert (
        memory_directory(Path("/w"), {"XDG_STATE_HOME": "/state"}, home) == "/state/bh-02/projects/-w/memory"
    )


def test_the_project_is_the_git_repository_and_its_worktrees_share_it(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "deep").mkdir(parents=True)
    assert project_of(repo / "src" / "deep") == repo / "src" / "deep"  # no repository: itself
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        check=True,
    )
    assert project_of(repo / "src" / "deep") == repo
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(tmp_path / "tree")], check=True)
    assert project_of(tmp_path / "tree") == repo.resolve()
