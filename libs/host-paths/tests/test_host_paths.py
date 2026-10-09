"""Where the person's directories are, and every place reading a file goes through: the one
definition each package that trusts a file by where it is uses, on links in a temporary
directory."""

from pathlib import Path

import pytest

from host_paths import MOST_LINKS, config_home, passes, roots, state_home, walked


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"XDG_CONFIG_HOME": "/elsewhere/config"}, Path("/elsewhere/config")),
        ({}, Path("/home/someone/.config")),
        ({"XDG_CONFIG_HOME": ""}, Path("/home/someone/.config")),  # empty is unset
        ({"XDG_CONFIG_HOME": "relative"}, Path("/home/someone/.config")),  # relative is unset (XDG)
    ],
)
def test_the_config_home_is_the_variable_else_the_home_s_dot_config(
    environ: dict[str, str], expected: Path
) -> None:
    assert config_home(environ, Path("/home/someone")) == expected


def test_the_state_home_is_the_variable_else_the_home_s_local_state() -> None:
    home = Path("/home/someone")
    assert state_home({"XDG_STATE_HOME": "/s"}, home) == Path("/s")
    assert state_home({}, home) == state_home({"XDG_STATE_HOME": "x"}, home) == home / ".local" / "state"


def _tree(top: Path) -> None:
    """`real/inner/file`, and links to it every way the walks meet: an absolute link to a
    directory, a relative one, a link that is the file, a loop, and one to nothing."""
    (top / "real" / "inner").mkdir(parents=True)
    (top / "real" / "inner" / "file").write_text("x")
    (top / "elsewhere").mkdir()
    (top / "absolute").symlink_to(top / "real")
    (top / "elsewhere" / "relative").symlink_to(Path("..", "real"))
    (top / "file").symlink_to(top / "real" / "inner" / "file")
    (top / "loop-a").symlink_to("loop-b")
    (top / "loop-b").symlink_to("loop-a")
    (top / "dangling").symlink_to(top / "gone")


def _from(top: Path, path: Path) -> list[str]:
    """`walked(path)` below `top`, as names relative to it (the places above it left out)."""
    return [str(p.relative_to(top)) for p in walked(path) if p.is_relative_to(top) and p != top]


# Each case: the path below the tree's top, then every place below the top its walk goes
# through, in order, the last where it ends.
_CASES = [
    ("no link", "real/inner/file", ["real", "real/inner", "real/inner/file", "real/inner/file"]),
    (
        "an absolute link to a directory, where it sits, then where it leads",
        "absolute/inner/file",
        ["absolute", "real", "real/inner", "real/inner/file", "real/inner/file"],
    ),
    (
        "a relative link, from the directory it sits in",
        "elsewhere/relative/inner/file",
        ["elsewhere", "elsewhere/relative", "real", "real/inner", "real/inner/file", "real/inner/file"],
    ),
    (
        "a link that is the file itself",
        "file",
        ["file", "real", "real/inner", "real/inner/file", "real/inner/file"],
    ),
    (
        "`..` goes up from where the links before it led, not from the name",
        "absolute/inner/../inner/file",
        ["absolute", "real", "real/inner", "real/inner", "real/inner/file", "real/inner/file"],
    ),
    ("a link to nothing, followed to where it would be", "dangling", ["dangling", "gone", "gone"]),
    ("a place that is not there", "missing/file", ["missing", "missing/file", "missing/file"]),
]


@pytest.mark.parametrize(("path", "expected"), [c[1:] for c in _CASES], ids=[c[0] for c in _CASES])
def test_the_walk_names_every_place_reading_a_path_goes_through(
    tmp_path: Path, path: str, expected: list[str]
) -> None:
    top = tmp_path.resolve()
    _tree(top)
    assert _from(top, top / path) == expected


def test_a_loop_of_links_ends_after_as_many_links_as_linux_follows(tmp_path: Path) -> None:
    top = tmp_path.resolve()
    _tree(top)
    places = _from(top, top / "loop-a" / "file")
    # each link followed is a place, and the one past the limit is where the walk goes on from
    assert places[: MOST_LINKS + 1] == ["loop-a", "loop-b"] * (MOST_LINKS // 2) + ["loop-a"]
    assert places[MOST_LINKS + 1 :] == ["loop-a/file", "loop-a/file"]


def test_the_walk_starts_from_the_top(tmp_path: Path) -> None:
    top = tmp_path.resolve()
    walk = walked(top / "x")
    assert walk[0] == Path(top.anchor) / top.parts[1]
    assert walk[-1] == top / "x"


def test_a_path_passes_through_a_root_as_named_or_anywhere_its_links_lead(tmp_path: Path) -> None:
    """A file is reached through a root when it is in it as named, or when any directory or link
    on its way is: a file of the person's that is a link into the project, say, whose end the
    model could repoint. The places come in order, so the first says where it first meets one."""
    top = tmp_path.resolve()
    project, home = top / "project", top / "home"
    (project / "dotfiles").mkdir(parents=True)
    home.mkdir()
    (project / "dotfiles" / "models.toml").write_text("")
    (home / "models.toml").symlink_to(project / "dotfiles" / "models.toml")
    (home / "own.toml").write_text("")
    found = roots(project)
    assert passes(home / "own.toml", found) == []
    through = passes(home / "models.toml", found)
    assert through[0] == project and through[-1] == project / "dotfiles" / "models.toml"
    assert passes(project / "x" / ".." / "dotfiles", found)[0] == project / "dotfiles"  # as named


def test_a_root_is_itself_as_named_and_as_it_resolves(tmp_path: Path) -> None:
    top = tmp_path.resolve()
    (top / "real").mkdir()
    (top / "link").symlink_to(top / "real")
    assert roots(top / "link" / "." / "..") == (top, top)
    assert roots(top / "link") == (top / "link", top / "real")
