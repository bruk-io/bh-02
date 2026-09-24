"""Unit tests for scratch directory sweeping and cleanup."""

from __future__ import annotations

import ast
import os
import tempfile
import time
from pathlib import Path

import pytest

from tests.scratch_sweep import roots_to_sweep, snapshot_roots, sweep_roots


@pytest.mark.unit
def test_snapshot_roots_returns_entry_names_with_prefix(tmp_path: Path) -> None:
    """snapshot_roots returns names (not paths) of entries starting with prefix."""
    (tmp_path / "bg123").mkdir()
    (tmp_path / "bg456").mkdir()
    (tmp_path / "other").mkdir()

    result = snapshot_roots(str(tmp_path), prefix="bg")

    assert "bg123" in result
    assert "bg456" in result
    assert "other" not in result
    assert isinstance(result, frozenset)


@pytest.mark.unit
def test_predicate_1_entry_must_start_with_prefix(tmp_path: Path) -> None:
    """Predicate 1: Entry name must start with prefix."""
    pid = 123
    # Plant: entry without prefix
    (tmp_path / "notbg123").mkdir()
    # Control: entry with prefix
    (tmp_path / f"bg{pid}x").mkdir()

    snapshot: frozenset[str] = frozenset()
    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # Plant is absent from result
    assert not any("notbg123" in p for p in result)
    # Control is present
    assert any(f"bg{pid}x" in p for p in result)


@pytest.mark.unit
def test_predicate_2_arm_a_current_run_not_in_snapshot_and_contains_pid(
    tmp_path: Path,
) -> None:
    """Predicate 2 arm (a): Not in snapshot AND name contains harness_pid."""
    pid = 123
    # Plant: in snapshot but contains pid - should NOT sweep
    name_in_snapshot = f"bg{pid}y"
    (tmp_path / name_in_snapshot).mkdir()
    snapshot: frozenset[str] = frozenset([name_in_snapshot])

    # Control: not in snapshot and contains pid - should sweep
    name_not_in_snapshot = f"bg{pid}x"
    (tmp_path / name_not_in_snapshot).mkdir()

    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # Plant is absent
    assert not any(name_in_snapshot in p for p in result)
    # Control is present
    assert any(name_not_in_snapshot in p for p in result)


@pytest.mark.unit
def test_predicate_2_arm_a_pid_prefix_not_substring(tmp_path: Path) -> None:
    """Verifier finding 1 regression: arm_a matches the pid-bearing SUFFIX
    by PREFIX (n[len(prefix):].startswith(str(harness_pid))), never by
    substring anywhere in the name. harness_pid=12: "bg912x" has "12" as a
    substring of "912x", but the suffix "912x" does NOT start with "12" --
    a substring implementation (`str(harness_pid) in entry_name`) would
    wrongly sweep it; this is the exact live bug the rejection reproduced.
    """
    pid = 12
    # Plant: not in snapshot; "12" is a substring of the suffix "912x" but
    # the suffix does not START WITH "12" -- must NOT sweep.
    (tmp_path / "bg912x").mkdir()
    snapshot: frozenset[str] = frozenset()

    # Control: not in snapshot; suffix "12x" DOES start with "12" -- swept.
    (tmp_path / f"bg{pid}x").mkdir()

    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # Plant (substring collision only) is absent
    assert not any("bg912x" in p for p in result)
    # Control (true prefix match) is present
    assert any(f"bg{pid}x" in p for p in result)


@pytest.mark.unit
def test_predicate_2_arm_a_wrong_pid_not_swept(tmp_path: Path) -> None:
    """Predicate 2 arm (a): Name not containing harness_pid should not sweep."""
    pid = 123
    # Plant: not in snapshot but wrong pid - should NOT sweep
    (tmp_path / "bg999x").mkdir()
    snapshot: frozenset[str] = frozenset()

    # Control: not in snapshot with correct pid - should sweep
    (tmp_path / f"bg{pid}x").mkdir()

    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # Plant is absent
    assert not any("bg999x" in p for p in result)
    # Control is present
    assert any(f"bg{pid}x" in p for p in result)


@pytest.mark.unit
def test_predicate_2_arm_b_aged_flag_controls_both_directions(tmp_path: Path) -> None:
    """AC #5: THE AGED ARM in both directions, from ONE planted entry, so
    the two calls cannot drift apart. The entry is IN the snapshot and its
    name does not carry harness_pid as a prefix, so arm_a can never explain
    its presence -- only arm_b (sweep_aged=True) can. `now` is captured
    once and reused for both calls; everything else is held identical.
    """
    aged_dir = tmp_path / "bg999aged"
    aged_dir.mkdir()
    two_days_ago = time.time() - (2 * 86400)
    os.utime(str(aged_dir), (two_days_ago, two_days_ago))

    snapshot = frozenset(["bg999aged"])
    now = time.time()

    result_flag_false = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=123,
        now=now,
        sweep_aged=False,
    )
    result_flag_true = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=123,
        now=now,
        sweep_aged=True,
    )

    # Absent when sweep_aged=False
    assert not any("bg999aged" in p for p in result_flag_false)
    # Present when sweep_aged=True, same entry, same `now`
    assert any("bg999aged" in p for p in result_flag_true)


@pytest.mark.unit
def test_predicate_3_not_a_directory_not_swept(tmp_path: Path) -> None:
    """Predicate 3: Must be a directory."""
    pid = 123
    # Plant: a file, not a directory
    (tmp_path / f"bg{pid}x").touch()
    snapshot: frozenset[str] = frozenset()

    # Control: a directory
    (tmp_path / f"bg{pid}y").mkdir()

    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # Plant (file) is absent
    assert not any(f"bg{pid}x" in p for p in result)
    # Control (directory) is present
    assert any(f"bg{pid}y" in p for p in result)


@pytest.mark.unit
def test_spawn_registry_file_not_swept_directory_swept(tmp_path: Path) -> None:
    """AC #3: Spawn registry file (bg<pid>-spawnreg) is spared; directory is swept."""
    pid = 456
    # Plant: spawn registry as a FILE - should NOT be swept
    spawnreg_file = tmp_path / f"bg{pid}-spawnreg"
    spawnreg_file.touch()
    snapshot: frozenset[str] = frozenset()

    # Control: spawn registry as a DIRECTORY - should be swept
    spawnreg_dir = tmp_path / f"bg{pid}-spawnregX"
    spawnreg_dir.mkdir()

    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # File is absent
    assert not any(f"bg{pid}-spawnreg" in p and p.endswith(f"bg{pid}-spawnreg") for p in result)
    # Directory is present
    assert any(f"bg{pid}-spawnregX" in p for p in result)


@pytest.mark.unit
def test_predicate_4_symlink_not_swept(tmp_path: Path) -> None:
    """Predicate 4: Symlinks are excluded -- isolated from predicate 5 by
    pointing the symlink's target INSIDE scratch_dir. A target outside
    scratch_dir would fail predicate 4 AND predicate 5 together, which is
    exactly the AC #2 "failing ONLY that predicate" breach the verifier
    named; a target that stays inside can only be excluded by predicate 4.
    """
    pid = 123
    # Target directory INSIDE scratch_dir, named so it does not itself
    # match `prefix` and show up as its own (separate) swept entry.
    inner_target = tmp_path / "inner_target"
    inner_target.mkdir()

    # Plant: a symlink whose target IS inside scratch_dir -- predicate 5's
    # realpath containment check would pass for it, so only predicate 4
    # (islink) can be what excludes it.
    symlink = tmp_path / f"bg{pid}link"
    symlink.symlink_to(inner_target)
    snapshot: frozenset[str] = frozenset()

    # Control: a real directory
    real_dir = tmp_path / f"bg{pid}real"
    real_dir.mkdir()

    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # Symlink is absent -- excluded by predicate 4 alone
    assert not any(f"bg{pid}link" in p for p in result)
    # Real directory is present
    assert any(f"bg{pid}real" in p for p in result)


@pytest.mark.unit
def test_predicate_4_external_symlink_absent_under_both_path_forms(tmp_path: Path) -> None:
    """AC #4, first half repeated under both path forms: a symlink entry
    whose target is a directory OUTSIDE scratch_dir is absent from the
    output, asserted both when scratch_dir is passed as its real path and
    as an aliased path to the same directory (standing in for /tmp vs
    /private/tmp on darwin, which pytest's tmp_path does not itself alias).

    Named plainly, per this repo's own discipline: this absence is enforced
    by predicate 4 (islink) before predicate 5 is ever reached -- the
    symlink is excluded regardless of where its target resolves, so this
    test alone does not discriminate a realpath predicate 5 from a
    string-prefix one. test_predicate_5_realpath_resolves_aliased_
    scratch_dir below is the positive case that does: a plain (non-symlink)
    entry, reached only through an aliased scratch_dir, that a
    string-prefix implementation would wrongly exclude.
    """
    pid = 123
    real_root = tmp_path / "real_root"
    real_root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real_root)

    with tempfile.TemporaryDirectory() as external_dir:
        symlink = real_root / f"bg{pid}x"
        symlink.symlink_to(external_dir)
        snapshot: frozenset[str] = frozenset()

        result_real_form = roots_to_sweep(
            str(real_root),
            snapshot=snapshot,
            prefix="bg",
            harness_pid=pid,
            now=time.time(),
            sweep_aged=False,
        )
        result_aliased_form = roots_to_sweep(
            str(alias),
            snapshot=snapshot,
            prefix="bg",
            harness_pid=pid,
            now=time.time(),
            sweep_aged=False,
        )

    assert not any(f"bg{pid}x" in p for p in result_real_form)
    assert not any(f"bg{pid}x" in p for p in result_aliased_form)


@pytest.mark.unit
def test_predicate_5_realpath_resolves_aliased_scratch_dir(tmp_path: Path) -> None:
    """AC #4 / verifier findings 4-5: predicate 5 is realpath-then-
    containment, not a string prefix test on the raw scratch_dir argument.

    scratch_dir is passed as an ALIAS symlink to the real root, and the
    planted entry is a plain (non-symlink) directory under the real root --
    so predicate 4 cannot be what admits or excludes it, isolating
    predicate 5 for the first time in this suite.

    A realpath-based predicate 5 resolves both the entry and scratch_dir to
    real_root and finds containment: PRESENT. A string-prefix
    implementation (`entry_realpath.startswith(scratch_dir + os.sep)`)
    would compare `.../real_root/bg<pid>x` against the literal alias
    string `.../alias` and find no match: ABSENT. This is the exact
    positive case that discriminates the two -- mutation-checked below.
    """
    pid = 123
    real_root = tmp_path / "real_root"
    real_root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real_root)

    # Plant: an ordinary directory inside the REAL root (not the alias).
    target = real_root / f"bg{pid}x"
    target.mkdir()
    snapshot: frozenset[str] = frozenset()

    # scratch_dir is the ALIAS, not the real path.
    result = roots_to_sweep(
        str(alias),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    assert any(f"bg{pid}x" in p for p in result)


@pytest.mark.unit
def test_roots_to_sweep_returns_absolute_paths_sorted(tmp_path: Path) -> None:
    """roots_to_sweep returns absolute paths, sorted."""
    pid = 123
    # Create multiple directories
    (tmp_path / f"bg{pid}a").mkdir()
    (tmp_path / f"bg{pid}z").mkdir()
    (tmp_path / f"bg{pid}m").mkdir()
    snapshot: frozenset[str] = frozenset()

    result = roots_to_sweep(
        str(tmp_path),
        snapshot=snapshot,
        prefix="bg",
        harness_pid=pid,
        now=time.time(),
        sweep_aged=False,
    )

    # All should be absolute paths
    assert all(os.path.isabs(p) for p in result)
    # Should be sorted
    assert result == tuple(sorted(result))


@pytest.mark.unit
def test_sweep_roots_returns_empty_tuple_on_success(tmp_path: Path) -> None:
    """sweep_roots returns empty tuple when all removals succeed."""
    dir1 = tmp_path / "test1"
    dir1.mkdir()
    dir2 = tmp_path / "test2"
    dir2.mkdir()

    result = sweep_roots([str(dir1), str(dir2)])

    assert result == ()
    assert not dir1.exists()
    assert not dir2.exists()


@pytest.mark.unit
def test_sweep_roots_no_swallowed_failures_reports_removal_errors(
    tmp_path: Path,
) -> None:
    """AC #6: sweep_roots reports removal failures, never swallows them with ignore_errors."""
    # Use a path that doesn't exist - guaranteed to fail
    nonexistent = tmp_path / "does_not_exist"

    result = sweep_roots([str(nonexistent)])

    # Should have failure lines
    assert len(result) > 0
    # Failure line should name the path
    assert str(nonexistent) in result[0]


@pytest.mark.unit
def test_scratch_sweep_source_never_uses_ignore_errors() -> None:
    """AC #6, second half: the literal token `ignore_errors` must appear
    nowhere in tests/scratch_sweep.py -- not in code, not in a comment or
    docstring. sweep_roots must catch OSError per path itself; it may
    never fall back on shutil.rmtree's own silent-failure mode.
    """
    module_path = Path(__file__).parent.parent / "scratch_sweep.py"
    source = module_path.read_text()
    assert "ignore_errors" not in source


@pytest.mark.unit
def test_sweep_roots_returns_failure_lines_with_path_names() -> None:
    """AC #6: Failure lines must name the path for debugging."""
    nonexistent = "/tmp/this_does_not_exist_anywhere_123456789"

    result = sweep_roots([nonexistent])

    # Must have a failure line
    assert len(result) > 0
    # Failure line must contain the path
    assert nonexistent in result[0]


@pytest.mark.unit
def test_conftest_pytest_addoption_wiring() -> None:
    """AC #7: AST inspection verifies pytest_addoption registers --sweep-aged correctly."""
    conftest_path = Path(__file__).parent.parent / "conftest.py"
    with open(conftest_path) as f:
        conftest_source = f.read()

    tree = ast.parse(conftest_source)

    # Find pytest_addoption function
    pytest_addoption_found = False
    has_sweep_aged_option = False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "pytest_addoption":
            pytest_addoption_found = True
            # Check that the function body references --sweep-aged
            source_text = ast.get_source_segment(conftest_source, node)
            if source_text and "--sweep-aged" in source_text:
                has_sweep_aged_option = True
                # Verify action="store_true" is present
                assert 'action="store_true"' in source_text
                # Verify default=False is present
                assert "default=False" in source_text

    assert pytest_addoption_found, "pytest_addoption function not found"
    assert has_sweep_aged_option, "--sweep-aged option not registered"


@pytest.mark.unit
def test_conftest_fixture_wiring() -> None:
    """AC #7: AST inspection verifies fixture references all three functions."""
    conftest_path = Path(__file__).parent.parent / "conftest.py"
    with open(conftest_path) as f:
        conftest_source = f.read()

    # Verify the fixture exists
    assert "_scratch_sweep" in conftest_source, "_scratch_sweep fixture not found"

    # Extract the fixture function and its decorators by finding the function definition
    fixture_start = conftest_source.find("def _scratch_sweep(")
    assert fixture_start != -1, "_scratch_sweep function definition not found in conftest"

    # Look backward from the function to find the decorator
    decorator_start = conftest_source.rfind("@pytest.fixture", 0, fixture_start)
    assert decorator_start != -1, "@pytest.fixture decorator not found before _scratch_sweep"

    # Extract everything from decorator to end of function (next @pytest or def at same level)
    next_def = conftest_source.find("\n@pytest", fixture_start)
    next_def = next_def if next_def != -1 else conftest_source.find("\ndef ", fixture_start + 50)
    fixture_section = conftest_source[decorator_start : next_def if next_def != -1 else None]

    # Verify decorator specifies session scope and autouse
    assert 'scope="session"' in fixture_section, "fixture does not specify scope=session"
    assert "autouse=True" in fixture_section, "fixture is not autouse=True"

    # Verify the fixture references all three functions
    assert "snapshot_roots" in fixture_section, "fixture does not reference snapshot_roots"
    assert "roots_to_sweep" in fixture_section, "fixture does not reference roots_to_sweep"
    assert "sweep_roots" in fixture_section, "fixture does not reference sweep_roots"
