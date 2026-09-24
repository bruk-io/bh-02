"""`brig.stack.degraded()`: the golden seven-axis report, exactly (task-039).

MILESTONES.md M3 EC4, verbatim:

    4. Report aggregation: `degraded()` preset's report is exactly the
       golden grades (snapshot-tested as data, reviewed by hand once).

SPEC.md §7's construction-time invariant:

    An `EnforcementReport` carries a `Graded` for all seven axes of §4;
    constructing one with an axis missing raises, naming that axis.

**Two mechanisms, not three -- RULED by decision-062** (operator round 7,
A3 accepted, and no stub proxy -- SPEC.md §2 law 2). SPEC.md §7's own
`degraded()` is `[env_scrub, rlimits, connect_proxy(env-routed)]`;
`connect_proxy` is M6, so this preset's `network` axis is honestly
`unenforced` and the golden below is versioned so M6's addition of the
proxy is a visible, reviewed diff, not a silent one.

**The golden is written as literal data, not derived from the mechanisms'
own constants** (`brig.mech.rlimits._BEST_EFFORT_DETAIL` is never
imported here): the whole point of a hand-reviewed snapshot is that a
change to what a mechanism claims -- including a one-word change to a
detail string -- shows up as a diff against fixed text a reviewer already
read, not as two sides of an equality that drift together silently. See
AC #4's mutation pairing below.
"""

from __future__ import annotations

import pytest

from brig.core import AXES, Axis, EnvMode, EnvPolicy, FloorViolation, Grade, Graded, Spec, require
from brig.mech.env_scrub import _SCRUB_DETAIL as _ENV_DETAIL
from brig.stack import degraded

# ---------------------------------------------------------------------------
# AC #1 / AC #7: the golden, reviewed by hand.
#
# Reviewed by: ATTEMPT 1 IMPLEMENTER (Sonnet, route:sonnet), 2026-08-23,
# task-039. Method: for each of the seven axes, read the mechanism source
# that produces the grade -- not the Graded(...) call site's own claim --
# and confirm the grade against that evidence:
#
#   - fs_read, fs_write, network, channel_exclusivity, control: UNENFORCED,
#     detail "". Checked by reading `EnvScrub.axes` (`frozenset({Axis.ENV})`)
#     and `Rlimits.axes` (`frozenset({Axis.LIMITS})`) in
#     brig/mech/env_scrub.py and brig/mech/rlimits.py -- neither of the two
#     M3 mechanisms claims any of these five axes, and no third mechanism
#     exists in brig/mech/ as of this task (`connect_proxy` is M6,
#     decision-062), so all five enter the compiled report via
#     `unenforced_report()`'s fill in `Stack.compile`, never overlaid.
#   - limits: BEST_EFFORT, detail names cpu-only coverage. Checked against
#     brig/mech/trampoline/__init__.py's `_apply_limits`, which calls
#     `resource.setrlimit` exactly once, on `resource.RLIMIT_CPU` -- no
#     RLIMIT_AS/RLIMIT_NPROC/wall-clock/output-byte limit is ever set on
#     this host by any code this stack composes. The detail's "uncovered:
#     memory, tasks, wall, output" list matches that absence exactly, and
#     decision-061 rules the axis-level grade BEST_EFFORT (not ENFORCED)
#     precisely because `Graded` has no sub-field structure to say
#     "enforced on cpu, absent elsewhere" any other way.
#   - env: ENFORCED, detail "". Checked against real observed behaviour,
#     not env_scrub's own docstring claim:
#     tests/integration/test_env_scrub.py::test_env_scrub_hides_the_canary_and_forwards_the_allowlist
#     (task-034's EC1) launches a real workload through a Stack containing
#     env_scrub, with a canary env var NOT on the allow-list, and asserts
#     -- reading the CHILD's own printed environment from inside the jail,
#     never the outside argv -- that the canary is absent while the
#     allow-listed name survives. Its named control,
#     ::test_control_without_env_scrub_the_same_probe_sees_the_secret, runs
#     the identical probe with env_scrub removed from the stack and asserts
#     the SAME canary IS visible -- the discriminating half that rules out
#     "the probe just never looked." That pair of integration-tier tests is
#     what the ENFORCED grade rests on here, not the mechanism's
#     self-report.
#
# Spec-dependence, checked directly: EnvScrub.compile grades Axis.ENV: ENFORCED only under
# EnvPolicy(mode=SCRUB) and grades nothing at all under PASS (brig/mech/env_scrub.py, one branch,
# SPEC.md section 6 / decision-092) -- so this golden IS a statement about a SCRUB spec. _spec()
# returns Spec(), whose EnvPolicy.mode defaults to SCRUB (brig/core/spec.py), which is why these
# grades still hold. The PASS case is asserted separately by
# test_degraded_under_pass_env_grades_env_unenforced in this file, and Rlimits.compile still
# grades Axis.LIMITS: BEST_EFFORT unconditionally.
#
# Every detail string below is copied by hand from the mechanism source at
# review time (not imported) -- see this file's module docstring.
# ---------------------------------------------------------------------------

_LIMITS_DETAIL = (
    "rlimits enforces the limits axis for cpu only (RLIMIT_CPU, via the "
    "exec trampoline); uncovered: memory, tasks, wall, output"
)

GOLDEN: dict[Axis, Graded] = {
    Axis.FS_READ: Graded(Grade.UNENFORCED, ""),
    Axis.FS_WRITE: Graded(Grade.UNENFORCED, ""),
    Axis.NETWORK: Graded(Grade.UNENFORCED, ""),
    Axis.LIMITS: Graded(Grade.BEST_EFFORT, _LIMITS_DETAIL),
    Axis.ENV: Graded(Grade.ENFORCED, _ENV_DETAIL),
    Axis.CHANNEL_EXCLUSIVITY: Graded(Grade.UNENFORCED, ""),
    Axis.CONTROL: Graded(Grade.UNENFORCED, ""),
}


def _spec() -> Spec:
    return Spec()


# ---------------------------------------------------------------------------
# AC #1: the golden, exact.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_degraded_report_matches_golden_exactly() -> None:
    """AC #1: degraded().compile(Spec()).report equals GOLDEN by full
    structural equality -- every one of the seven axes, its grade, AND its
    detail string. Not membership, not a subset check: `==` on the
    axes mapping, which compares every key and every Graded value.
    """
    compiled = degraded().compile(_spec())
    assert dict(compiled.report.axes) == GOLDEN, (
        "degraded() report drifted from the reviewed golden; see this "
        "file's module docstring: a golden that changes is a change to "
        "what brig claims, and must be re-reviewed, not silently accepted"
    )


# ---------------------------------------------------------------------------
# AC #3 (task-044): env_scrub under PASS claims nothing, so degraded()'s
# env axis falls to §7's coverage fill as UNENFORCED, exactly like an axis
# no mechanism declared. Named control: the golden above is a SCRUB-mode
# statement, and SCRUB still matches it exactly.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_degraded_under_pass_env_grades_env_unenforced() -> None:
    """AC #3: under `EnvPolicy(mode=PASS)`, `env_scrub` claims nothing on
    the env axis (SPEC.md §6 / decision-092, P-12, task-044's own spec
    anchor) -- `Step.grades` is the empty mapping for this mechanism, so
    `degraded()`'s aggregate report never overlays `Axis.ENV` at all, and
    it falls through to `unenforced_report()`'s fill exactly like an axis
    no mechanism declared: `Graded(UNENFORCED, "")`, not the SCRUB-only
    `ENFORCED` the GOLDEN above pins."""
    compiled = degraded().compile(Spec(env=EnvPolicy(mode=EnvMode.PASS)))
    assert compiled.report.grade_for(Axis.ENV) == Graded(Grade.UNENFORCED, "")


@pytest.mark.unit
def test_degraded_under_scrub_env_still_matches_golden() -> None:
    """AC #3's named control: the default `Spec()` (`EnvPolicy.mode`
    defaults to `SCRUB`, `brig/core/spec.py`) still compiles to
    `GOLDEN[Axis.ENV]` exactly -- the PASS case above is a genuine branch
    on `EnvPolicy.mode`, not a change to what SCRUB grades. Without this
    control, the PASS test above cannot distinguish "PASS claims nothing"
    from "env_scrub stopped claiming ENFORCED at all"."""
    compiled = degraded().compile(_spec())
    assert compiled.report.axes[Axis.ENV] == GOLDEN[Axis.ENV]


# ---------------------------------------------------------------------------
# AC #2: coverage -- all seven axes, by set equality against AXES.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_degraded_report_covers_exactly_the_seven_axes() -> None:
    """AC #2: the compiled report's axis keys equal AXES exactly (set
    equality, not membership) -- SPEC.md §7's construction-time coverage
    invariant was not bypassed by degraded()'s own aggregation path.
    """
    compiled = degraded().compile(_spec())
    assert set(compiled.report.axes) == set(AXES)
    assert set(GOLDEN) == set(AXES)


# ---------------------------------------------------------------------------
# AC #5: network axis is honestly unenforced; docstring names the M6 gap.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_degraded_network_axis_is_unenforced() -> None:
    """AC #5: degraded() has no network mechanism, so it must not claim
    anything stronger on this axis than the empty stack would. decision-140
    kept it that way at M6 -- connect_proxy ships in
    `confined_egress_darwin()`, not here."""
    compiled = degraded().compile(_spec())
    assert compiled.report.axes[Axis.NETWORK].grade is Grade.UNENFORCED


@pytest.mark.unit
def test_degraded_docstring_names_connect_proxy_as_m6_addition() -> None:
    """AC #5 (second half): degraded()'s own docstring names connect_proxy
    as the mechanism M6 adds, and says the report changes then -- the claim
    that this preset is honestly incomplete has to be written where a
    reader of the function itself finds it, not only in this test file.
    """
    doc = degraded.__doc__
    assert doc is not None
    assert "connect_proxy" in doc
    assert "M6" in doc


# ---------------------------------------------------------------------------
# AC #6: floors interact correctly, both directions.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_require_env_enforced_compiles_against_degraded() -> None:
    """AC #6 (control): require(env=ENFORCED) is exactly what degraded()
    delivers on the env axis, so compile succeeds."""
    compiled = degraded().compile(_spec(), require(env=Grade.ENFORCED))
    assert compiled.report.axes[Axis.ENV].grade is Grade.ENFORCED


@pytest.mark.unit
def test_require_network_enforced_refuses_against_degraded() -> None:
    """AC #6: require(network=ENFORCED) against degraded() refuses at
    compile, naming the network axis and the shortfall -- the refusal
    alone cannot distinguish "floors work" from "compile is broken", so
    this is paired with the control above (env=ENFORCED, which succeeds).
    """
    floors = require(network=Grade.ENFORCED)
    with pytest.raises(FloorViolation) as exc_info:
        degraded().compile(_spec(), floors)
    shortfalls = exc_info.value.shortfalls
    assert len(shortfalls) == 1
    shortfall = shortfalls[0]
    assert shortfall.axis is Axis.NETWORK
    assert shortfall.required is Grade.ENFORCED
    assert shortfall.actual is Grade.UNENFORCED


# ---------------------------------------------------------------------------
# Sanity: degraded() is data, ships exactly the two M3 mechanisms.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_degraded_ships_exactly_rlimits_and_env_scrub() -> None:
    """degraded() is a two-mechanism Stack -- exactly {rlimits, env_scrub}.

    **This stayed two, and decision-140 is why.** SPEC.md §7 defines the
    preset as three, and decision-062 planned connect_proxy joining at M6;
    implementing that broke seven test modules, because a preset declaring a
    JAIL_LIFETIME helper can no longer be compiled-and-inspected with
    `ctx=None` -- it must be LAUNCHED. connect_proxy also enforces nothing
    here, since this preset carries no confinement to make anyone honour the
    proxy variables. It lives in `confined_egress_darwin()` instead.
    """
    names = {mechanism.name for mechanism in degraded().mechanisms}
    assert names == {"rlimits", "env_scrub"}
    assert len(degraded().mechanisms) == 2
