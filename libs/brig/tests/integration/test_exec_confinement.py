"""`jail.start` places the sibling inside the SAME confinement as the
workload -- task-046's spec anchor, SPEC.md §9, verbatim:

    - The exec'd process is subject to the same Spec as the workload --
      never a weaker one. A mechanism that cannot guarantee this refuses
      exec.

Before this task, an exec (a sibling `jail.start` since decision-183) spawned the caller's
raw `argv` through `subprocess.Popen` directly -- neither the compiled
stack's argv wrap NOR its env overlay ever reached an exec sibling, so an
exec under `degraded()` ran BARE: no env scrubbing, no cpu cap. This file
is the measured claim, run for real, against the REAL `degraded()` preset
(`env_scrub` + `rlimits`, matrix-ordered `rlimits` outermost) launched
through the REAL `Jail.create` and `jail.start` -- same "observe from inside the
jail" posture as `tests/integration/test_stack_matrix_ordering.py`, applied
here to the exec path instead of the workload path.

Every long-lived JAIL WORKLOAD here (the `sleep 100` each test's exec runs
alongside) is built through `tests.conftest.workload_argv` so the suite's
leak sweep catches anything a test's own teardown misses. The exec'd
commands themselves are short-lived and always `wait()`-ed on synchronously
within the test that spawned them -- by the time a test returns, nothing it
exec'd is still alive to leak, so none of them need a `workload_argv` token
(same posture as `tests/integration/test_rlimits.py`'s own docstring).

Short scratch roots from `tests/conftest.py`'s `jail_dir` throughout, never
`tmp_path` (`sun_path` is 104 bytes on darwin).
"""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Sequence

import pytest

from brig.core import Axis, EnvMode, EnvPolicy, Limits, Spec
from brig.core.runtime import RuntimeKind
from brig.mech import CompileCtx, Step
from brig.run import ExecFidelity, ExecWrapNotAPrefix, IoPolicy, Jail, Process, _records
from brig.stack import Stack, degraded
from tests.conftest import NewJailDir, launch, teardown_group, workload_argv

#: Embedded as the spin loop's own first source line so it shows up in
#: `/bin/ps`'s command column while the process is alive -- same
#: convention as `test_rlimits.py`'s `_SPIN_LOOP_MARKER` and
#: `test_stack_matrix_ordering.py`'s marker of the same purpose.
_SPIN_LOOP_MARKER = "T046_SPIN_MARKER"
_SPIN_LOOP = f"# {_SPIN_LOOP_MARKER}\nx = 0\nwhile True:\n    x += 1\n"

_WAIT_TIMEOUT_S = 10.0


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


def _launch(
    stack: Stack, spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str, jail_dir: str
) -> tuple[Jail, Process]:
    """Compile `stack` against `spec` and launch `argv` through the REAL
    `Jail.create` and `jail.start` -- no monkeypatching, no hand-built `CompiledJail`,
    the same real-mechanism posture `test_stack_matrix_ordering.py`
    establishes for the workload path, applied here to the path this task
    changes: `jail.start`."""
    ctx = CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    jail = stack.compile(spec, ctx=ctx)
    return launch(
        jail,
        argv=list(argv),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _teardown_group(process: Process) -> None:
    """Group-kill the long-lived workload -- the kill is hand-rolled, not
    `Jail.destroy()`, same reasoning as `test_exec.py`'s own
    `_teardown_group`: a test's cleanup path must not be the code under
    test. `process.wait()` blocks until the launcher's exit-waiter has reaped
    it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(process)


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
    runtime: RuntimeKind | None = None

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
    run_id: str, monkeypatch: pytest.MonkeyPatch, jail_dir: str
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
    jail, process = _launch(
        degraded(),
        spec,
        _sleep_workload(run_id),
        jail_id="jail-t046-ac1",
        run_id=run_id,
        jail_dir=jail_dir,
    )
    try:
        sibling = jail.start(["/usr/bin/env"])
        assert sibling.wait(timeout=_WAIT_TIMEOUT_S) == 0
        with open(sibling.stdout_path, encoding="utf-8", errors="replace") as f:
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
        _teardown_group(process)


@pytest.mark.integration
def test_control_exec_sibling_under_the_empty_stack_does_see_the_canary(
    run_id: str, monkeypatch: pytest.MonkeyPatch, jail_dir: str
) -> None:
    """AC #1's named control: the IDENTICAL probe, against `Stack([])`
    (the empty stack, `wrap_prefix == ()`), DOES see the canary -- the
    discriminating half that rules out "the probe never looked" (the same
    canary name, the same exec argv, only the stack differs)."""
    canary_name = f"BRIG_T046_CANARY_{run_id}"
    monkeypatch.setenv(canary_name, "should-be-visible")

    jail, process = _launch(
        Stack([]),
        Spec(),
        _sleep_workload(run_id),
        jail_id="jail-t046-ac1-control",
        run_id=run_id,
        jail_dir=jail_dir,
    )
    try:
        assert jail._base.wrap_prefix == ()
        sibling = jail.start(["/usr/bin/env"])
        assert sibling.wait(timeout=_WAIT_TIMEOUT_S) == 0
        with open(sibling.stdout_path, encoding="utf-8", errors="replace") as f:
            names = _parse_env_lines(f.read())

        assert canary_name in names
        assert names[canary_name] == "should-be-visible"
    finally:
        _teardown_group(process)


# ---------------------------------------------------------------------------
# AC #2 -- the cpu claim: the exec sibling is subject to the SAME cpu
# limit as the workload, with its discriminating short-command control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_sibling_is_subject_to_the_cpu_limit(run_id: str, jail_dir: str) -> None:
    """AC #2: `degraded()` under `Limits(cpu_seconds=1)`. An exec'd spin
    loop (`sys.executable -c <busy loop>`, absolute path -- no PATH
    forwarding needed to find it, sidestepping the env axis entirely) dies
    on `SIGXCPU` -- `wait()` returns exactly `-signal.SIGXCPU`, within a
    bounded deadline (`wait(timeout=...)` itself raises rather than hang
    on a runaway)."""
    assert int(signal.SIGXCPU) == 24  # platform pin, asserted not assumed
    spec = Spec(limits=Limits(cpu_seconds=1))
    jail, process = _launch(
        degraded(),
        spec,
        _sleep_workload(run_id),
        jail_id="jail-t046-ac2",
        run_id=run_id,
        jail_dir=jail_dir,
    )
    try:
        sibling = jail.start([sys.executable, "-c", _SPIN_LOOP])
        status = sibling.wait(timeout=_WAIT_TIMEOUT_S)
        assert status == -int(signal.SIGXCPU), (
            f"expected the exec sibling to die on SIGXCPU under the SAME "
            f"cpu_seconds=1 limit as the workload; got wait()={status!r}"
        )
    finally:
        _teardown_group(process)


@pytest.mark.integration
def test_control_exec_sibling_short_command_exits_zero_under_the_same_limit(
    run_id: str,
    jail_dir: str,
) -> None:
    """AC #2's named control: under the SAME `Limits(cpu_seconds=1)` and
    the SAME jail, an exec'd command trivial enough to finish well inside
    the cap (`/usr/bin/true`, absolute path) exits 0 -- so a test that
    killed everything under this stack (e.g. a broken trampoline
    invocation) could not pass this half."""
    spec = Spec(limits=Limits(cpu_seconds=1))
    jail, process = _launch(
        degraded(),
        spec,
        _sleep_workload(run_id),
        jail_id="jail-t046-ac2-control",
        run_id=run_id,
        jail_dir=jail_dir,
    )
    try:
        sibling = jail.start(["/usr/bin/true"])
        assert sibling.wait(timeout=_WAIT_TIMEOUT_S) == 0
    finally:
        _teardown_group(process)


# ---------------------------------------------------------------------------
# AC #3 -- exec refuses when the composed wrap is not a pure argv prefix;
# nothing is spawned.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_every_start_refuses_when_the_composed_wrap_is_not_a_pure_prefix(
    run_id: str, new_jail_dir: NewJailDir
) -> None:
    """AC #3, as decision-181 (2026-10-12) moved it: a REAL `Stack` containing
    `_AppendingMechanism` (its `wrap` APPENDS a trailing token, so the suffix
    check fails) compiles, and `create` derives no prefix (`None`), so EVERY
    start refuses, the first included: the launch raises `ExecWrapNotAPrefix`
    and NO process is spawned -- no records directory appears under
    `<jail_dir>/procs` at all (the refusal is checked before one is made).
    Before decision-181 the first process ran and only a later `exec`
    refused; now the first process is a start like any other.

    THE CONTROL, in the same test: the identical `procs/` scan, against a
    SECOND (empty-stack) launch where the start succeeds, DOES find a new
    entry -- without this, an empty scan on the refused jail would pass just
    as happily if the scan could never match anything at all."""
    jail_dir = new_jail_dir()
    ctx = CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    compiled = Stack([_AppendingMechanism()]).compile(Spec(), ctx=ctx)

    with pytest.raises(ExecWrapNotAPrefix) as exc_info:
        launch(
            compiled,
            argv=_sleep_workload(run_id),
            cwd=jail_dir,
            io=IoPolicy(),
            jail_id="jail-t046-ac3",
            jail_dir=jail_dir,
        )
    assert "is not a pure argv prefix" in str(exc_info.value)
    assert exc_info.value.wrap_prefix is None
    assert not os.path.exists(_records.procs_dir(jail_dir))

    control_jail, control_process = _launch(
        Stack([]),
        Spec(),
        _sleep_workload(run_id),
        jail_id="jail-t046-ac3-control",
        run_id=run_id,
        jail_dir=new_jail_dir(),
    )
    try:
        assert control_jail._base.wrap_prefix == ()
        before = os.listdir(_records.procs_dir(control_jail.jail_dir))
        assert len(before) == 1  # the control's own first process
        control_exec = control_jail.start(["true"])
        assert control_exec.wait(timeout=_WAIT_TIMEOUT_S) == 0
        after = os.listdir(_records.procs_dir(control_jail.jail_dir))
        assert len(after) == 2
    finally:
        _teardown_group(control_process)


# ---------------------------------------------------------------------------
# AC #5 -- the EXEC event records the wrapped argv, with an empty-stack
# control. DELETED by decision-152 (2026-09-08) together with the per-jail
# event stream it read. The claim was about a RECORD ("the `EXEC` event's
# argv is `wrap_prefix + requested`, not the raw request"), and with the
# record gone there is nothing left to assert that is not either a
# restatement of `jail._base.wrap_prefix` (already pinned above) or a weaker
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
def test_fidelity_is_equivalent_profile_under_a_composed_stack(run_id: str, jail_dir: str) -> None:
    """A non-empty, verified `wrap_prefix` grades `ExecFidelity.
    EQUIVALENT_PROFILE`, asserted as the enum member (SPEC.md §9: "A stack
    with no mechanisms grades PLAIN" -- the composed `degraded()` stack is
    not that case, and must not silently read as if it were)."""
    spec = Spec(limits=Limits(cpu_seconds=60))
    jail, process = _launch(
        degraded(),
        spec,
        _sleep_workload(run_id),
        jail_id="jail-t046-fidelity",
        run_id=run_id,
        jail_dir=jail_dir,
    )
    try:
        sibling = jail.start(["/usr/bin/true"])
        assert sibling.wait(timeout=_WAIT_TIMEOUT_S) == 0
        assert sibling.fidelity is ExecFidelity.EQUIVALENT_PROFILE
    finally:
        _teardown_group(process)
