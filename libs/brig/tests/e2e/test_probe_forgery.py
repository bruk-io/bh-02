"""EC3, MILESTONES.md M4, executed literally (task-054):

    3. Mutation check: weaken a stack (drop `env_scrub`) without changing its
       claimed report (test-local forgery) -- the probe battery *catches the
       contradiction* and fails loudly. This is the probe engine's reason to
       exist; it gets its own test.

`.claude/rules/system-tests.md`, verbatim:

    Full stacks through the public API only: `Spec` -> preset `Stack` ->
    `Launcher` -> `Handle` -> probe battery, exactly as an embedder would
    drive them. No internal imports below the public surface

and:

    - probe forgery detection (a weakened stack with an unchanged claimed
      report is caught);

SPEC.md sec 12, verbatim:

    Probe outcomes are checked against the report's grades: a probe that
    contradicts a grade fails the battery loudly.

Operator ruling round 15 (decision-104) retired the battery-level `PASS`;
every assertion below uses the vocabulary that ruling left in force
(`BatteryVerdict.CONTRADICTED` / `CONSISTENT` at battery altitude,
`Verdict.PASS` / `FAIL` per probe) -- see task-053's own notes for the full
rename history this file inherits rather than re-derives.

**The forgery, built with no brig-internal hook.** `Handle` is a frozen
`dataclass` (`brig/run/handle.py`); `dataclasses.replace` (stdlib) is the
ordinary way to build a new immutable value from an old one with named
fields swapped -- exactly what an embedder holding a real `Handle` would
also have to reach for. Nothing here imports a private constructor or a
test-only seam.

**Public-API-only, and the two names it does not let through cleanly.**
`BatteryVerdict` (SPEC.md sec 12, decision-104) is NOT re-exported by
`brig.core`'s barrel `__init__.py` -- confirmed directly
(`grep -n BatteryVerdict brig/core/__init__.py` matches nothing) and by
task-053's own verifier note: "BatteryVerdict is imported directly from
brig.core.probes everywhere, not through the barrel." `KillOutcome`
(`brig/run/teardown.py`) is the same shape one module over -- every
integration test that names it already imports it the identical way
(`tests/integration/test_kill_group.py`, this file's sibling in
`test_degraded_journey.py`). Per `.claude/rules/system-tests.md`, "if a
system test needs a private hook, the public API is missing something;
file that instead" -- filed as a finding in this task's own closing notes,
not routed around: neither gap blocks building or observing the forgery
through `Handle`'s real public surface, so nothing here reaches for a hook
to compensate. `env_battery` and `CANARY_ENV_NAME` are a *different* case,
not a gap: `brig/probe/batteries/__init__.py`'s own docstring states the
package is "deliberately not a barrel... each battery is imported by its
own module path", so `brig.probe.batteries.env` IS that subpackage's
documented public surface, not a private path around one. Every import
this file's own grep sweep (this task's AC #6) catches is justified on
that same line.

**task-065 (EC3's other half, AC #5/#6): the same forgery, carried onto
`scratch_darwin()`.** The three functions at the bottom of this file --
darwin-gated, since `scratch_darwin()` composes `seatbelt`
(`sandbox-exec`/SBPL, darwin-only) where this file's original M4 trio above
does not -- reproduce the identical shape one axis and one mechanism over:
`Axis.FS_WRITE` claimed by `seatbelt`, not `Axis.ENV` claimed by
`env_scrub`. The weakened stack drops `seatbelt` (`Stack([rlimits,
env_scrub])` -- `scratch_darwin()` minus its one darwin-only mechanism,
same "drop one mechanism" shape as the M4 trio's `Stack([rlimits])`), and
the forged claim is copied from a REAL `scratch_darwin().compile(spec,
ctx=...)` -- never hand-built -- for the identical reason the M4 trio's own
docstring states it. `BatteryVerdict`, `Handle`, `SubprocessLauncher`,
`Stack`, `degraded`, `_new_root`, `_teardown_group`, and `_probe` above are
all reused UNCHANGED, not reimplemented -- this is one file extended, not
two files sharing a shape by accident (this task's own Deliverable: "M4's
`test_probe_forgery.py` is plant-proved load-bearing... Carry its structure
onto `scratch_darwin()`").
"""

from __future__ import annotations

import dataclasses
import itertools
import os
import sys
from collections.abc import Sequence
from typing import cast

import pytest

from brig.core import (
    Axis,
    EnforcementReport,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    Grade,
    ProbeReport,
    ProbeShape,
    SignatureBook,
    Spec,
    Verdict,
)
from brig.core import Battery as CoreBattery
from brig.core.probes import BatteryVerdict  # not barrel-exported; justified above and in AC #6
from brig.mech import env_scrub, rlimits
from brig.probe.batteries.env import CANARY_ENV_NAME, env_battery  # batteries: no barrel, by design
from brig.probe.batteries.fs import fs_write_battery
from brig.run import Handle, IoPolicy, SubprocessLauncher, build_compile_ctx
from brig.stack import Stack, degraded, scratch_darwin
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()


def _new_root(run_id: str, tag: str) -> str:
    """A short scratch root, `/tmp/bg<pid><tag><run_id[:8]><n>` -- never
    `tmp_path` (`sun_path` is 104 bytes on darwin; CLAUDE.md's own trap
    list). The `pf` infix (this file's own tag below) keeps this file's
    counter from colliding with a sibling e2e file's own."""
    return f"/tmp/bg{os.getpid()}{tag}{run_id[:8]}{next(_jail_counter)}"


def _launch(stack: Stack, spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str) -> Handle:
    """`Spec -> preset/weakened Stack -> Launcher -> Handle`, exactly the
    public chain `.claude/rules/system-tests.md` names -- `stack.compile`
    and `SubprocessLauncher().launch` are both public methods on public
    types, never an internal helper."""
    jail_dir = _new_root(run_id, "pf")
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
    """Group-kill the long-lived workload. The kill is hand-rolled rather
    than `Handle.kill()`, same reasoning as the integration tier's own
    `_teardown_group` helpers: a test's cleanup path must not be the code
    under test (`handle.probe(...)` is what these tests exist to exercise,
    not what tears them down afterward). `handle.wait()` blocks until the
    launcher's exit-waiter has reaped it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _probe(handle: Handle, battery: object) -> ProbeReport:
    """`handle.probe(battery)` through a `cast` to `core.probes.Battery` --
    the same idiom the integration tier's own `_probe` helpers use: a
    concrete `brig.probe.battery.Battery` satisfies that `@runtime_
    checkable` `Protocol` at runtime, but mypy --strict flags it statically
    (`Protocol member Battery.name expected settable variable, got
    read-only attribute` -- a frozen dataclass field read against a
    Protocol's default read-write attribute check), so the mismatch is
    silenced with an explicit cast rather than left unresolved."""
    return handle.probe(cast(CoreBattery, battery))


def _env_spec() -> Spec:
    return Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",)))


# ---------------------------------------------------------------------------
# AC #1 / #2 -- the forgery itself.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_weakened_stack_with_an_unchanged_claimed_report_is_caught(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #1 / #2 (EC3). Build a jail from `Stack([rlimits])` -- `degraded()`
    with `env_scrub` REMOVED -- then forge a `Handle` whose `report` and
    `signatures` still carry `env_scrub`'s claim exactly as `degraded()`
    would have produced it (`Axis.ENV` graded `ENFORCED`, with the empty
    `denial_signatures` tuple `env_scrub` declares under SCRUB). Everything
    else about the handle is the weakened stack's own, real, launched
    output -- unchanged.

    The genuine `degraded()` report/claim the forgery copies is never
    hand-built: it comes from `degraded().compile(spec)`, a real
    `Stack.compile` call against the SAME spec, so the forged values are
    exactly what a caller of `degraded()` would actually have seen -- not
    an approximation of it.
    """
    monkeypatch.setenv(CANARY_ENV_NAME, "topsecret-should-leak-here")
    spec = _env_spec()

    genuine = degraded().compile(spec)
    genuine_env_graded = genuine.report.axes[Axis.ENV]
    assert genuine_env_graded.grade is Grade.ENFORCED, (
        "sanity: degraded() must actually claim ENV ENFORCED, or this test would "
        "not be forging anything"
    )
    genuine_env_claim = genuine.signatures.for_axis(Axis.ENV)
    assert genuine_env_claim is not None
    assert genuine_env_claim.signatures == (), (
        "sanity: env_scrub's own claim carries the empty tuple (SPEC.md sec 6) -- "
        "the exact shape the forgery must preserve so it cannot go red for the "
        "wrong reason (AC #2)"
    )

    weakened = Stack([rlimits])  # degraded() with env_scrub dropped
    handle = _launch(
        weakened, spec, workload_argv(run_id, "sleep 100"), jail_id="pf-forgery", run_id=run_id
    )
    try:
        assert handle.report.axes[Axis.ENV].grade is Grade.UNENFORCED, (
            "sanity: the weakened stack's OWN report must honestly grade ENV "
            "unenforced -- nothing here claims it"
        )
        assert handle.signatures.for_axis(Axis.ENV) is None, (
            "sanity: the weakened stack's OWN signature book must carry no ENV "
            "claim -- nothing here claims it either"
        )

        forged_axes = dict(handle.report.axes)
        forged_axes[Axis.ENV] = genuine_env_graded
        forged_report = EnforcementReport(axes=forged_axes)
        forged_signatures = SignatureBook(claims=(*handle.signatures.claims, genuine_env_claim))
        forged_handle = dataclasses.replace(
            handle, report=forged_report, signatures=forged_signatures
        )

        # AC #2: the forgery keeps the SignatureBook claim, BEFORE the
        # battery ever runs -- so a CONTRADICTED verdict below cannot be
        # explained by "the claim was simply missing".
        forged_claim = forged_handle.signatures.for_axis(Axis.ENV)
        assert forged_claim is not None
        assert forged_claim.signatures == ()

        report = _probe(forged_handle, env_battery(spec))

        # AC #1: caught, and CAUGHT BY AXIS -- not merely "not CONSISTENT".
        assert report.battery_verdict is BatteryVerdict.CONTRADICTED
        assert report.contradictions != ()
        axis_marker = f"axis {Axis.ENV.value!r}"
        assert any(axis_marker in c for c in report.contradictions), (
            f"expected a contradiction naming {axis_marker!r}, got {report.contradictions!r}"
        )
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #3 -- control one: the same battery, the real degraded() jail, no forgery.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_control_the_unforged_degraded_jail_is_consistent_on_the_same_battery(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #3. The IDENTICAL battery, against a real, unweakened `degraded()`
    jail carrying its own genuine report -- no substitution anywhere. This
    is the discriminating half stated at BOTH altitudes: the battery-level
    `CONSISTENT` (with no contradictions) AND the env ABSENCE probe's own
    `Verdict.PASS`, so a summary word alone can never stand in for it.
    """
    monkeypatch.setenv(CANARY_ENV_NAME, "topsecret-should-not-leak")
    spec = _env_spec()
    handle = _launch(
        degraded(),
        spec,
        workload_argv(run_id, "sleep 100"),
        jail_id="pf-control-real",
        run_id=run_id,
    )
    try:
        report = _probe(handle, env_battery(spec))
        assert report.battery_verdict is BatteryVerdict.CONSISTENT
        assert report.contradictions == ()
        absence = next(o for o in report.outcomes if o.probe_name == "scrubbed_name_is_absent")
        assert absence.verdict is Verdict.PASS
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #4 -- control two: the same weakened stack, its own honest report.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_control_the_weakened_stack_with_an_HONEST_report_does_not_contradict(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #4. The SAME weakened stack as the forgery test (`env_scrub`
    dropped), but carrying its OWN honestly-compiled report (`Axis.ENV`
    `UNENFORCED`) -- no substitution. Three explicit assertions, so this
    control cannot pass on a probe that never ran and cannot be mistaken
    for the forgery test's own CONTRADICTED case:

    - `contradictions` is EMPTY;
    - the env ABSENCE probe's OWN verdict is `Verdict.FAIL` -- the
      violation really did succeed (the canary genuinely leaks with
      `env_scrub` gone), so this is not a probe that quietly never looked;
    - `battery_verdict` is `BatteryVerdict.CONSISTENT`, because a `FAIL`
      against an honestly `UNENFORCED` grade is consistency, not a
      contradiction (SPEC.md sec 12).

    This is the distinction EC3 is about: the forgery test goes
    CONTRADICTED because the CLAIM was dishonest, not because the stack was
    weak -- this control proves the weakness alone, honestly reported,
    never contradicts anything.
    """
    monkeypatch.setenv(CANARY_ENV_NAME, "topsecret-should-leak-here")
    spec = _env_spec()
    weakened = Stack([rlimits])
    handle = _launch(
        weakened,
        spec,
        workload_argv(run_id, "sleep 100"),
        jail_id="pf-control-honest",
        run_id=run_id,
    )
    try:
        report = _probe(handle, env_battery(spec))
        assert report.contradictions == ()
        absence = next(o for o in report.outcomes if o.probe_name == "scrubbed_name_is_absent")
        assert absence.verdict is Verdict.FAIL, (
            "the probe must have actually observed the leaking canary -- a probe "
            "that never looked would not discriminate anything"
        )
        assert report.battery_verdict is BatteryVerdict.CONSISTENT
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# task-065 AC #5/#6 -- the SAME forgery, carried onto scratch_darwin().
# Axis.FS_WRITE, claimed by seatbelt, not Axis.ENV claimed by env_scrub.
# Darwin-gated: scratch_darwin() composes seatbelt (sandbox-exec/SBPL).
# ---------------------------------------------------------------------------

_darwin_only = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="scratch_darwin() composes seatbelt (sandbox-exec/SBPL), darwin-only (SPEC.md sec 6)",
)


def _scratch_fs_spec(workspace: str, hooks_dir: str) -> Spec:
    """`write_denies=(hooks_dir,)` is NOT optional here: `write_into_git_
    hooks_carveout`'s target sits INSIDE the granted `write_allows`
    workspace, so without this carve-out seatbelt honestly ALLOWS it --
    proven the hard way (this function originally omitted it, and the real,
    unweakened `scratch_darwin()` control below came back CONTRADICTED, not
    CONSISTENT, because that one probe's own real attempt genuinely
    succeeded against an ENFORCED claim). Same fixture shape
    `tests/integration/test_seatbelt_fs.py`'s own `hooks_dir` uses."""
    return Spec(fs=FsPolicy(write_allows=(workspace,), write_denies=(hooks_dir,)))


def _seed_scratch_fs_targets(run_id: str) -> tuple[str, str, str]:
    """`workspace`, `hooks_dir` (the `.git/hooks` carve-out INSIDE
    workspace -- must also land in `spec.fs.write_denies`, this module's own
    `_scratch_fs_spec` docstring), and `outside_writable` -- the HOST-
    resolved scratch paths `fs_write_battery` needs (doc-016 sec 7 deviation
    4, task-062). The `pfsd` infix family below is THIS file's own --
    deliberately distinct from `test_scratch_darwin_batteries.py`'s `sd*`
    family (both use the same `run_id`+pid; a shared infix would let a
    full `-m system` run's per-module counters collide on path, not merely
    read alike)."""
    workspace = _new_root(run_id, "pfsw")
    hooks_dir = os.path.join(workspace, ".git", "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    outside_writable = _new_root(run_id, "pfso")
    os.makedirs(outside_writable, exist_ok=True)
    return workspace, hooks_dir, outside_writable


def _launch_scratch(
    stack: Stack, spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str
) -> Handle:
    """Same public chain as this file's own `_launch`, but through
    `build_compile_ctx` (`platform=sys.platform`, i.e. `"darwin"` under this
    module's own skip gate) rather than a bare `stack.compile(spec)` --
    required because a genuine `scratch_darwin()` compile needs
    `ctx.platform == "darwin"` (`Seatbelt.compile`'s own `PlatformUnsupported`
    refusal); the weakened stack below (`rlimits` + `env_scrub`, no
    `seatbelt`) does not read `ctx.platform` at all, so one code path serves
    both without branching."""
    jail_dir = _new_root(run_id, "pfsf")
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    jail = stack.compile(spec, ctx=ctx)
    launcher = SubprocessLauncher()
    return launcher.launch(
        jail, argv=list(argv), cwd=jail_dir, io=IoPolicy(), jail_id=jail_id, jail_dir=jail_dir
    )


@pytest.mark.e2e
@_darwin_only
def test_a_weakened_scratch_darwin_stack_with_an_unchanged_claimed_fs_write_report_is_caught(
    run_id: str,
) -> None:
    """task-065 AC #5. Build a jail from `Stack([rlimits, env_scrub])` --
    `scratch_darwin()` with `seatbelt` REMOVED -- then forge a `Handle`
    whose `report` and `signatures` still carry `seatbelt`'s claim exactly
    as `scratch_darwin()` would have produced it for THIS spec
    (`Axis.FS_WRITE` graded `ENFORCED`, with seatbelt's own real declared
    denial-signature tuple -- non-empty, unlike `env_scrub`'s, which is the
    one shape difference from this file's own M4 trio above). Everything
    else about the handle is the weakened stack's own, real, launched
    output -- unchanged.

    The genuine claim the forgery copies comes from a real
    `scratch_darwin().compile(spec, ctx=...)` call against the SAME spec,
    never hand-built -- identical posture to the M4 trio above.
    """
    workspace, hooks_dir, outside_writable = _seed_scratch_fs_targets(run_id)
    spec = _scratch_fs_spec(workspace, hooks_dir)

    genuine_jail_dir = _new_root(run_id, "pfsg")
    genuine_ctx = build_compile_ctx(spec, jail_dir=genuine_jail_dir, platform="darwin")
    genuine = scratch_darwin().compile(spec, ctx=genuine_ctx)
    genuine_fs_write_graded = genuine.report.axes[Axis.FS_WRITE]
    assert genuine_fs_write_graded.grade is Grade.ENFORCED, (
        "sanity: scratch_darwin() must actually claim FS_WRITE ENFORCED, or this "
        "test would not be forging anything"
    )
    genuine_fs_write_claim = genuine.signatures.for_axis(Axis.FS_WRITE)
    assert genuine_fs_write_claim is not None
    assert genuine_fs_write_claim.signatures != (), (
        "sanity: seatbelt's own claim carries a real denial-signature pattern "
        "(unlike env_scrub's empty tuple) -- the exact shape the forgery must "
        "preserve so it cannot go red for the wrong reason"
    )

    weakened = Stack([rlimits, env_scrub])  # scratch_darwin() with seatbelt dropped
    handle = _launch_scratch(
        weakened, spec, workload_argv(run_id, "sleep 100"), jail_id="pfsf-forgery", run_id=run_id
    )
    try:
        assert handle.report.axes[Axis.FS_WRITE].grade is Grade.UNENFORCED, (
            "sanity: the weakened stack's OWN report must honestly grade FS_WRITE "
            "unenforced -- nothing here claims it"
        )
        assert handle.signatures.for_axis(Axis.FS_WRITE) is None, (
            "sanity: the weakened stack's OWN signature book must carry no "
            "FS_WRITE claim -- nothing here claims it either"
        )

        forged_axes = dict(handle.report.axes)
        forged_axes[Axis.FS_WRITE] = genuine_fs_write_graded
        forged_report = EnforcementReport(axes=forged_axes)
        forged_signatures = SignatureBook(
            claims=(*handle.signatures.claims, genuine_fs_write_claim)
        )
        forged_handle = dataclasses.replace(
            handle, report=forged_report, signatures=forged_signatures
        )

        # Before the battery ever runs: the forgery keeps the SignatureBook
        # claim, so a CONTRADICTED verdict below cannot be explained by "the
        # claim was simply missing".
        forged_claim = forged_handle.signatures.for_axis(Axis.FS_WRITE)
        assert forged_claim is not None
        assert forged_claim.signatures != ()

        report = _probe(forged_handle, fs_write_battery(spec, outside_writable=outside_writable))
        print(
            "\n[AC #5 forgery] battery_verdict:",
            report.battery_verdict,
            "contradictions:",
            report.contradictions,
        )

        # Caught, and CAUGHT BY AXIS -- not merely "not CONSISTENT".
        assert report.battery_verdict is BatteryVerdict.CONTRADICTED
        assert report.contradictions != ()
        axis_marker = f"axis {Axis.FS_WRITE.value!r}"
        assert any(axis_marker in c for c in report.contradictions), (
            f"expected a contradiction naming {axis_marker!r}, got {report.contradictions!r}"
        )
    finally:
        _teardown_group(handle)


@pytest.mark.e2e
@_darwin_only
def test_control_the_unforged_scratch_darwin_jail_is_consistent_on_the_same_battery(
    run_id: str,
) -> None:
    """task-065 AC #5, control one. The IDENTICAL battery, against a real,
    unweakened `scratch_darwin()` jail carrying its own genuine report -- no
    substitution anywhere. Both altitudes: the battery-level `CONSISTENT`
    (with no contradictions) AND every DENIAL probe's own `Verdict.PASS`.
    """
    workspace, hooks_dir, outside_writable = _seed_scratch_fs_targets(run_id)
    spec = _scratch_fs_spec(workspace, hooks_dir)
    handle = _launch_scratch(
        scratch_darwin(),
        spec,
        workload_argv(run_id, "sleep 100"),
        jail_id="pfsf-control-real",
        run_id=run_id,
    )
    try:
        report = _probe(handle, fs_write_battery(spec, outside_writable=outside_writable))
        print(
            "\n[AC #5 control 1: unforged scratch_darwin()] battery_verdict:",
            report.battery_verdict,
            "contradictions:",
            report.contradictions,
        )
        assert report.battery_verdict is BatteryVerdict.CONSISTENT
        assert report.contradictions == ()
        for outcome in report.outcomes:
            if outcome.shape is ProbeShape.DENIAL:
                assert outcome.verdict is Verdict.PASS, (outcome.probe_name, outcome.verdict)
    finally:
        _teardown_group(handle)


@pytest.mark.e2e
@_darwin_only
def test_control_the_weakened_scratch_darwin_stack_with_an_HONEST_report_does_not_contradict(
    run_id: str,
) -> None:
    """task-065 AC #5, control two. The SAME weakened stack as the forgery
    test (`seatbelt` dropped), but carrying its OWN honestly-compiled report
    (`Axis.FS_WRITE` `UNENFORCED`) -- no substitution. `contradictions` is
    EMPTY, every DENIAL probe's OWN verdict is `Verdict.FAIL` (the write
    genuinely succeeds with no fs mechanism in the stack, so this is not a
    probe that quietly never looked), and `battery_verdict` is
    `BatteryVerdict.CONSISTENT` -- a `FAIL` against an honestly `UNENFORCED`
    grade is consistency, not a contradiction (SPEC.md sec 12).
    """
    workspace, hooks_dir, outside_writable = _seed_scratch_fs_targets(run_id)
    spec = _scratch_fs_spec(workspace, hooks_dir)
    weakened = Stack([rlimits, env_scrub])
    handle = _launch_scratch(
        weakened,
        spec,
        workload_argv(run_id, "sleep 100"),
        jail_id="pfsf-control-honest",
        run_id=run_id,
    )
    try:
        report = _probe(handle, fs_write_battery(spec, outside_writable=outside_writable))
        print(
            "\n[AC #5 control 2: weakened, honest report] battery_verdict:",
            report.battery_verdict,
            "contradictions:",
            report.contradictions,
        )
        assert report.contradictions == ()
        denial_outcomes = [o for o in report.outcomes if o.shape is ProbeShape.DENIAL]
        assert denial_outcomes, "sanity: fs_write_battery must carry at least one DENIAL probe"
        for outcome in denial_outcomes:
            assert outcome.verdict is Verdict.FAIL, (
                "the probe must have actually observed the write succeed -- a probe "
                f"that never looked would not discriminate anything: {outcome.probe_name}"
            )
        assert report.battery_verdict is BatteryVerdict.CONSISTENT
    finally:
        _teardown_group(handle)
