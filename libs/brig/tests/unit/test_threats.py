"""Test threat lists as documented tuples (M1 EC3)."""

import pytest

from brig.core.threats import (
    BARE_REPO_TOPLEVEL,
    CREDENTIAL_READ_DENIES_HOME_RELATIVE,
    SELF_MODIFY_WORKSPACE_RELATIVE,
)


@pytest.mark.unit
def test_ec3_canary_self_modify_includes_git_hooks() -> None:
    """AC #1: .git/hooks is in SELF_MODIFY_WORKSPACE_RELATIVE."""
    assert ".git/hooks" in SELF_MODIFY_WORKSPACE_RELATIVE


@pytest.mark.unit
def test_ec3_canary_credentials_include_ssh() -> None:
    """AC #2: .ssh is in CREDENTIAL_READ_DENIES_HOME_RELATIVE."""
    assert ".ssh" in CREDENTIAL_READ_DENIES_HOME_RELATIVE


@pytest.mark.unit
def test_exact_lengths() -> None:
    """AC #3: exact lengths 12 / 11 / 3 (truncation and silent addition both red)."""
    assert len(CREDENTIAL_READ_DENIES_HOME_RELATIVE) == 12
    assert len(SELF_MODIFY_WORKSPACE_RELATIVE) == 11
    assert len(BARE_REPO_TOPLEVEL) == 3


@pytest.mark.unit
def test_all_entries_are_valid_relative_posix_paths() -> None:
    """AC #4: all entries are relative POSIX paths, no leading slash, no '..', no trailing slash, no duplicates."""
    all_tuples = [
        ("CREDENTIAL_READ_DENIES_HOME_RELATIVE", CREDENTIAL_READ_DENIES_HOME_RELATIVE),
        ("SELF_MODIFY_WORKSPACE_RELATIVE", SELF_MODIFY_WORKSPACE_RELATIVE),
        ("BARE_REPO_TOPLEVEL", BARE_REPO_TOPLEVEL),
    ]

    for tuple_name, threat_list in all_tuples:
        # Check no duplicates
        assert len(threat_list) == len(set(threat_list)), f"{tuple_name} has duplicates"

        for entry in threat_list:
            # Check it's a string
            assert isinstance(entry, str), f"{tuple_name}: {entry} is not a string"

            # Check no leading slash
            assert not entry.startswith("/"), f"{tuple_name}: {entry} has leading slash"

            # Check no trailing slash
            assert not entry.endswith("/"), f"{tuple_name}: {entry} has trailing slash"

            # Check no '..' segment
            parts = entry.split("/")
            assert ".." not in parts, f"{tuple_name}: {entry} contains '..' segment"

            # Check no empty segments (would indicate double slashes, trailing slashes, etc.)
            # However, single dots in filenames like .ssh or .git are allowed
            assert all(p for p in parts), f"{tuple_name}: {entry} has empty segments"
