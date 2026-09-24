"""`run_battery`: SPEC.md §12's probe engine -- runs a `Battery`'s probes
through the SAME `handle.exec` path the workload uses, classifies each
result, and decides the battery's own verdict.

SPEC.md §12's opening, verbatim:

    `handle.probe(battery)` runs canned violation attempts **inside the
    jail, through the same stack, launcher, and channel the workload
    uses** -- a policy that holds for a side shell but not for the real
    path is not a policy.

SPEC.md §9, verbatim:

    - Probes (§12) run *through* `exec`, which is what makes them exercise
      the real path -- probe and exec are the same machinery, one canned
      and judged, one free-form.

and, on contradiction, verbatim:

    Probe outcomes are checked against the report's grades: a probe that
    contradicts a grade fails the battery loudly.

MILESTONES.md M4 EC2, verbatim:

    2. Positive controls: a battery run where the workspace-write control
       fails marks the whole battery VACUOUS, not passed -- demonstrated
       by pointing the battery at a non-writable workspace.

MILESTONES.md M4 EC1's parenthetical, verbatim -- the asymmetry the
contradiction table below encodes:

    fs/network probes report honestly (FAIL where genuinely unenforced -- a
    FAIL against an `unenforced` grade is *consistent*, not a
    contradiction).

**Why `handle` is typed `Any`, not `brig.run.handle.Handle`.** `probe` may
import `run` (`pyproject.toml`'s `[tool.pypeeker.brig-layers.allow]`), so
naming `Handle` here would not itself be a layer or cycle violation -- the
reason is `Battery.run`'s own signature. `core.probes.Battery`'s `Protocol`
declares `run(self, handle: object) -> ProbeReport` (that parameter is
`object`, not `Handle`, because `core` may not import `run` at all -- see
`brig/core/probes.py`'s own docstring). `brig/probe/battery.py`'s concrete
`Battery.run` has to match that shape to satisfy the Protocol, so it also
receives `handle: object` and passes it straight through to this function --
narrowing it to `Handle` here would just move the same widen-or-narrow
mismatch onto that call instead of resolving it. `handle: Any` is the same
choice `brig/run/exec_.py`'s own `exec_in_jail` already made for the
identical shape of tension (see that module's docstring); this function
inherits it rather than fighting it a second time.

**Controls run first, unconditionally** (MILESTONES.md M4 EC2): every
`ProbeShape.CONTROL` probe in `battery.probes` executes, in its original
relative order, before any non-`CONTROL` probe -- but every probe still
runs and is still recorded, control failure or not. The report is evidence,
not just a verdict.

**The contradiction table** (the module docstring's own copy of the task's
deliverable table) reduces to one rule once every row is examined: a
`FAIL` verdict contradicts any report grade other than `UNENFORCED`.
`VACUOUS` never contradicts (a probe that did not run cleanly asserted
nothing), and `PASS` never contradicts -- though a `PASS` against a
`UNENFORCED` or `COOPERATIVE` grade is an honest **under-claim**: the
report graded the axis weaker than the probe's own result would have
justified, and law 1 (never grade up) prefers that direction of mismatch
over its opposite, so it is annotated onto the recorded outcome's `detail`
rather than raised as a contradiction.

This module is impure by necessity -- it drives real subprocess execution
through `handle.exec` and reads their exit status and captured output back
off disk -- unlike every other module in `brig.probe`, which stays pure.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Final

from brig.core import Grade, ProbeOutcome, ProbeReport, ProbeShape, Verdict
from brig.core.probes import BatteryVerdict
from brig.probe.battery import Battery, Probe
from brig.probe.verdict import classify

#: Bounded deadline for one probe's `exec.wait()` (SPEC.md §12 names no
#: number; this task's own Deliverable says only "waits with a bounded
#: deadline"). Generous enough for a probe under `degraded()`'s cpu limits
#: in the shipped batteries (tasks 051-053) without letting one hung probe
#: block a battery run forever.
_PROBE_WAIT_TIMEOUT_S: Final = 15.0

#: Grades a `PASS` verdict against are an honest under-claim, not a
#: contradiction (SPEC.md §12's asymmetry: never grade up).
_UNDERCLAIM_GRADES: Final = (Grade.UNENFORCED, Grade.COOPERATIVE)


def run_battery(handle: Any, battery: Battery) -> ProbeReport:
    """Run every probe in `battery` against `handle`, through `handle.exec`,
    and decide the battery's own verdict.

    **Battery verdict, in this order and no other** (task-050's own
    Deliverable, verbatim algorithm; task-053/decision-104 renamed only the
    fourth branch's result and the third's name, from `Verdict` to
    `BatteryVerdict` -- the ORDER and the CONTRADICTION rule are unchanged):
    any control's own `Verdict` not `PASS` -> `BatteryVerdict.VACUOUS`; else
    any contradiction -> `BatteryVerdict.CONTRADICTED`; else any non-control
    probe's own `Verdict` `VACUOUS` -> `BatteryVerdict.VACUOUS`; else
    `BatteryVerdict.CONSISTENT`.
    """
    controls = [probe for probe in battery.probes if probe.shape is ProbeShape.CONTROL]
    others = [probe for probe in battery.probes if probe.shape is not ProbeShape.CONTROL]

    raw_outcomes = [_run_one(handle, probe) for probe in (*controls, *others)]

    contradictions: list[str] = []
    outcomes: list[ProbeOutcome] = []
    for outcome in raw_outcomes:
        grade = handle.report.grade_for(outcome.axis).grade
        if outcome.verdict is Verdict.FAIL and grade is not Grade.UNENFORCED:
            contradictions.append(
                f"probe {outcome.probe_name!r} (axis {outcome.axis.value!r}): verdict FAIL "
                f"contradicts report grade {grade.value!r}"
            )
            outcomes.append(outcome)
        elif outcome.verdict is Verdict.PASS and grade in _UNDERCLAIM_GRADES:
            outcomes.append(
                dataclasses.replace(
                    outcome,
                    detail=(
                        f"under-claim: probe {outcome.probe_name!r} PASSed against a "
                        f"{grade.value!r} report grade for axis {outcome.axis.value!r} "
                        "(SPEC.md §12: honest under-claiming is not a contradiction)"
                    ),
                )
            )
        else:
            outcomes.append(outcome)

    control_outcomes = [o for o in raw_outcomes if o.shape is ProbeShape.CONTROL]
    failing_control = next((o for o in control_outcomes if o.verdict is not Verdict.PASS), None)

    battery_verdict: BatteryVerdict
    if failing_control is not None:
        battery_verdict = BatteryVerdict.VACUOUS
    elif contradictions:
        battery_verdict = BatteryVerdict.CONTRADICTED
    elif any(
        o.verdict is Verdict.VACUOUS for o in raw_outcomes if o.shape is not ProbeShape.CONTROL
    ):
        battery_verdict = BatteryVerdict.VACUOUS
    else:
        battery_verdict = BatteryVerdict.CONSISTENT

    return ProbeReport(
        outcomes=tuple(outcomes),
        battery_name=battery.name,
        battery_verdict=battery_verdict,
        contradictions=tuple(contradictions),
    )


def _run_one(handle: Any, probe: Probe) -> ProbeOutcome:
    """Run one probe through `handle.exec`, wait for it with a bounded
    deadline, and classify it against `handle.signatures.for_axis(probe.axis)`
    -- the axis's claim, which may be `None`.

    Reads `stdout`/`stderr` back from the exec's own files on disk, exactly
    as `handle.exec` wrote them (SPEC.md §12: probes run through the same
    stack, launcher, and channel the workload uses; this reads what that
    real path actually produced, not an in-process capture)."""
    exec_handle = handle.exec(list(probe.argv))
    returncode = exec_handle.wait(timeout=_PROBE_WAIT_TIMEOUT_S)
    stdout = _read_text(exec_handle.stdout_path)
    stderr = _read_text(exec_handle.stderr_path)
    claim = handle.signatures.for_axis(probe.axis)
    return classify(probe, returncode, stdout, stderr, claim)


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


__all__ = ("run_battery",)
