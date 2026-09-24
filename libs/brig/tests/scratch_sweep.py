"""Scratch directory sweep and cleanup utilities.

This module provides pure functions for safely cleaning up jail scratch roots
created during test runs. It is kept separate from conftest.py to allow unit
testing without loading session fixtures.

Decision-121's five predicates, verified:
  1. Entry name starts with prefix
  2. One of two arms:
     - current-run: not in snapshot AND name[len(prefix):] starts with
       str(harness_pid) (a prefix match on the pid-bearing suffix, never a
       substring match anywhere in the name)
     - aged: (only if sweep_aged) mtime older than aged_seconds
  3. Is a directory (os.path.isdir)
  4. Is NOT a symlink (not os.path.islink)
  5. Realpath-then-containment: resolved path under resolved scratch_dir
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence


def snapshot_roots(scratch_dir: str, *, prefix: str) -> frozenset[str]:
    """Take a snapshot of existing root directory names.

    Returns entry names (not paths) in scratch_dir that start with prefix.
    This snapshot is taken before the test run and used to distinguish
    this run's new roots from pre-existing ones.

    Args:
        scratch_dir: Directory to scan (typically /tmp)
        prefix: Prefix filter (typically "bg")

    Returns:
        Frozenset of matching entry names
    """
    try:
        entries = os.listdir(scratch_dir)
    except OSError:
        return frozenset()

    return frozenset(name for name in entries if name.startswith(prefix))


def roots_to_sweep(
    scratch_dir: str,
    *,
    snapshot: frozenset[str],
    prefix: str,
    harness_pid: int,
    now: float,
    sweep_aged: bool,
    aged_seconds: float = 86400.0,
) -> tuple[str, ...]:
    """Determine which roots should be swept.

    Applies all five predicates from decision-121 and returns absolute paths
    of directories that match ALL predicates, sorted.

    Args:
        scratch_dir: Directory to scan (typically /tmp)
        snapshot: Pre-run snapshot from snapshot_roots
        prefix: Prefix filter (typically "bg")
        harness_pid: This run's harness process ID
        now: Current timestamp for age calculation
        sweep_aged: If True, include aged entries regardless of snapshot/pid
        aged_seconds: Threshold for "aged" (default 1 day)

    Returns:
        Sorted tuple of absolute paths to sweep
    """
    scratch_realpath = os.path.realpath(scratch_dir)
    scratch_sep = scratch_realpath + os.sep

    try:
        entries = os.listdir(scratch_dir)
    except OSError:
        return ()

    to_sweep: list[str] = []

    for entry_name in entries:
        # Predicate 1: Name must start with prefix
        if not entry_name.startswith(prefix):
            continue

        entry_path = os.path.join(scratch_dir, entry_name)

        # Predicate 2: One of two arms must hold
        # arm_a matches the pid-bearing suffix by PREFIX, never by substring
        # anywhere in the name -- a substring test would sweep e.g. "bg912x"
        # under harness_pid=12, since "12" is a substring of "912".
        suffix = entry_name[len(prefix) :]
        arm_a = entry_name not in snapshot and suffix.startswith(str(harness_pid))
        arm_b = sweep_aged and (now - os.lstat(entry_path).st_mtime > aged_seconds)

        if not (arm_a or arm_b):
            continue

        # Predicate 3: Must be a directory
        if not os.path.isdir(entry_path):
            continue

        # Predicate 4: Must NOT be a symlink
        if os.path.islink(entry_path):
            continue

        # Predicate 5: Realpath must be under realpath of scratch_dir
        try:
            entry_realpath = os.path.realpath(entry_path)
        except OSError:
            continue

        if not entry_realpath.startswith(scratch_sep):
            continue

        to_sweep.append(entry_path)

    # Return absolute paths, sorted
    return tuple(sorted(to_sweep))


def sweep_roots(paths: Sequence[str]) -> tuple[str, ...]:
    """Remove the given directory paths.

    Every failure is collected and reported -- never suppressed -- catching
    OSError per path and returning formatted failure lines. An empty return
    means every removal succeeded.

    Args:
        paths: Absolute paths to remove

    Returns:
        Tuple of formatted failure lines (empty = all succeeded)
    """
    failures: list[str] = []

    for path in paths:
        try:
            shutil.rmtree(path)
        except OSError as exc:
            failures.append(f"{path}: {exc}")

    return tuple(failures)
