"""Pure argv parsing for the rlimits exec trampoline (`brig.mech.trampoline`).

Importing `brig.mech.trampoline` here never applies a limit or execs
anything -- see that package's `__init__.py` docstring. Every case asserts
the exact parsed dataclass or the exact refusal message, never a substring
(a stronger-than-required message would still contain a weaker assertion --
see this project's unit-test rules on that anti-pattern).
"""

from __future__ import annotations

import resource

import pytest

from brig.mech import trampoline
from brig.mech.trampoline import (
    ParsedTrampolineArgv,
    TrampolineArgvError,
    parse_trampoline_argv,
)


@pytest.mark.unit
def test_parses_cpu_flag_and_workload_argv() -> None:
    result = parse_trampoline_argv(["--cpu", "1", "--", "/bin/true"])
    assert result == ParsedTrampolineArgv(cpu_seconds=1, workload_argv=("/bin/true",))


@pytest.mark.unit
def test_no_separator_is_refused() -> None:
    with pytest.raises(TrampolineArgvError) as exc_info:
        parse_trampoline_argv(["--cpu", "1", "/bin/true"])
    assert str(exc_info.value) == ("missing '--' separator between limit flags and workload argv")


@pytest.mark.unit
def test_unknown_flag_is_refused() -> None:
    with pytest.raises(TrampolineArgvError) as exc_info:
        parse_trampoline_argv(["--memory", "1", "--", "/bin/true"])
    assert str(exc_info.value) == "unknown flag: '--memory'"


@pytest.mark.unit
def test_empty_tail_after_separator_is_refused() -> None:
    with pytest.raises(TrampolineArgvError) as exc_info:
        parse_trampoline_argv(["--cpu", "1", "--"])
    assert str(exc_info.value) == "empty workload argv after '--'"


@pytest.mark.unit
def test_workload_argv_with_flag_like_tokens_passes_through_unmodified() -> None:
    """The tail after `--` is never re-parsed as trampoline flags, even when
    it contains tokens that look like them."""
    result = parse_trampoline_argv(["--cpu", "1", "--", "python", "-c", "--cpu"])
    assert result == ParsedTrampolineArgv(cpu_seconds=1, workload_argv=("python", "-c", "--cpu"))


@pytest.mark.unit
def test_no_cpu_flag_is_a_valid_no_limit_parse() -> None:
    result = parse_trampoline_argv(["--", "/bin/echo", "hi"])
    assert result == ParsedTrampolineArgv(cpu_seconds=None, workload_argv=("/bin/echo", "hi"))


@pytest.mark.unit
def test_cpu_flag_missing_value_is_refused() -> None:
    with pytest.raises(TrampolineArgvError) as exc_info:
        parse_trampoline_argv(["--cpu", "--", "/bin/true"])
    assert str(exc_info.value) == "'--cpu' requires a value"


@pytest.mark.unit
def test_cpu_flag_non_integer_value_is_refused() -> None:
    with pytest.raises(TrampolineArgvError) as exc_info:
        parse_trampoline_argv(["--cpu", "soon", "--", "/bin/true"])
    assert str(exc_info.value) == "'--cpu' value must be an integer, got 'soon'"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["0", "-1"])
def test_cpu_flag_non_positive_value_is_refused(value: str) -> None:
    """`setrlimit(RLIMIT_CPU, (-1, -1))` means RLIM_INFINITY (no limit at
    all), and `0` trips instantly -- neither is a value this parser should
    hand through unexamined; both are refused as loudly as an unparseable
    one."""
    with pytest.raises(TrampolineArgvError) as exc_info:
        parse_trampoline_argv(["--cpu", value, "--", "/bin/true"])
    assert str(exc_info.value) == f"'--cpu' value must be a positive integer, got {value!r}"


# ---------------------------------------------------------------------------
# decision-161 (2026-09-08): the hard limit is one CPU-second above the soft
# one. `apply_limits` is exercised here through a stubbed `resource` -- unit
# tier, so nothing is set on this process and no workload is launched. The
# integration tier's spin loops (tests/integration/test_trampoline.py) are
# what prove the SIGNAL that pair produces; this proves the pair.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_limits_sets_the_hard_limit_one_second_above_the_soft_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Soft-equals-hard is `SIGKILL` on Linux, which is the kill this
    mechanism's whole `SIGXCPU` story depends on NOT happening."""
    calls: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        resource,
        "setrlimit",
        lambda which, limits: calls.append((which, limits)),
    )

    trampoline.apply_limits(ParsedTrampolineArgv(cpu_seconds=5, workload_argv=("/bin/true",)))

    assert calls == [(resource.RLIMIT_CPU, (5, 6))]


@pytest.mark.unit
def test_apply_limits_sets_nothing_when_no_cpu_limit_was_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        resource,
        "setrlimit",
        lambda which, limits: calls.append((which, limits)),
    )

    trampoline.apply_limits(ParsedTrampolineArgv(cpu_seconds=None, workload_argv=("/bin/true",)))

    assert calls == []
