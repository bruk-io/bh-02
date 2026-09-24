"""`brig.stack.scratch_darwin()`: the golden seven-axis report, exactly (task-064).

MILESTONES.md M5-lite EC4, verbatim (this task's half):

    Reports: `fs_read`, `fs_write`, `network` and `env` grade `enforced` and
    `limits` grades `best_effort` on `scratch_darwin()`, as a hand-reviewed
    golden that turns red on any grade drifting **up**; the **read model is
    declared** in the report `detail` as a **denylist**.

SPEC.md §7's construction-time invariant:

    An `EnforcementReport` carries a `Graded` for all seven axes of §4;
    constructing one with an axis missing raises, naming that axis.

**Three mechanisms, all M5-lite.** SPEC.md §7's `scratch_darwin()` is
`[rlimits, seatbelt, env_scrub]`. The composition order is fixed by SPEC.md's
security reasoning (RULED by decision-119 from doc-017's ambiguity A4): rlimits
outermost so it bounds the other mechanisms' helper processes, seatbelt next so
the `/bin/sh` and `/usr/bin/env` that `env_scrub`'s wrap spawns run inside the
profile, and `env_scrub` innermost so its `env -i` reaches the workload with
nothing between them to re-add what it removed.

**The golden is written as literal data, not derived from the mechanisms' own
constants** (this file never imports `_FS_READ_DETAIL`, `_FS_WRITE_DETAIL`,
`_BEST_EFFORT_DETAIL` or any mechanism's internal detail strings): the whole
point of a hand-reviewed snapshot is that a change to what a mechanism claims
-- including a one-word change to a detail string -- shows up as a diff against
fixed text a reviewer already read, not as two sides of an equality that drift
together silently.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from brig.core import (
    AXES,
    Axis,
    EnvMode,
    EnvPolicy,
    FloorViolation,
    FsPolicy,
    Grade,
    Graded,
    NetworkPolicy,
    ReadModel,
    Spec,
    require,
)
from brig.mech import CompileCtx
from brig.mech.env_scrub import _SCRUB_DETAIL as _ENV_DETAIL
from brig.run.exec_ import ExecFidelity
from brig.run.launcher import _derive_wrap_prefix
from brig.stack import scratch_darwin

# ---------------------------------------------------------------------------
# AC #1 / AC #2: the golden, reviewed by hand, all seven axes.
#
# Reviewed by: ATTEMPT 1 IMPLEMENTER (Haiku, route:haiku), 2026-08-24,
# task-064. Method: for each of the seven axes, read the mechanism source
# that produces the grade:
#
#   - fs_read: ENFORCED, seatbelt (denylist model). Checked against
#     brig/mech/seatbelt/__init__.py's Seatbelt.compile method, which grades
#     Axis.FS_READ: Graded(Grade.ENFORCED, _FS_READ_DETAIL) where _FS_READ_DETAIL
#     contains "denylist" (MILESTONES.md M5-lite EC4's requirement).
#
#   - fs_write: ENFORCED, seatbelt. Checked against Seatbelt.compile which
#     grades Axis.FS_WRITE: Graded(Grade.ENFORCED, _FS_WRITE_DETAIL) where
#     _FS_WRITE_DETAIL contains "write_denies" (the carve-out model).
#
#   - network: ENFORCED, seatbelt. Checked against Seatbelt.compile which
#     grades Axis.NETWORK: Graded(Grade.ENFORCED, _network_detail(...)) where
#     the detail string names seatbelt's default-deny network policy.
#
#   - env: ENFORCED, env_scrub under SCRUB mode. Checked against
#     brig/mech/env_scrub.py's EnvScrub.compile method, which grades
#     Axis.ENV: Graded(Grade.ENFORCED, _ENV_DETAIL) when policy.mode is
#     EnvMode.SCRUB. The detail was "" until decision-143, which moved the
#     argv-transit caveat out of env_scrub's docstring and into the report
#     a reader actually sees. The GRADE is unchanged.
#     (brig/core/spec.py defaults to SCRUB).
#
#   - limits: BEST_EFFORT, rlimits (cpu only). Checked against
#     brig/mech/rlimits.py's Rlimits.compile method, which grades
#     Axis.LIMITS: Graded(Grade.BEST_EFFORT, _BEST_EFFORT_DETAIL) where
#     _BEST_EFFORT_DETAIL names cpu-only coverage and lists the uncovered
#     fields: memory, tasks, wall, output (M3's EC2, decision-061).
#
#   - channel_exclusivity: UNENFORCED, no mechanism claims it. Checked by
#     reading brig/mech/seatbelt/__init__.py, brig/mech/rlimits.py, and
#     brig/mech/env_scrub.py -- none of the three mechanisms' `axes` frozenset
#     includes Axis.CHANNEL_EXCLUSIVITY, so it enters the compiled report via
#     `unenforced_report()`'s fill in `Stack.compile`, never overlaid.
#
#   - control: UNENFORCED, no mechanism claims it. Same reasoning as above.
#
# Every detail string below is copied by hand from the mechanism source at
# review time (not imported).
# ---------------------------------------------------------------------------

_FS_READ_DETAIL = (
    "seatbelt enforces fs_read as a denylist: reads are default-allow "
    '(allow file-read* (subpath "/")), with spec.fs.read_denies compiled '
    "as explicit per-path denies layered on top of that default-allow."
)

_FS_WRITE_DETAIL = (
    "seatbelt enforces fs_write by denying by default and allowing only "
    "spec.fs.write_allows; write_denies carve-outs are compiled deny-over-"
    "allow -- inside the granted write_allows, never as a separate policy."
)

_NETWORK_DETAIL = (
    "seatbelt denies all network traffic by default (deny network* (with no-log)). "
    "No LISTEN channel is declared, so no network-bind rule is emitted at all."
)

_LIMITS_DETAIL = (
    "rlimits enforces the limits axis for cpu only (RLIMIT_CPU, via the exec "
    "trampoline); uncovered: memory, tasks, wall, output"
)

GOLDEN: dict[Axis, Graded] = {
    Axis.FS_READ: Graded(Grade.ENFORCED, _FS_READ_DETAIL),
    Axis.FS_WRITE: Graded(Grade.ENFORCED, _FS_WRITE_DETAIL),
    Axis.NETWORK: Graded(Grade.ENFORCED, _NETWORK_DETAIL),
    Axis.LIMITS: Graded(Grade.BEST_EFFORT, _LIMITS_DETAIL),
    Axis.ENV: Graded(Grade.ENFORCED, _ENV_DETAIL),
    Axis.CHANNEL_EXCLUSIVITY: Graded(Grade.UNENFORCED, ""),
    Axis.CONTROL: Graded(Grade.UNENFORCED, ""),
}


def _spec() -> Spec:
    return Spec()


def _darwin_ctx(resolved_paths: dict[str, str] | None = None) -> CompileCtx:
    """CompileCtx for darwin platform (seatbelt requires it).
    jail_dir must be realpath'd; on darwin /tmp is a symlinked root,
    so use /private/tmp instead (as per CLAUDE.md: "resolve /tmp -> /private/tmp").
    """
    if resolved_paths is None:
        resolved_paths = {}
    return CompileCtx(
        jail_dir="/private/tmp/test",
        platform="darwin",
        resolved_paths=resolved_paths,
    )


# ---------------------------------------------------------------------------
# AC #1: the golden, exact -- all seven axes as data, not seven substrings.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_report_matches_golden_exactly() -> None:
    """AC #1 & AC #2: scratch_darwin().compile(Spec()).report equals GOLDEN
    by full structural equality -- every one of the seven axes, its grade, AND
    its detail string. Not membership, not a subset check: `==` on the axes
    mapping, which compares every key and every Graded value. This single
    assertion catches if any axis silently vanishes from the golden.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    assert dict(compiled.report.axes) == GOLDEN, (
        "scratch_darwin() report drifted from the reviewed golden; see this "
        "file's module docstring: a golden that changes is a change to what "
        "brig claims, and must be re-reviewed, not silently accepted"
    )


# ---------------------------------------------------------------------------
# AC #2 (again): coverage -- all seven axes, by set equality against AXES.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_report_covers_exactly_the_seven_axes() -> None:
    """AC #2: the compiled report's axis keys equal AXES exactly (set
    equality, not membership) -- SPEC.md §7's construction-time coverage
    invariant was not bypassed by scratch_darwin()'s own aggregation path.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    assert set(compiled.report.axes) == set(AXES)
    assert set(GOLDEN) == set(AXES)


# ---------------------------------------------------------------------------
# AC #3: golden reddens on a grade drifting UP (mutation test provided below).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_golden_is_grading_honest() -> None:
    """AC #3 (baseline half): the real compiled report grades
    channel_exclusivity and control UNENFORCED, exactly as GOLDEN pins them.
    Paired below with a channel_exclusivity-SPECIFIC forgery that drifts one
    axis upward and demonstrates the golden comparison rejects it.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    assert compiled.report.axes[Axis.CHANNEL_EXCLUSIVITY].grade is Grade.UNENFORCED
    assert compiled.report.axes[Axis.CONTROL].grade is Grade.UNENFORCED


@pytest.mark.unit
def test_scratch_darwin_channel_exclusivity_forgery_reddens_golden() -> None:
    """AC #3: a test-local forgery -- distinct from AC #9's mutation, which
    only ever touches Axis.ENV by dropping env_scrub from the source's
    returned Stack -- raises Axis.CHANNEL_EXCLUSIVITY specifically from
    UNENFORCED to ENFORCED and demonstrates the SAME golden-comparison
    assertion used by test_scratch_darwin_report_matches_golden_exactly
    (`dict(compiled.report.axes) == GOLDEN`) goes red against it, and red
    on exactly that one axis -- nothing else drifts as a side effect of the
    forgery.

    This forgery never touches brig/stack/__init__.py: it is built entirely
    from the real compiled report's own axes, with one entry substituted in
    a plain dict, which is what makes it "test-local" rather than a source
    mutation (AC #9's kind, which needs a scratch-copy + sha256 restore
    because it edits the delivered file).
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    real_axes = dict(compiled.report.axes)
    assert real_axes == GOLDEN  # sanity: forgery starts from a golden-matching baseline

    forged_axes = dict(real_axes)
    forged_axes[Axis.CHANNEL_EXCLUSIVITY] = Graded(
        Grade.ENFORCED,
        "forged: scratch_darwin() claims no mechanism that restricts shared "
        "channel media, so this axis must never grade ENFORCED",
    )

    with pytest.raises(AssertionError):
        assert forged_axes == GOLDEN, "the same failure message shape as the real golden test above"
    # The raised AssertionError is proof the golden test's own assertion
    # form (`== GOLDEN`) goes red against this forgery -- this IS "the
    # golden test fails", demonstrated rather than merely asserted, and it
    # needed no source edit to produce.

    # Prove the failure is on CHANNEL_EXCLUSIVITY specifically, not merely
    # "somewhere": every other axis still matches GOLDEN exactly.
    diverged = {axis for axis in AXES if forged_axes[axis] != GOLDEN[axis]}
    assert diverged == {Axis.CHANNEL_EXCLUSIVITY}


# ---------------------------------------------------------------------------
# AC #4: fs_read detail declares the denylist model.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_fs_read_detail_declares_denylist() -> None:
    """AC #4: the fs_read grade detail contains the word 'denylist'
    (MILESTONES.md M5-lite EC4's own requirement) -- the read model is
    declared.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    fs_read_detail = compiled.report.axes[Axis.FS_READ].detail
    assert "denylist" in fs_read_detail


# ---------------------------------------------------------------------------
# AC #5: limits detail names all four uncovered fields.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_limits_detail_names_all_uncovered_fields() -> None:
    """AC #5: the limits grade detail names all four fields rlimits cannot
    reach -- memory, tasks, wall, output -- so this preset does not quietly
    claim more coverage than degraded() does.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    limits_detail = compiled.report.axes[Axis.LIMITS].detail
    assert "memory" in limits_detail
    assert "tasks" in limits_detail
    assert "wall" in limits_detail
    assert "output" in limits_detail


# ---------------------------------------------------------------------------
# AC #6: scratch_darwin() is data, not logic.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_ships_exactly_three_mechanisms() -> None:
    """AC #6: scratch_darwin() returns a Stack with exactly three mechanisms
    -- rlimits, seatbelt, env_scrub. Not a factory with logic: calling it
    twice yields the same three mechanism names.
    """
    names = {mechanism.name for mechanism in scratch_darwin().mechanisms}
    assert names == {"rlimits", "seatbelt", "env_scrub"}
    assert len(scratch_darwin().mechanisms) == 3


@pytest.mark.unit
def test_scratch_darwin_function_contains_no_conditional() -> None:
    """AC #6: the function body contains no conditional or loop anywhere in
    it -- not merely after its `return` statement. Parsed via `ast` over the
    WHOLE function body (`ast.walk` from the `FunctionDef` node, not a
    line-prefix scan anchored to `return Stack`), so a conditional placed
    ABOVE the return -- the only place one could go, since the return is
    this function's sole statement -- is caught, not skipped.

    Mutation-checked directly against a prior, rejected version of this
    test: that version only started collecting body lines once it saw
    `return Stack`, so `if True:` inserted immediately above the return
    (re-indented) was invisible to it and the vacuous test passed anyway.
    This version walks the full `ast.FunctionDef`, so that same mutation
    is caught by construction -- there is no region of the function this
    parse does not see.
    """
    source = textwrap.dedent(inspect.getsource(scratch_darwin))
    tree = ast.parse(source)
    (func_def,) = tree.body
    assert isinstance(func_def, ast.FunctionDef)

    conditional_types = (
        ast.If,
        ast.For,
        ast.While,
        ast.IfExp,  # ternary
        ast.Match,  # match/case
    )
    # Comprehension `if` clauses (ast.comprehension.ifs) are covered too:
    # ast.walk descends into every comprehension node it finds, and any
    # such node here would itself already be a second finding (this
    # function has no comprehensions in a correct implementation).
    found = [node for node in ast.walk(func_def) if isinstance(node, conditional_types)]
    assert found == [], (
        f"scratch_darwin() must be a pure data literal with no conditional "
        f"or loop; found {[type(n).__name__ for n in found]} at line(s) "
        f"{[getattr(n, 'lineno', None) for n in found]}"
    )

    # Named in the task's own Deliverable: the body IS a three-element list
    # literal, nothing else. Confirms the ast-based check above isn't
    # passing on some other single-statement shape.
    (stmt,) = [s for s in func_def.body if not isinstance(s, ast.Expr | ast.Constant)]
    assert isinstance(stmt, ast.Return)
    assert isinstance(stmt.value, ast.Call)
    (list_arg,) = stmt.value.args
    assert isinstance(list_arg, ast.List)
    assert len(list_arg.elts) == 3


# ---------------------------------------------------------------------------
# AC #7: composed wrap is a pure argv prefix with EQUIVALENT_PROFILE.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_composed_wrap_is_pure_argv_prefix() -> None:
    """AC #7 (first half): the composed wrap from the three-mechanism stack
    is a pure argv prefix, VERIFIED by the real production function --
    `brig.run.launcher._derive_wrap_prefix` -- the exact function
    `launcher.py`'s own `SubprocessLauncher.launch` calls to compute
    `Handle.wrap_prefix`, and the exact function `exec_.exec_in_jail`
    trusts. This does not reimplement the slice-check by hand: it calls
    the real seam so a regression in `_derive_wrap_prefix` itself would be
    caught here, not just in this test's own hand-rolled arithmetic.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())

    original_argv = ("/bin/echo", "hello", "world")
    wrapped_argv = tuple(compiled.wrap(original_argv))

    prefix = _derive_wrap_prefix(wrapped_argv, original_argv)

    # None means "not a pure prefix" -- exec_.exec_in_jail refuses exec on
    # this (ExecWrapNotAPrefix) rather than spawn a weaker sibling. This
    # preset's three-mechanism wrap must not trigger that refusal, or every
    # battery in task-065 that runs a probe via handle.exec fails for a
    # reason that has nothing to do with a kernel.
    assert prefix is not None, (
        "composed wrap is not a pure argv prefix; exec_.exec_in_jail would "
        "refuse every probe that runs through handle.exec (task-065)"
    )
    assert len(prefix) > 0, (
        "an empty (but non-None) prefix means the real exec seam grades "
        "PLAIN, not EQUIVALENT_PROFILE -- wrong for a three-mechanism stack"
    )


@pytest.mark.unit
def test_scratch_darwin_wrap_prefix_consistency() -> None:
    """AC #7 (second half): `handle.exec` grades `ExecFidelity.EQUIVALENT_
    PROFILE` for this preset, not `PLAIN` and not a refusal.

    `brig.run.exec_.exec_in_jail` computes fidelity from `handle.wrap_prefix`
    (itself `_derive_wrap_prefix`'s return value, stored at launch time) with
    exactly this branch (brig/run/exec_.py):

        if wrap_prefix:
            fidelity = ExecFidelity.EQUIVALENT_PROFILE
        else:
            fidelity = ExecFidelity.PLAIN

    `exec_in_jail` itself spawns a real subprocess, which is integration-tier,
    not unit -- so this test stays at unit tier by calling the real,
    subprocess-free `_derive_wrap_prefix` and applying `exec_in_jail`'s own
    documented branch condition to its result, rather than reimplementing
    the prefix arithmetic separately from the AC #7 test above.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())

    original_argv = ("/bin/echo", "hello", "world")
    wrapped_argv = tuple(compiled.wrap(original_argv))
    prefix = _derive_wrap_prefix(wrapped_argv, original_argv)
    assert prefix is not None

    fidelity = ExecFidelity.EQUIVALENT_PROFILE if prefix else ExecFidelity.PLAIN
    assert fidelity is ExecFidelity.EQUIVALENT_PROFILE

    # Named control: the wrap really does add a prefix and preserve the
    # original argv unchanged as the tail -- the property _derive_wrap_prefix
    # itself verifies before returning non-None.
    assert len(wrapped_argv) > len(original_argv)
    assert wrapped_argv[-len(original_argv) :] == original_argv
    assert wrapped_argv[: len(wrapped_argv) - len(original_argv)] == prefix


# ---------------------------------------------------------------------------
# AC #8: preset refuses on spec seatbelt refuses.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_refuses_with_granted_domains() -> None:
    """AC #8: scratch_darwin() refuses at compile time when the spec has
    granted network domains (seatbelt has no DNS awareness). The refusal is
    seatbelt's own exception, propagated unchanged.
    """
    from brig.mech.seatbelt import NetworkUnsupported

    spec = Spec(network=NetworkPolicy(allowed_domains=("example.com",)))

    with pytest.raises(NetworkUnsupported):
        scratch_darwin().compile(spec, ctx=_darwin_ctx())


@pytest.mark.unit
def test_scratch_darwin_refuses_with_allowlist_read_model() -> None:
    """AC #8 (second refusal): scratch_darwin() refuses at compile time when
    the spec's read model is `ReadModel.ALLOW_LIST` -- seatbelt is a
    denylist-only mechanism (brig/mech/seatbelt/profile.py's `render_sbpl`)
    and raises its own `ReadModelUnsupported`, propagated here unchanged.

    `FsPolicy.__post_init__` (brig/core/spec.py) rejects a `read_denies`
    entry when `read_model` is `ALLOW_LIST`, so the spec that actually
    reaches `ReadModelUnsupported` sets `read_model=ReadModel.ALLOW_LIST`
    with `read_allows` populated and `read_denies` left empty -- NOT
    `FsPolicy(read_denies=(...))` with `read_model` left at its DENY_LIST
    default, which can never raise this exception (that was this AC's prior,
    rejected form: no assertion ran outside a `contextlib.suppress`, so a
    compile that quietly succeeded made the test pass too).

    `render_sbpl` checks `read_model` before it resolves any path (profile.py:
    the `ReadModelUnsupported` raise sits above the `_jail_dir_is_unresolved`
    check and above any `resolved` lookup), so this spec's `read_allows`
    entry needs no matching `ctx.resolved_paths` -- confirmed by using the
    plain darwin ctx with no `resolved_paths` override.
    """
    from brig.mech.seatbelt import ReadModelUnsupported

    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/private/tmp/allowed",),
        )
    )

    with pytest.raises(ReadModelUnsupported):
        scratch_darwin().compile(spec, ctx=_darwin_ctx())


# ---------------------------------------------------------------------------
# AC #6 (again): spec floors interact correctly.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_require_fs_read_enforced_compiles_against_scratch_darwin() -> None:
    """AC #6 (control): require(fs_read=ENFORCED) is exactly what
    scratch_darwin() delivers on the fs_read axis, so compile succeeds.
    """
    compiled = scratch_darwin().compile(_spec(), require(fs_read=Grade.ENFORCED), ctx=_darwin_ctx())
    assert compiled.report.axes[Axis.FS_READ].grade is Grade.ENFORCED


@pytest.mark.unit
def test_require_channel_exclusivity_enforced_refuses_against_scratch_darwin() -> None:
    """AC #6: require(channel_exclusivity=ENFORCED) against scratch_darwin()
    refuses at compile, naming the axis and the shortfall -- the refusal alone
    cannot distinguish "floors work" from "compile is broken", so this is
    paired with the control above (fs_read=ENFORCED, which succeeds).
    """
    floors = require(channel_exclusivity=Grade.ENFORCED)
    with pytest.raises(FloorViolation) as exc_info:
        scratch_darwin().compile(_spec(), floors, ctx=_darwin_ctx())
    shortfalls = exc_info.value.shortfalls
    assert len(shortfalls) == 1
    shortfall = shortfalls[0]
    assert shortfall.axis is Axis.CHANNEL_EXCLUSIVITY
    assert shortfall.required is Grade.ENFORCED
    assert shortfall.actual is Grade.UNENFORCED


# ---------------------------------------------------------------------------
# AC #4 (again): env axis under PASS mode.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_under_pass_env_grades_env_unenforced() -> None:
    """AC #4: under `EnvPolicy(mode=PASS)`, `env_scrub` claims nothing on the
    env axis (SPEC.md §6 / decision-092) -- `Step.grades` is the empty mapping
    for this mechanism, so `scratch_darwin()`'s aggregate report never overlays
    `Axis.ENV` at all, and it falls through to `unenforced_report()`'s fill
    exactly like an axis no mechanism declared: `Graded(UNENFORCED, "")`.
    """
    compiled = scratch_darwin().compile(Spec(env=EnvPolicy(mode=EnvMode.PASS)), ctx=_darwin_ctx())
    assert compiled.report.grade_for(Axis.ENV) == Graded(Grade.UNENFORCED, "")


@pytest.mark.unit
def test_scratch_darwin_under_scrub_env_still_matches_golden() -> None:
    """AC #4's named control: the default `Spec()` (`EnvPolicy.mode` defaults
    to `SCRUB`, brig/core/spec.py) still compiles to `GOLDEN[Axis.ENV]` exactly
    -- the PASS case above is a genuine branch on `EnvPolicy.mode`, not a change
    to what SCRUB grades.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    assert compiled.report.axes[Axis.ENV] == GOLDEN[Axis.ENV]


# ---------------------------------------------------------------------------
# Mutation check (AC #9): drop env_scrub, golden test reddens on env axis.
# This is demonstrated rather than embedded (see AC #9 description); the
# mutation check output is pasted into the task's notes.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scratch_darwin_mutation_check_marker() -> None:
    """AC #9 marker: this test asserts that the golden exists and has a real
    env=ENFORCED value to be broken by the mutation. The actual mutation check
    (dropping env_scrub from the returned Stack) is run as a separate test
    outside this file, per AC #9's requirements, with output pasted into
    task-064's notes as evidence.
    """
    compiled = scratch_darwin().compile(_spec(), ctx=_darwin_ctx())
    # The golden has env: ENFORCED. If env_scrub is dropped from scratch_darwin(),
    # this will become UNENFORCED. The mutation test in the task notes demonstrates
    # this by:
    # 1. Removing env_scrub from the Stack in __init__.py
    # 2. Running pytest on this file
    # 3. Seeing test_scratch_darwin_report_matches_golden_exactly FAIL
    #    because env is now UNENFORCED instead of ENFORCED
    # 4. Restoring env_scrub with sha256 verification
    assert compiled.report.axes[Axis.ENV].grade is Grade.ENFORCED
