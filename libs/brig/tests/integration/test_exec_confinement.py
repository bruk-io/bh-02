"""`handle.exec` places the sibling inside the SAME confinement as the
workload -- task-046's spec anchor, SPEC.md §9, verbatim:

    - The exec'd process is subject to the same Spec as the workload --
      never a weaker one. A mechanism that cannot guarantee this refuses
      exec.

Before this task, `exec_in_jail` (`brig/run/exec_.py`) spawned the caller's
raw `argv` through `subprocess.Popen` directly -- neither the compiled
stack's argv wrap NOR its env overlay ever reached an exec sibling, so an
exec under `degraded()` ran BARE: no env scrubbing, no cpu cap. This file
is the measured claim, run for real, against the REAL `degraded()` preset
(`env_scrub` + `rlimits`, matrix-ordered `rlimits` outermost) launched
through the REAL `SubprocessLauncher` -- same "observe from inside the
jail" posture as `tests/integration/test_stack_matrix_ordering.py`, applied
here to the exec path instead of the workload path.

Every long-lived JAIL WORKLOAD here (the `sleep 100` each test's exec runs
alongside) is built through `tests.conftest.workload_argv` so the suite's
leak sweep catches anything a test's own teardown misses. The exec'd
commands themselves are short-lived and always `wait()`-ed on synchronously
within the test that spawned them -- by the time a test returns, nothing it
exec'd is still alive to leak, so none of them need a `workload_argv` token
(same posture as `tests/integration/test_rlimits.py`'s own docstring).

Short `/tmp/bg<pid>ec<run_id[:8]><n>` scratch roots throughout (`ec` --
"exec confinement" -- keeping this file's jail-dir sequence disjoint from
every sibling integration file sharing the same `os.getpid()` across one
pytest session), never `tmp_path` (`sun_path` is 104 bytes on darwin). The
`run_id[:8]` salt is load-bearing, not decorative -- see `_new_jail_dir`'s
own docstring for the confirmed collision it closes.
"""

from __future__ import annotations

import itertools
import os
import signal
import sys
from collections.abc import Sequence

import pytest

from brig.core import Axis, EnvMode, EnvPolicy, Limits, Spec
from brig.mech import CompileCtx, Step
from brig.run.exec_ import ExecFidelity, ExecWrapNotAPrefix, exec_in_jail
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack, degraded
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()

#: Embedded as the spin loop's own first source line so it shows up in
#: `/bin/ps`'s command column while the process is alive -- same
#: convention as `test_rlimits.py`'s `_SPIN_LOOP_MARKER` and
#: `test_stack_matrix_ordering.py`'s marker of the same purpose.
_SPIN_LOOP_MARKER = "T046_SPIN_MARKER"
_SPIN_LOOP = f"# {_SPIN_LOOP_MARKER}\nx = 0\nwhile True:\n    x += 1\n"

_WAIT_TIMEOUT_S = 10.0


def _new_jail_dir(run_id: str) -> str:
    """A short scratch root, `/tmp/bg<pid>ec<run_id[:8]><n>` -- never
    `tmp_path` (`sun_path` is 104 bytes on darwin).

    `run_id[:8]` (the session-scoped fixture's own fresh
    `uuid.uuid4().hex`, never reused across a pytest invocation) is
    load-bearing, not cosmetic: `os.getpid()` ALONE is not collision-free
    across separate invocations sharing one long-lived shell session --
    darwin's pid counter wraps (default max ~99998), and NOTHING here
    deletes a `jail_dir` after its test ends, so an earlier invocation's
    directory can still be sitting at the exact path a LATER invocation's
    `os.getpid() + counter` combination reproduces. Confirmed directly (not
    merely reasoned): pre-seeding a jail_dir's `events.jsonl` with a stale,
    unmatched `EXEC` record under the SAME `jail_id` a later `_launch`
    call also uses, then launching a real handle into that same directory
    and calling `kill()`, makes `teardown.kill_jail`'s own
    `_live_exec_siblings` count the phantom record as one more live
    sibling -- inflating `len(KillReport.items)` by one. The `run_id`
    salt makes that specific collision structurally unreachable for this
    file's own jail dirs, independent of pid reuse."""
    return f"/tmp/bg{os.getpid()}ec{run_id[:8]}{next(_jail_counter)}"


def _parse_env_lines(text: str) -> dict[str, str]:
    """Parse `NAME=VALUE` lines (as `/usr/bin/env` with no args prints)
    into a dict, split on the FIRST `=` only. Reimplemented locally rather
    than imported -- no cross-integration-file private-helper imports
    elsewhere in this suite (see `test_stack_matrix_ordering.py`'s helper
    of the same name and purpose)."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line or "=" not in line:
            continue
        name, _sep, value = line.partition("=")
        result[name] = value
    return result


def _launch(stack: Stack, spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str) -> Handle:
    """Compile `stack` against `spec` and launch `argv` through the REAL
    `SubprocessLauncher` -- no monkeypatching, no hand-built `CompiledJail`,
    the same real-mechanism posture `test_stack_matrix_ordering.py`
    establishes for the workload path, applied here to the path this task
    changes: `handle.exec`."""
    jail_dir = _new_jail_dir(run_id)
    ctx = CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    jail = stack.compile(spec, ctx=ctx)
    launcher = SubprocessLauncher()
    return launcher.launch(
        jail,
        argv=list(argv),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _teardown_group(handle: Handle) -> None:
    """Group-kill the long-lived workload -- the kill is hand-rolled, not
    `Handle.kill()`, same reasoning as `test_exec.py`'s own
    `_teardown_group`: a test's cleanup path must not be the code under
    test. `handle.wait()` blocks until the launcher's exit-waiter has reaped
    it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _sleep_workload(run_id: str) -> list[str]:
    return workload_argv(run_id, "sleep 100")


class _AppendingMechanism:
    """Test-only `Mechanism` (SPEC.md §6's `Protocol` shape, duck-typed):
    its `wrap` APPENDS a trailing token AFTER `argv` instead of prefixing
    it -- the shape AC #3 needs to exercise `_derive_wrap_prefix`'s suffix
    check failing against a REAL `Stack.compile()` output, not a hand-built
    `CompiledJail` with a bad `wrap` spliced in directly. Claims no axis
    (`axes = frozenset()`) so it needs no compatibility-matrix entry and no
    grade -- the only thing under test here is the wrap shape."""

    name = "test_appending"
    axes: frozenset[Axis] = frozenset()

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        del spec, ctx

        def wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
            return (*argv, "--appended-by-test-mechanism")

        return Step(
            wrap=wrap,
            env={},
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades={},
            denial_signatures=(),
        )


# ---------------------------------------------------------------------------
# AC #1 -- the env claim: the scrubbed canary does not reach an exec
# sibling, with its discriminating empty-stack control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_sibling_does_not_see_the_scrubbed_canary(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #1: `degraded()` under `EnvPolicy(SCRUB, allow_names=("PATH",
    "HOME"))`, with a canary name NOT on that allow-list set in the
    launching (this test) process's own environment. The exec sibling
    (`["/usr/bin/env"]`, printing its own environment with no args) does
    NOT see the canary -- read back from its stdout FILE on disk, not from
    any in-process claim."""
    canary_name = f"BRIG_T046_CANARY_{run_id}"
    monkeypatch.setenv(canary_name, "leak-if-visible")

    spec = Spec(
        limits=Limits(cpu_seconds=60),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH", "HOME")),
    )
    handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="jail-t046-ac1", run_id=run_id
    )
    try:
        exec_handle = exec_in_jail(handle, ["/usr/bin/env"])
        assert exec_handle.wait(timeout=_WAIT_TIMEOUT_S) == 0
        with open(exec_handle.stdout_path, encoding="utf-8", errors="replace") as f:
            names = _parse_env_lines(f.read())

        assert canary_name not in names, (
            f"{canary_name!r} leaked into the exec sibling's environment: {names!r}"
        )
        # Control against a vacuous pass: the allow-listed names actually
        # arrived, proving env_scrub's own forwarding ran and the exec
        # sibling really did print a real environment -- not that it
        # failed to launch or print anything at all.
        assert "PATH" in names
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_control_exec_sibling_under_the_empty_stack_does_see_the_canary(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #1's named control: the IDENTICAL probe, against `Stack([])`
    (the empty stack, `wrap_prefix == ()`), DOES see the canary -- the
    discriminating half that rules out "the probe never looked" (the same
    canary name, the same exec argv, only the stack differs)."""
    canary_name = f"BRIG_T046_CANARY_{run_id}"
    monkeypatch.setenv(canary_name, "should-be-visible")

    handle = _launch(
        Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t046-ac1-control", run_id=run_id
    )
    try:
        assert handle.wrap_prefix == ()
        exec_handle = exec_in_jail(handle, ["/usr/bin/env"])
        assert exec_handle.wait(timeout=_WAIT_TIMEOUT_S) == 0
        with open(exec_handle.stdout_path, encoding="utf-8", errors="replace") as f:
            names = _parse_env_lines(f.read())

        assert canary_name in names
        assert names[canary_name] == "should-be-visible"
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #2 -- the cpu claim: the exec sibling is subject to the SAME cpu
# limit as the workload, with its discriminating short-command control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_sibling_is_subject_to_the_cpu_limit(run_id: str) -> None:
    """AC #2: `degraded()` under `Limits(cpu_seconds=1)`. An exec'd spin
    loop (`sys.executable -c <busy loop>`, absolute path -- no PATH
    forwarding needed to find it, sidestepping the env axis entirely) dies
    on `SIGXCPU` -- `wait()` returns exactly `-signal.SIGXCPU`, within a
    bounded deadline (`wait(timeout=...)` itself raises rather than hang
    on a runaway)."""
    assert int(signal.SIGXCPU) == 24  # platform pin, asserted not assumed
    spec = Spec(limits=Limits(cpu_seconds=1))
    handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="jail-t046-ac2", run_id=run_id
    )
    try:
        exec_handle = exec_in_jail(handle, [sys.executable, "-c", _SPIN_LOOP])
        status = exec_handle.wait(timeout=_WAIT_TIMEOUT_S)
        assert status == -int(signal.SIGXCPU), (
            f"expected the exec sibling to die on SIGXCPU under the SAME "
            f"cpu_seconds=1 limit as the workload; got wait()={status!r}"
        )
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_control_exec_sibling_short_command_exits_zero_under_the_same_limit(
    run_id: str,
) -> None:
    """AC #2's named control: under the SAME `Limits(cpu_seconds=1)` and
    the SAME jail, an exec'd command trivial enough to finish well inside
    the cap (`/usr/bin/true`, absolute path) exits 0 -- so a test that
    killed everything under this stack (e.g. a broken trampoline
    invocation) could not pass this half."""
    spec = Spec(limits=Limits(cpu_seconds=1))
    handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="jail-t046-ac2-control", run_id=run_id
    )
    try:
        exec_handle = exec_in_jail(handle, ["/usr/bin/true"])
        assert exec_handle.wait(timeout=_WAIT_TIMEOUT_S) == 0
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #3 -- exec refuses when the composed wrap is not a pure argv prefix;
# nothing is spawned.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_refuses_when_the_composed_wrap_is_not_a_pure_prefix(run_id: str) -> None:
    """AC #3: a REAL `Stack` containing `_AppendingMechanism` (its `wrap`
    APPENDS a trailing token, so the suffix check fails) compiles and
    launches normally -- the refusal is `handle.exec`'s to make, not the
    launcher's. `handle.exec(...)` raises `ExecWrapNotAPrefix`, naming that
    the composed wrap is not a pure argv prefix; NO process is spawned --
    no new `exec-*` file appears under `jail_dir` at all (the refusal is
    checked before either exec stdio file is even opened).

    THE CONTROL, in the same test: the identical `exec-*` scan, against a
    SECOND (empty-stack) handle where the exec actually succeeds, DOES
    find a new file -- without this, `after == before` on the refused
    handle would pass just as happily if the scan pattern could never
    match anything at all (a scan that never finds anything cannot tell
    "refused" apart from "broken probe")."""
    handle = _launch(
        Stack([_AppendingMechanism()]),
        Spec(),
        _sleep_workload(run_id),
        jail_id="jail-t046-ac3",
        run_id=run_id,
    )
    control_handle = _launch(
        Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t046-ac3-control", run_id=run_id
    )
    try:
        assert handle.wrap_prefix is None

        before = {name for name in os.listdir(handle.jail_dir) if name.startswith("exec-")}

        with pytest.raises(ExecWrapNotAPrefix) as exc_info:
            handle.exec(["true"])
        assert "is not a pure argv prefix" in str(exc_info.value)

        after = {name for name in os.listdir(handle.jail_dir) if name.startswith("exec-")}
        assert after == before  # no exec-*-{stdout,stderr}.log file was ever created

        # THE CONTROL: the SAME scan, on a handle whose exec is allowed
        # to succeed, DOES see a new exec-* file -- proving the scan
        # pattern can positively detect an exec artifact at all.
        control_before = {
            name for name in os.listdir(control_handle.jail_dir) if name.startswith("exec-")
        }
        assert control_before == set()
        control_exec = exec_in_jail(control_handle, ["true"])
        assert control_exec.wait(timeout=_WAIT_TIMEOUT_S) == 0
        control_after = {
            name for name in os.listdir(control_handle.jail_dir) if name.startswith("exec-")
        }
        assert control_after != control_before
        assert len(control_after) == 2  # exec-<token>-stdout.log, exec-<token>-stderr.log
    finally:
        _teardown_group(handle)
        _teardown_group(control_handle)


# ---------------------------------------------------------------------------
# AC #5 -- the EXEC event records the wrapped argv, with an empty-stack
# control. DELETED by decision-152 (2026-09-08) together with the per-jail
# event stream it read. The claim was about a RECORD ("the `EXEC` event's
# argv is `wrap_prefix + requested`, not the raw request"), and with the
# record gone there is nothing left to assert that is not either a
# restatement of `handle.wrap_prefix` (already pinned above) or a weaker
# proxy for it. The property the record stood in for -- the sibling really
# does run under the workload's own wrap -- is observed FROM INSIDE THE
# JAIL by AC #1 and AC #2 above, each with its own empty-stack control,
# which is the stronger evidence and always was. No replacement test is
# invented here: a weaker test wearing a deleted one's name is exactly
# what this library's own laws forbid.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fidelity is honest under the composed stack (not directly one of the
# named ACs, but the same claim AC #1/#2 exercise, made checkable on the
# structured field SPEC.md §9 names -- same posture as
# `test_exec.py::test_fidelity_is_plain_and_spec_matches_handles`).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_fidelity_is_equivalent_profile_under_a_composed_stack(run_id: str) -> None:
    """A non-empty, verified `wrap_prefix` grades `ExecFidelity.
    EQUIVALENT_PROFILE`, asserted as the enum member (SPEC.md §9: "A stack
    with no mechanisms grades PLAIN" -- the composed `degraded()` stack is
    not that case, and must not silently read as if it were)."""
    spec = Spec(limits=Limits(cpu_seconds=60))
    handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="jail-t046-fidelity", run_id=run_id
    )
    try:
        exec_handle = exec_in_jail(handle, ["/usr/bin/true"])
        assert exec_handle.wait(timeout=_WAIT_TIMEOUT_S) == 0
        assert exec_handle.fidelity is ExecFidelity.EQUIVALENT_PROFILE
    finally:
        _teardown_group(handle)
