"""Where the person's configuration is, and every place reading a file goes through: the one
definition each package that trusts a file by where it is uses, on links in a temporary
directory."""

from pathlib import Path

import pytest

from cordis_helpers import MOST_LINKS, config_home, walked


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"XDG_CONFIG_HOME": "/elsewhere/config"}, Path("/elsewhere/config")),
        ({}, Path("/home/someone/.config")),
        ({"XDG_CONFIG_HOME": ""}, Path("/home/someone/.config")),  # empty is unset
        ({"XDG_CONFIG_HOME": "relative"}, Path("relative")),  # as given, for the caller to place
    ],
)
def test_the_config_home_is_the_variable_else_the_home_s_dot_config(
    environ: dict[str, str], expected: Path
) -> None:
    assert config_home(environ, Path("/home/someone")) == expected


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
        [
            "elsewhere",
            "elsewhere/relative",
            "real",
            "real/inner",
            "real/inner/file",
            "real/inner/file",
        ],
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
