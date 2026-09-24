"""`launcher._derive_wrap_prefix`: task-046's pure DERIVE-and-VERIFY step.

SPEC.md §9, `exec`, verbatim: "The exec'd process is subject to the same
Spec as the workload -- never a weaker one. A mechanism that cannot
guarantee this refuses exec." `handle.exec` (`brig/run/exec_.py`) trusts
`launcher.py`'s `wrap_prefix` derivation to decide whether the compiled
stack's `wrap` can safely be reproduced on an arbitrary exec argv by
prepending a fixed tuple -- so the derivation has to be VERIFIED against
the actual compiled wrap's output, never assumed from the wrap's shape or
the mechanism roster.

`_derive_wrap_prefix` is pure: no I/O, no clock, no subprocess -- exactly
the unit tier's "render function" shape (`.claude/rules/unit-tests.md`:
"Render functions are the unit-test goldmine"). It is private to
`brig.run.launcher` (no public re-export); imported directly here, the
same posture the module's own docstring takes toward it.
"""

from __future__ import annotations

import pytest

from brig.run.launcher import _derive_wrap_prefix

_ARGV: tuple[str, ...] = ("workload", "--flag", "value")


@pytest.mark.unit
def test_prefix_is_derived_only_when_the_suffix_matches() -> None:
    """AC #4, enumerated exactly as the task names them:

    1. identity wrap -> `()`.
    2. a prefixing wrap -> the exact prefix tuple.
    3. an appending wrap -> `None`.
    4. a wrap that rewrites an element of `argv` -> `None`.
    5. a wrap returning FEWER elements than `argv` -> `None`.
    """
    # 1. Identity: wrapped_argv == argv itself -- the prefix is empty, not
    # None. This is the degenerate case `exec_in_jail` reads as "spawn
    # bare" (PLAIN fidelity), so it must be DISTINGUISHED from a refusal.
    assert _derive_wrap_prefix(_ARGV, _ARGV) == ()

    # 2. A real prefixing wrap: two tokens ahead of argv, argv itself
    # untouched at the tail.
    prefix = ("python3", "-m", "brig.mech.trampoline", "--cpu", "1", "--")
    wrapped = prefix + _ARGV
    assert _derive_wrap_prefix(wrapped, _ARGV) == prefix

    # 3. Appending: the wrap tacked a token onto the END instead of the
    # front -- the suffix comparison must catch this even though the
    # LENGTH check alone (mutation check B's own plant) would not.
    appended = (*_ARGV, "--appended")
    assert _derive_wrap_prefix(appended, _ARGV) is None

    # 4. Rewriting: same length and same prefix position, but one element
    # of what SHOULD be the argv suffix was changed in place -- a wrap
    # that silently altered the workload's own flag.
    rewritten = ("python3", "-m", "wrapper", "workload", "--flag", "REWRITTEN")
    assert _derive_wrap_prefix(rewritten, _ARGV) is None

    # 5. Fewer elements out than in: a (nonsensical, but not impossible for
    # a misbehaving mechanism) wrap that DROPS part of argv rather than
    # merely prefixing it.
    fewer = ("python3", "-m", "wrapper", "workload", "--flag")
    assert _derive_wrap_prefix(fewer, _ARGV) is None


@pytest.mark.unit
def test_empty_argv_is_not_corrupted_by_pythons_negative_zero_slice() -> None:
    """The special case `_derive_wrap_prefix`'s own docstring names:
    `seq[-0:]` is `seq[0:]` (the WHOLE sequence), not the empty suffix,
    because `-0 == 0` in Python. An implementation that slices
    `wrapped_argv[-len(argv):]` unconditionally would, for `argv == ()`,
    read the suffix as the ENTIRE `wrapped_argv` and then compare that
    against `()` -- which is false for any non-empty `wrapped_argv`, so a
    correct wrap of an empty exec argv would be wrongly REFUSED. The
    correct answer here is that EVERY `wrapped_argv` is trivially a valid
    "prefix" of an empty `argv` (the whole thing is prefix, nothing is
    suffix)."""
    assert _derive_wrap_prefix((), ()) == ()
    assert _derive_wrap_prefix(("a", "b", "c"), ()) == ("a", "b", "c")


@pytest.mark.unit
def test_zero_length_wrap_prefix_is_distinguishable_from_refusal() -> None:
    """Non-vacuity closer: `()` (empty tuple, a valid prefix) and `None`
    (refused) must never compare equal or be confusable by a caller doing
    `if not wrap_prefix`. `exec_.exec_in_jail` uses `is None` specifically
    to keep these apart (see that module's own docstring); this test pins
    that the two are actually distinct values, not merely reasoned to be."""
    result = _derive_wrap_prefix(_ARGV, _ARGV)
    assert result is not None
    assert result == ()
    refusal = _derive_wrap_prefix((*_ARGV, "extra"), _ARGV)
    assert refusal is None
