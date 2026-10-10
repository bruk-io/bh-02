"""The one opener of a file the model may have written: held to a table of what a model could
leave beneath a root, in a temporary directory."""

import os
from pathlib import Path, PurePath

import pytest

from host_paths import Link, Linked, NotOneFile, TooLarge, directory_beneath, read_beneath


def _tree(root: Path) -> Path:
    """`root/a/b/file` holding `hello`, and beside the root a secret a link could lead to."""
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / "file").write_bytes(b"hello")
    secret = root.parent / "secret"
    (secret / "b").mkdir(parents=True)
    (secret / "b" / "file").write_bytes(b"the jail hides this")
    return secret


def test_a_file_reached_through_no_link_is_read(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _tree(root)
    assert read_beneath(root, ["a", "b", "file"], cap=5) == b"hello"
    with directory_beneath(root, ["a", "b"]) as directory:
        assert read_beneath(directory, ["file"], cap=5) == b"hello"
        assert sorted(os.listdir(directory)) == ["file"]
    with directory_beneath(root, []) as itself:
        assert sorted(os.listdir(itself)) == ["a"]


def test_a_root_that_is_a_link_is_the_caller_s_to_trust(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _tree(root)
    (tmp_path / "named").symlink_to(root)
    assert read_beneath(tmp_path / "named", ["a", "b", "file"], cap=5) == b"hello"


@pytest.mark.parametrize(("depth", "part"), [(1, "a"), (2, "a/b")])
def test_a_link_at_any_depth_on_the_way_stops_the_walk_naming_it(
    tmp_path: Path, depth: int, part: str
) -> None:
    root = tmp_path / "root"
    secret = _tree(root)
    linked = root / part
    os.rename(linked, tmp_path / "moved")
    linked.symlink_to(secret if depth == 1 else secret / "b")
    with pytest.raises(Linked, match=f"{part} is a link, which is not followed") as raised:
        read_beneath(root, ["a", "b", "file"], cap=100)
    assert raised.value.part == PurePath(part)
    with pytest.raises(Linked), directory_beneath(root, ["a", "b"]):
        pass


def test_a_link_at_the_end_is_answered_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    secret = _tree(root)
    (root / "a" / "b" / "file").unlink()
    (root / "a" / "b" / "file").symlink_to(secret / "b" / "file")
    assert read_beneath(root, ["a", "b", "file"], cap=100) == Link(str(secret / "b" / "file"))
    (root / "a" / "b" / "dangling").symlink_to("nowhere")
    assert read_beneath(root, ["a", "b", "dangling"], cap=100) == Link("nowhere")


def test_a_hard_link_is_not_one_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    secret = _tree(root)
    os.link(secret / "b" / "file", root / "a" / "hard")
    with pytest.raises(NotOneFile, match="not a regular file with one name") as raised:
        read_beneath(root, ["a", "hard"], cap=100)
    assert raised.value.names == 2


def test_a_pipe_is_not_waited_on_and_a_directory_is_not_a_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _tree(root)
    os.mkfifo(root / "a" / "pipe")
    with pytest.raises(NotOneFile) as raised:
        read_beneath(root, ["a", "pipe"], cap=100)  # returns at once: O_NONBLOCK
    assert raised.value.names == 1
    with pytest.raises(NotOneFile):
        read_beneath(root, ["a", "b"], cap=100)


def test_a_file_on_the_way_is_not_a_directory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _tree(root)
    with pytest.raises(NotADirectoryError, match="a/b/file"):
        read_beneath(root, ["a", "b", "file", "deeper"], cap=100)


def test_a_file_over_the_cap_is_refused_not_cut_short(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _tree(root)
    with pytest.raises(TooLarge, match="larger than 4 bytes") as raised:
        read_beneath(root, ["a", "b", "file"], cap=4)
    assert raised.value.cap == 4


def test_a_file_gone_between_the_walk_and_the_read_is_not_found(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _tree(root)
    with directory_beneath(root, ["a", "b"]) as directory:
        (root / "a" / "b" / "file").unlink()
        with pytest.raises(FileNotFoundError):
            read_beneath(directory, ["file"], cap=100)
    with pytest.raises(FileNotFoundError, match="missing"):
        read_beneath(root, ["missing", "file"], cap=100)


def test_a_name_is_one_step_beneath_the_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    _tree(root)
    for names in (["a/b", "file"], ["..", "secret"], ["a", "."], []):
        with pytest.raises(ValueError):
            read_beneath(root, names, cap=100)
