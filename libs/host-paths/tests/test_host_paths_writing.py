"""The one writer of a file the model may have planted a link beside: held to a table of what a
model could leave beneath a root, in a temporary directory. Whatever it left, nothing outside the
root is written or removed."""

import os
from collections.abc import Callable
from pathlib import Path, PurePath
from typing import Any

import pytest

from host_paths import Linked, NotOneFile, directory_beneath, read_beneath, remove_beneath, write_beneath


def _tree(tmp_path: Path) -> tuple[Path, Path]:
    """`root/a` (the directory written to) and, beside the root, a secret a link could lead to."""
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "a").mkdir(parents=True)
    outside.mkdir()
    secret = outside / "secret"
    secret.write_text("the jail hides this")
    return root, secret


def test_a_file_is_written_whole_and_replaced_by_a_second_write(tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    assert write_beneath(root, ["a", "memory.md"], b"one") is False  # nothing was there
    assert (root / "a" / "memory.md").read_bytes() == b"one"
    assert write_beneath(root, ["a", "memory.md"], b"two, longer") is True  # a file was
    assert (root / "a" / "memory.md").read_bytes() == b"two, longer"
    assert read_beneath(root, ["a", "memory.md"], cap=100) == b"two, longer"
    assert sorted(os.listdir(root / "a")) == ["memory.md"]  # no half-written file is left beside it


def test_a_file_is_written_readable_by_its_owner_alone(tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    write_beneath(root, ["a", "memory.md"], b"x")
    assert (root / "a" / "memory.md").stat().st_mode & 0o077 == 0


def test_a_file_is_written_beneath_a_directory_held_open(tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    with directory_beneath(root, ["a"]) as directory:
        write_beneath(directory, ["memory.md"], b"held")
        assert os.listdir(directory) == ["memory.md"]
    assert (root / "a" / "memory.md").read_bytes() == b"held"


def test_a_link_at_the_name_is_refused_not_followed(tmp_path: Path) -> None:
    """The link the model left to a file outside the directory: not written through, not replaced."""
    root, secret = _tree(tmp_path)
    (root / "a" / "memory.md").symlink_to(secret)
    with pytest.raises(Linked, match=r"a/memory.md is a link, which is not followed") as raised:
        write_beneath(root, ["a", "memory.md"], b"overwritten")
    assert raised.value.part == PurePath("a", "memory.md")
    assert secret.read_text() == "the jail hides this"
    assert (root / "a" / "memory.md").is_symlink()
    assert sorted(os.listdir(root / "a")) == ["memory.md"]


def test_a_dangling_link_at_the_name_does_not_create_what_it_points_to(tmp_path: Path) -> None:
    root, secret = _tree(tmp_path)
    planted = secret.parent / "not-there-yet"
    (root / "a" / "memory.md").symlink_to(planted)
    with pytest.raises(Linked):
        write_beneath(root, ["a", "memory.md"], b"created through it")
    assert not planted.exists()


def test_a_link_on_the_way_is_refused_and_nothing_is_written_through_it(tmp_path: Path) -> None:
    root, secret = _tree(tmp_path)
    (root / "swapped").symlink_to(secret.parent)
    with pytest.raises(Linked, match="swapped is a link") as raised:
        write_beneath(root, ["swapped", "memory.md"], b"planted")
    assert raised.value.part == PurePath("swapped")
    assert sorted(os.listdir(secret.parent)) == ["secret"]


def test_a_second_hard_linked_name_is_refused_and_the_file_it_names_is_left_alone(tmp_path: Path) -> None:
    root, secret = _tree(tmp_path)
    os.link(secret, root / "a" / "memory.md")
    with pytest.raises(NotOneFile, match="not a regular file with one name") as raised:
        write_beneath(root, ["a", "memory.md"], b"overwritten")
    assert raised.value.names == 2
    assert secret.read_text() == "the jail hides this"
    assert (root / "a" / "memory.md").read_text() == "the jail hides this"


def test_a_pipe_and_a_directory_are_not_files_to_write(tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    os.mkfifo(root / "a" / "pipe")
    (root / "a" / "directory").mkdir()
    for name in ("pipe", "directory"):
        with pytest.raises(NotOneFile):
            write_beneath(root, ["a", name], b"x")
    assert sorted(os.listdir(root / "a")) == ["directory", "pipe"]


def test_a_link_planted_after_the_check_is_replaced_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model is quicker than the check: it plants the link after the name was found free. The
    file is made under a name of its own and moved over the name, which replaces the link."""
    root, secret = _tree(tmp_path)
    renamed: Callable[..., Any] = os.rename
    planted: list[str] = []

    def late(source: str, to: str, **where: Any) -> None:
        os.symlink(secret, root / "a" / "memory.md")
        planted.append(to)
        renamed(source, to, **where)

    monkeypatch.setattr(os, "rename", late)
    write_beneath(root, ["a", "memory.md"], b"mine")
    assert planted == ["memory.md"]  # the link was there when the file was moved over the name
    assert secret.read_text() == "the jail hides this"
    assert not (root / "a" / "memory.md").is_symlink()
    assert (root / "a" / "memory.md").read_bytes() == b"mine"


def test_a_write_that_fails_leaves_no_file_behind(tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    with pytest.raises(TypeError):
        write_beneath(root, ["a", "memory.md"], "text, not bytes")  # type: ignore[arg-type]
    assert os.listdir(root / "a") == []


def test_a_name_is_one_step_beneath_the_root(tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    for names in (["a/memory.md"], ["..", "outside"], ["a", "."], []):
        with pytest.raises(ValueError):
            write_beneath(root, names, b"x")
        with pytest.raises(ValueError):
            remove_beneath(root, names)
    assert os.listdir(root / "a") == []


def test_a_file_is_removed(tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    (root / "a" / "memory.md").write_text("x")
    remove_beneath(root, ["a", "memory.md"])
    assert os.listdir(root / "a") == []
    with pytest.raises(FileNotFoundError, match="memory.md"):
        remove_beneath(root, ["a", "memory.md"])


def test_a_link_at_the_name_is_refused_not_removed_or_followed(tmp_path: Path) -> None:
    root, secret = _tree(tmp_path)
    (root / "a" / "memory.md").symlink_to(secret)
    with pytest.raises(Linked, match="is a link, which is not followed"):
        remove_beneath(root, ["a", "memory.md"])
    assert (root / "a" / "memory.md").is_symlink() and secret.exists()


def test_a_second_hard_linked_name_and_a_link_on_the_way_are_not_removed(tmp_path: Path) -> None:
    root, secret = _tree(tmp_path)
    os.link(secret, root / "a" / "memory.md")
    with pytest.raises(NotOneFile):
        remove_beneath(root, ["a", "memory.md"])
    assert (root / "a" / "memory.md").exists()
    (root / "swapped").symlink_to(secret.parent)
    with pytest.raises(Linked, match="swapped is a link"):
        remove_beneath(root, ["swapped", "secret"])
    assert secret.exists()
