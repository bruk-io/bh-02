"""`Stack.compile` assembles a `core.signatures.SignatureBook` alongside the
aggregate report, so `CompiledJail.signatures` (and, through it, a
rehydrated `Handle`) can still answer "which mechanism claims this axis,
and what does its denial look like?" (task-047).

## THE GAP THIS TASK CLOSES

SPEC.md §6:

    **Denial signatures** are part of the contract because probes and event
    classification need to distinguish "denied by policy" from "failed for
    an unrelated reason" (a probe that can't tell is vacuous). Each
    mechanism knows its own

SPEC.md §12:

    the probe engine builds the normalized denial string ... and matches the
    claiming mechanism's `denial_signatures` against *that*.

Before this task, `Step.denial_signatures` was declared by every mechanism
and then dropped: `Stack.compile` never read it, and `CompiledJail` had no
field to carry it onward. Verified at the M4 plan gate: `/usr/bin/grep -rn
'denial_signatures' brig/` hit only `brig/mech/`.

## The key set: `step.grades`, NOT `mechanism.axes` (task-044)

`Stack.compile`'s own comment, immediately above the loop this file tests,
already states the rule the signature book follows: "what [a mechanism]
DOES claim for a given Spec is the key set of its compiled `Step.grades`,
and the two need not be equal" to `axes` (SPEC.md §6 / decision-092, P-12).
`env_scrub` is the concrete case task-044 shipped: under `EnvMode.PASS` it
declares `axes = {Axis.ENV}` but its compiled `Step.grades` is empty (`{}`)
-- so it claims nothing, on either the report OR the signature book, for
that spec. `test_the_book_keys_off_step_grades_not_mechanism_axes` below is
the discriminating test: if the book were built from `mechanism.axes`
instead, it would carry an `env_scrub` claim under PASS that the mechanism
itself never made.

## The empty-tuple routing fact (decision-067)

`env_scrub` declares `denial_signatures=()` unconditionally (see
`brig/mech/env_scrub.py`'s own docstring) -- under `SCRUB` it still claims
`Axis.ENV` on the report, but with nothing to match by signature. That is
carried through as a PRESENT claim with an EMPTY signatures tuple, not
absorbed into "no claim at all": the two are different facts a later probe
(task-050) routes on differently -- "prove this axis via `ABSENCE` plus a
`CONTROL`" vs. "nothing claims this axis, don't probe it as if something
did." `test_env_scrub_claim_is_present_with_an_EMPTY_signature_tuple` and
its named control, `test_an_unclaimed_axis_has_no_claim_at_all`, are the
discriminating pair that proves the two are actually told apart, not both
just quietly `None`/empty in the same way.
"""

from __future__ import annotations

import re

import pytest

from brig.core import Axis, EnvMode, EnvPolicy, Limits, Spec
from brig.stack import degraded

# ---------------------------------------------------------------------------
# AC #1 -- a real, non-empty claim: rlimits under a real cpu limit.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_degraded_book_carries_rlimits_signature_under_its_own_axis() -> None:
    """AC #1. `degraded()` compiled against a spec with a real cpu limit:
    the book's `Axis.LIMITS` claim is owned by `rlimits`, and its
    `signatures` tuple is non-empty with every element a compiled
    `re.Pattern` -- never a bare string (SPEC.md §6: `Step.denial_signatures`
    is regex patterns, and `SignatureBook.to_list`/`from_list` is the only
    place a pattern SOURCE, a plain `str`, is legitimate)."""
    jail = degraded().compile(Spec(limits=Limits(cpu_seconds=1)))

    claim = jail.signatures.for_axis(Axis.LIMITS)
    assert claim is not None
    assert claim.mechanism == "rlimits"
    assert claim.axis is Axis.LIMITS
    assert len(claim.signatures) > 0
    assert all(isinstance(pattern, re.Pattern) for pattern in claim.signatures)


# ---------------------------------------------------------------------------
# AC #2 -- the discriminating pair: a present-but-empty claim vs. no claim.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_env_scrub_claim_is_present_with_an_EMPTY_signature_tuple() -> None:
    """AC #2, THE CLAIM half. `degraded()`'s default `Spec()` has
    `EnvPolicy.mode == EnvMode.SCRUB` (the dataclass default) -- `env_scrub`
    claims `Axis.ENV` on the report under SCRUB (`brig/mech/env_scrub.py`),
    and its `Step.denial_signatures` is `()` unconditionally
    (decision-067). The book must carry that claim through EXACTLY as
    declared: present, `mechanism == 'env_scrub'`, `signatures == ()` --
    not `None` (that would be "unclaimed"), and not a signatures tuple this
    task substituted a generic pattern into (decision-067's own
    prohibition, named in this task's Out of scope)."""
    jail = degraded().compile(Spec())

    claim = jail.signatures.for_axis(Axis.ENV)
    assert claim is not None
    assert claim.mechanism == "env_scrub"
    assert claim.signatures == ()


@pytest.mark.unit
def test_an_unclaimed_axis_has_no_claim_at_all() -> None:
    """AC #2, THE CONTROL, named. Same compile as the test directly above
    (`degraded().compile(Spec())`): neither `env_scrub` nor `rlimits`
    claims `Axis.NETWORK` (`connect_proxy` is M6, decision-062), so the
    book has NO claim for it at all -- `for_axis` returns `None`, not an
    `AxisClaim` with empty fields. Run alongside the test above, this is
    what proves "claimed with no signatures" (ENV) and "not claimed"
    (NETWORK) are genuinely distinguished by the book, rather than both
    collapsing to the same empty-looking shape."""
    jail = degraded().compile(Spec())

    assert jail.signatures.for_axis(Axis.NETWORK) is None


# ---------------------------------------------------------------------------
# AC #3 -- the book keys off step.grades, not mechanism.axes (task-044).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_book_keys_off_step_grades_not_mechanism_axes() -> None:
    """AC #3, THE CLAIM half. `degraded()` compiled against
    `Spec(env=EnvPolicy(mode=EnvMode.PASS))`: task-044 makes `env_scrub`
    grade NOTHING under PASS (`Step.grades == {}`), even though
    `EnvScrub.axes == frozenset({Axis.ENV})` still declares the axis
    statically. A book built from `mechanism.axes` would carry an
    `env_scrub` claim here regardless; a book built from `step.grades` (the
    rule this module's docstring quotes) does not. `for_axis(Axis.ENV)` is
    `None`."""
    jail = degraded().compile(Spec(env=EnvPolicy(mode=EnvMode.PASS)))

    assert jail.signatures.for_axis(Axis.ENV) is None


@pytest.mark.unit
def test_the_book_keys_off_step_grades_not_mechanism_axes_control_under_scrub() -> None:
    """AC #3, THE CONTROL. The SAME stack, the SAME axis, the only
    difference being `EnvMode.SCRUB` instead of `PASS`: now `env_scrub`
    DOES grade `Axis.ENV` (`Step.grades == {Axis.ENV: ...}`), and the book
    carries a claim for it. Without this control, "PASS has no ENV claim"
    could mean either "the book correctly keys off `step.grades`" or "the
    book never carries an `env_scrub` claim under any spec" -- indistinguishable
    from the PASS case alone."""
    jail = degraded().compile(Spec(env=EnvPolicy(mode=EnvMode.SCRUB)))

    claim = jail.signatures.for_axis(Axis.ENV)
    assert claim is not None
    assert claim.mechanism == "env_scrub"
