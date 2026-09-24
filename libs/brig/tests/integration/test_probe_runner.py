"""`run_battery`/`Handle.probe` -- task-050. SPEC.md §12, verbatim:

    `handle.probe(battery)` runs canned violation attempts **inside the
    jail, through the same stack, launcher, and channel the workload
    uses** -- a policy that holds for a side shell but not for the real
    path is not a policy.

and, on contradiction:

    Probe outcomes are checked against the report's grades: a probe that
    contradicts a grade fails the battery loudly.

MILESTONES.md M4 EC2, verbatim:

    2. Positive controls: a battery run where the workspace-write control
       fails marks the whole battery VACUOUS, not passed -- demonstrated
       by pointing the battery at a non-writable workspace.

Every REAL jail this file launches is built through the REAL
`SubprocessLauncher`, `stack.compile()`, and `handle.exec` -- no
monkeypatching, no hand-built `ExecHandle`, same "observe from inside the
jail" posture `tests/integration/test_exec_confinement.py` established for
the exec path this file's subject (`run_battery`) sits directly on top of.
Where a test's whole point is the CONTRADICTION-TABLE logic rather than any
real enforcement (AC #4/#7), the launched jail's `report` is deliberately
overridden via `dataclasses.replace` (`Handle` is frozen) to a KNOWN grade,
and the probe's own verdict is forced by a `returncode`-only fact
(`/usr/bin/true` always exits 0, which `classify` alone -- unmodified,
per this task's Out of scope -- turns into `Verdict.FAIL` for a `DENIAL`
probe) rather than by faking `classify`'s output directly.

Every long-lived JAIL WORKLOAD here (`sleep 100`) is built through
`tests.conftest.workload_argv` so the suite's leak sweep catches anything a
test's own teardown misses; the probes themselves are short-lived and
`wait()`-ed on synchronously by `run_battery` before this file's own
assertions run, so none of them need a `workload_argv` token (same posture
as `test_exec_confinement.py`'s own docstring).

Short `/tmp/bg<pid>pr<run_id[:8]><n>` scratch roots throughout (`pr` --
"probe runner") -- never `tmp_path` (`sun_path` is 104 bytes on darwin;
CLAUDE.md's own trap list).
"""

from __future__ import annotations

import dataclasses
import itertools
import os
import shutil
import stat
from collections.abc import Sequence
from typing import cast

import pytest

from brig.core import (
    Axis,
    EnforcementReport,
    EnvMode,
    EnvPolicy,
    Grade,
    Graded,
    Limits,
    ProbeReport,
    ProbeShape,
    Spec,
    Verdict,
)
from brig.core.probes import Battery as CoreBattery
from brig.core.probes import BatteryVerdict
from brig.probe.battery import Battery, Expectation, Probe
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack, degraded
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()
_WAIT_TIMEOUT_S = 15.0


def _new_root(run_id: str, tag: str) -> str:
    """A short scratch root, `/tmp/bg<pid><tag><run_id[:8]><n>` -- never
    `tmp_path` (`sun_path` is 104 bytes on darwin). The `run_id[:8]` salt is
    load-bearing, not decorative -- see `test_exec_confinement.py`'s own
    `_new_jail_dir` docstring for the confirmed pid-reuse collision it
    closes, reproduced here for the same reason."""
    return f"/tmp/bg{os.getpid()}{tag}{run_id[:8]}{next(_jail_counter)}"


def _launch(stack: Stack, spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str) -> Handle:
    jail_dir = _new_root(run_id, "pr")
    jail = stack.compile(spec)
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
    `Handle.kill()`, same reasoning as `test_exec_confinement.py`'s own
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


def _with_axis_grade(handle: Handle, axis: Axis, grade: Grade) -> Handle:
    """A copy of `handle` whose `report` grades `axis` as `grade`, every
    other axis unchanged -- `Handle` and `EnforcementReport` are both
    frozen, so this is `dataclasses.replace` two layers deep, never
    mutation. Used only where a test's subject is the contradiction table
    itself (AC #4/#7), not real per-mechanism enforcement."""
    new_axes = dict(handle.report.axes)
    new_axes[axis] = Graded(grade=grade)
    return dataclasses.replace(handle, report=EnforcementReport(axes=new_axes))


def _probe(handle: Handle, battery: Battery) -> ProbeReport:
    """`Handle.probe`'s own parameter is typed against `core.probes.Battery`
    (task-050's Deliverable: "run imports nothing from probe"). Every
    concrete `Battery` this file builds is FROZEN (`brig/probe/battery.py`'s
    own convention throughout), and mypy models a frozen dataclass field as
    READ-ONLY -- so it never structurally matches `core.probes.Battery`'s
    plain `name: str` attribute, which mypy's Protocol check treats as
    requiring a settable variable. This is the exact same tension
    `brig/run/exec_.py`'s own docstring documents for `Handle` on the OTHER
    side of a Protocol-shaped boundary ("mypy models a frozen dataclass's
    fields as read-only, so `Handle` (frozen) fails a `Protocol`'s default
    read-write attribute check").

    It is a STATIC-ANALYSIS-ONLY mismatch, not a real one: `core.probes.
    Battery` is `@runtime_checkable`, and its RUNTIME check only tests
    attribute PRESENCE, never writability -- every concrete `Battery` this
    file builds already satisfies it at runtime
    (`isinstance(battery, CoreBattery)` is `True`, confirmed directly, not
    assumed). `cast` below tells mypy what is already true at runtime,
    same idiom `exec_.py` uses `Any` for on the analogous `Handle` side."""
    return handle.probe(cast(CoreBattery, battery))


# ---------------------------------------------------------------------------
# AC #1 / #2 -- a failed positive control marks the battery VACUOUS, not
# passed (MILESTONES M4 EC2), with the discriminating writable-workspace
# control.
# ---------------------------------------------------------------------------


def _workspace_control_battery(workspace: str) -> Battery:
    """A single-probe, `CONTROL`-shaped battery: write a marker into
    `workspace` and read it back. IDENTICAL across AC #1 and its control
    (AC #2) -- only `workspace`'s own permission bits differ between the
    two callers."""
    argv = (
        "/bin/sh",
        "-c",
        f"echo t050ctrlok > {workspace}/probe.txt && cat {workspace}/probe.txt",
    )
    control = Probe(
        name="workspace-write-control",
        shape=ProbeShape.CONTROL,
        axis=Axis.FS_WRITE,
        argv=argv,
        expect=Expectation(token="t050ctrlok"),
    )
    return Battery(name="t050-workspace-control", axis=Axis.FS_WRITE, probes=(control,))


@pytest.mark.integration
def test_a_failed_control_marks_the_battery_vacuous_not_passed(run_id: str) -> None:
    """AC #1 / MILESTONES M4 EC2, executed literally: the battery's
    `CONTROL` probe attempts to write into a directory `chmod`'d `0o500`
    (read+execute, no write) -- a REAL OS permission denial, not a faked
    verdict. `report.battery_verdict` is `BatteryVerdict.VACUOUS`, the
    control's own `ProbeOutcome.verdict` is `Verdict.FAIL`, and that
    outcome's `probe_name` names the failing control."""
    workspace = _new_root(run_id, "ws")
    os.makedirs(workspace)
    os.chmod(workspace, stat.S_IRUSR | stat.S_IXUSR)  # 0o500: no write
    try:
        handle = _launch(
            Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t050-ac1", run_id=run_id
        )
        try:
            battery = _workspace_control_battery(workspace)
            report = _probe(handle, battery)

            assert report.battery_verdict is BatteryVerdict.VACUOUS
            control_outcome = next(
                o for o in report.outcomes if o.probe_name == "workspace-write-control"
            )
            assert control_outcome.verdict is Verdict.FAIL
            assert control_outcome.probe_name == "workspace-write-control"
        finally:
            _teardown_group(handle)
    finally:
        os.chmod(workspace, stat.S_IRWXU)
        shutil.rmtree(workspace)


@pytest.mark.integration
def test_the_same_battery_against_a_writable_workspace_does_not_go_vacuous(run_id: str) -> None:
    """AC #2, the discriminating half: the IDENTICAL battery
    (`_workspace_control_battery`), against the SAME shape of directory
    left writable, does NOT go `Verdict.VACUOUS` -- without this, the first
    test cannot distinguish "the control mechanism works" from "this battery
    always reports VACUOUS no matter what"."""
    workspace = _new_root(run_id, "ws")
    os.makedirs(workspace)
    os.chmod(workspace, stat.S_IRWXU)  # 0o700: writable
    try:
        handle = _launch(
            Stack([]),
            Spec(),
            _sleep_workload(run_id),
            jail_id="jail-t050-ac2-control",
            run_id=run_id,
        )
        try:
            battery = _workspace_control_battery(workspace)
            report = _probe(handle, battery)

            assert report.battery_verdict is not BatteryVerdict.VACUOUS
            assert report.battery_verdict is BatteryVerdict.CONSISTENT
            control_outcome = next(
                o for o in report.outcomes if o.probe_name == "workspace-write-control"
            )
            assert control_outcome.verdict is Verdict.PASS
        finally:
            _teardown_group(handle)
    finally:
        shutil.rmtree(workspace)


# ---------------------------------------------------------------------------
# AC #3 -- controls run before other probes, proven by what the probes
# themselves did inside the jail, not by reading the runner's source.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_controls_run_before_other_probes(run_id: str) -> None:
    """AC #3. The battery declares its non-`CONTROL` probe FIRST and its
    `CONTROL` probe SECOND -- so if `run_battery` merely preserved
    declaration order, the control would run second.

    Each probe appends its own name to a shared file as its side effect,
    so the order is read from what the two processes ACTUALLY did, in the
    jail, in wall-clock order. That used to be read out of the jail's
    `events.jsonl` (each probe identifiable by its recorded `EXEC` argv);
    decision-152 (2026-09-08) deleted the stream, and a side effect the
    probes write themselves is a stronger observation than a record brig
    wrote about them anyway -- it cannot be right while the execution is
    wrong. The non-control probe still exits non-zero, so its `DENIAL`
    shape is unchanged."""
    order_dir = _new_root(run_id, "ord")
    os.makedirs(order_dir, exist_ok=True)
    order_path = os.path.join(order_dir, "order.txt")
    other = Probe(
        name="other-denial",
        shape=ProbeShape.DENIAL,
        axis=Axis.LIMITS,
        argv=("/bin/sh", "-c", f"echo other >> {order_path}; exit 1"),
        expect=Expectation(),
    )
    control = Probe(
        name="the-control",
        shape=ProbeShape.CONTROL,
        axis=Axis.LIMITS,
        argv=("/bin/sh", "-c", f"echo control >> {order_path}"),
        expect=Expectation(token=None),
    )
    # Declared non-control FIRST -- the ordering claim under test is that
    # `run_battery` reorders this, not that it merely echoes declaration
    # order.
    battery = Battery(name="t050-ordering", axis=Axis.LIMITS, probes=(other, control))

    handle = _launch(
        Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t050-ac3", run_id=run_id
    )
    try:
        _probe(handle, battery)

        with open(order_path) as f:
            ran = [line.strip() for line in f if line.strip()]
        assert ran == ["control", "other"], (
            f"expected the CONTROL probe to run before the non-control probe, got order {ran!r}"
        )
    finally:
        _teardown_group(handle)
        shutil.rmtree(order_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC #4 -- a probe that contradicts an ENFORCED/BEST_EFFORT/COOPERATIVE
# grade fails the battery loudly; a FAIL against UNENFORCED is consistent
# (MILESTONES M4 EC1's parenthetical).
# ---------------------------------------------------------------------------


def _contradiction_battery() -> Battery:
    """One `CONTROL` probe that always succeeds (satisfies `Battery`'s own
    construction requirement) plus one `DENIAL` probe whose argv
    (`/usr/bin/true`) always exits 0 -- which `classify` (unmodified, per
    this task's Out of scope) turns into `Verdict.FAIL` unconditionally,
    regardless of any signature claim: "the attempt succeeded; the claim is
    false" (SPEC.md §12). This isolates the contradiction-table logic from
    real per-mechanism enforcement."""
    control = Probe(
        name="always-pass-control",
        shape=ProbeShape.CONTROL,
        axis=Axis.NETWORK,
        argv=("/bin/sh", "-c", "echo t050ctrlpass"),
        expect=Expectation(token="t050ctrlpass"),
    )
    denial = Probe(
        name="always-succeeds-denial",
        shape=ProbeShape.DENIAL,
        axis=Axis.NETWORK,
        argv=("/usr/bin/true",),
        expect=Expectation(),
    )
    return Battery(name="t050-contradiction", axis=Axis.NETWORK, probes=(control, denial))


@pytest.mark.integration
def test_a_probe_that_contradicts_an_enforced_grade_fails_the_battery(run_id: str) -> None:
    """AC #4. `handle.report` is forced to grade `Axis.NETWORK` `ENFORCED`
    (`_with_axis_grade`); the battery's `DENIAL` probe verdicts `FAIL`
    (see `_contradiction_battery`'s docstring). `battery_verdict` is
    `BatteryVerdict.CONTRADICTED` and `report.contradictions` is non-empty
    and names the axis."""
    handle = _launch(
        Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t050-ac4", run_id=run_id
    )
    try:
        enforced_handle = _with_axis_grade(handle, Axis.NETWORK, Grade.ENFORCED)
        battery = _contradiction_battery()
        report = _probe(enforced_handle, battery)

        assert report.battery_verdict is BatteryVerdict.CONTRADICTED
        assert report.contradictions != ()
        assert any(Axis.NETWORK.value in c for c in report.contradictions), report.contradictions
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_the_same_fail_against_an_unenforced_grade_is_consistent(run_id: str) -> None:
    """AC #4's named control (MILESTONES M4 EC1's parenthetical): the
    IDENTICAL battery (`_contradiction_battery`, so the identical probe
    verdicts `FAIL` for the identical reason) against a handle whose
    `Axis.NETWORK` grades `UNENFORCED` -- the empty stack's own natural,
    unmodified grade, since neither mechanism in `Stack([])` claims
    `Axis.NETWORK` -- leaves `report.contradictions` empty and does NOT
    make the battery `FAIL`."""
    handle = _launch(
        Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t050-ac4-control", run_id=run_id
    )
    try:
        assert handle.report.grade_for(Axis.NETWORK).grade is Grade.UNENFORCED
        battery = _contradiction_battery()
        report = _probe(handle, battery)

        assert report.contradictions == ()
        assert report.battery_verdict is not BatteryVerdict.CONTRADICTED
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #5 -- probes run through handle.exec and therefore inside the real
# confinement, with an empty-stack control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_probes_run_through_handle_exec_and_therefore_inside_the_confinement(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #5. `degraded()` under `EnvPolicy(SCRUB, allow_names=("PATH",
    "HOME"))`, with a canary set in the LAUNCHING (this test) process's own
    environment. A one-probe (`CONTROL`-shaped, so it also satisfies
    `Battery`'s own construction rule) battery whose argv is
    `/usr/bin/env` runs through `handle.probe` -- its recorded outcome's
    `subject` (== the probe's captured stdout for a non-`DENIAL` shape,
    `brig/core/probes.py`'s own docstring) does NOT contain the canary,
    proving the probe ran through the SAME scrubbed environment
    `handle.exec` gives the workload, not the test process's own.

    THE CONTROL, in the same test: the IDENTICAL battery against
    `Stack([])` (`wrap_prefix == ()`, unscrubbed) DOES see the canary --
    without this, "the canary is absent" could just as easily mean "the
    probe never ran" as "the probe ran scrubbed"."""
    canary_name = f"BRIG_T050_CANARY_{run_id}"
    monkeypatch.setenv(canary_name, "leak-if-visible")

    probe = Probe(
        name="env-dump-control",
        shape=ProbeShape.CONTROL,
        axis=Axis.ENV,
        argv=("/usr/bin/env",),
        expect=Expectation(token="PATH="),
    )
    battery = Battery(name="t050-env-confinement", axis=Axis.ENV, probes=(probe,))

    spec = Spec(
        limits=Limits(cpu_seconds=60),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH", "HOME")),
    )
    scrubbed_handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="jail-t050-ac5", run_id=run_id
    )
    control_handle = _launch(
        Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t050-ac5-control", run_id=run_id
    )
    try:
        scrubbed_report = _probe(scrubbed_handle, battery)
        scrubbed_outcome = scrubbed_report.outcomes[0]
        assert canary_name not in scrubbed_outcome.subject, (
            f"{canary_name!r} leaked into a probe run through a SCRUB'd handle: "
            f"{scrubbed_outcome.subject!r}"
        )
        assert "PATH=" in scrubbed_outcome.subject

        control_report = _probe(control_handle, battery)
        control_outcome = control_report.outcomes[0]
        assert canary_name in control_outcome.subject
    finally:
        _teardown_group(scrubbed_handle)
        _teardown_group(control_handle)


# ---------------------------------------------------------------------------
# AC #6 -- Handle.probe is a bound method returning battery.run's report;
# run imports nothing from probe (grep evidence, pasted separately).
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _RecordingBattery:
    """A test-only stand-in satisfying `core.probes.Battery`'s `Protocol`
    shape (`name: str`, `run(self, handle: object) -> ProbeReport`) that
    records exactly one thing: the `handle` object it was called with. Its
    `run` never touches `handle.exec` at all -- this test's subject is
    `Handle.probe`'s OWN delegation, not the probe engine underneath it,
    same isolation `test_handle_delegates.py` uses for `kill`/`exec`."""

    name: str
    _report: ProbeReport
    seen_handle: object = None

    def run(self, handle: object) -> ProbeReport:
        self.seen_handle = handle
        return self._report


@pytest.mark.integration
def test_handle_probe_is_a_bound_method_returning_the_battery_report(run_id: str) -> None:
    """AC #6. `handle.probe(battery)` returns the EXACT SAME `ProbeReport`
    object `battery.run(handle)` would (identity, via a battery whose `run`
    is instrumented to record its call and hand back a fixed report), and
    the battery's own `run` was called with `handle` itself (identity, not
    equality)."""
    handle = _launch(
        Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t050-ac6", run_id=run_id
    )
    try:
        fixed_report = ProbeReport(
            outcomes=(),
            battery_name="recording",
            battery_verdict=BatteryVerdict.CONSISTENT,
            contradictions=(),
        )
        battery = _RecordingBattery(name="recording", _report=fixed_report)

        result = handle.probe(battery)

        assert result is fixed_report
        assert battery.seen_handle is handle
        assert result == battery.run(handle)
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #7 -- the battery-verdict ORDER: a failed control dominates a
# contradiction, never the reverse.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_failed_control_dominates_a_contradiction(run_id: str) -> None:
    """AC #7: the case a rule written in the wrong order gets backwards. A
    battery carrying BOTH a failing `CONTROL` (writes into a `chmod 0o500`
    workspace) AND a contradicting `DENIAL` probe (`/usr/bin/true`, always
    `FAIL`, against a handle forced to grade the axis `ENFORCED`) -- if
    `run_battery` checked contradictions before the control, this would
    read `BatteryVerdict.CONTRADICTED`; the correct order reads
    `BatteryVerdict.VACUOUS` (task-053 AC #15 proves this order by
    mutation: reordering the branches makes this exact test fail)."""
    workspace = _new_root(run_id, "ws")
    os.makedirs(workspace)
    os.chmod(workspace, stat.S_IRUSR | stat.S_IXUSR)  # 0o500: no write
    try:
        control = Probe(
            name="failing-workspace-control",
            shape=ProbeShape.CONTROL,
            axis=Axis.FS_WRITE,
            argv=("/bin/sh", "-c", f"echo t050ok > {workspace}/probe.txt"),
            expect=Expectation(token="t050ok"),
        )
        denial = Probe(
            name="contradicting-denial",
            shape=ProbeShape.DENIAL,
            axis=Axis.FS_WRITE,
            argv=("/usr/bin/true",),
            expect=Expectation(),
        )
        battery = Battery(
            name="t050-control-dominates", axis=Axis.FS_WRITE, probes=(control, denial)
        )

        handle = _launch(
            Stack([]), Spec(), _sleep_workload(run_id), jail_id="jail-t050-ac7", run_id=run_id
        )
        try:
            enforced_handle = _with_axis_grade(handle, Axis.FS_WRITE, Grade.ENFORCED)
            report = _probe(enforced_handle, battery)

            assert report.contradictions != ()  # the contradiction really is present
            # `is BatteryVerdict.VACUOUS` -- never `BatteryVerdict.CONTRADICTED` --
            # is the whole claim under test here: `BatteryVerdict` members are
            # mutually exclusive, so this single assertion already rules
            # CONTRADICTED out (mypy narrows the two as non-overlapping literals; a
            # separate `is not BatteryVerdict.CONTRADICTED` assert is flagged
            # `comparison-overlap` under --strict as redundant).
            assert report.battery_verdict is BatteryVerdict.VACUOUS
        finally:
            _teardown_group(handle)
    finally:
        os.chmod(workspace, stat.S_IRWXU)
        shutil.rmtree(workspace)
