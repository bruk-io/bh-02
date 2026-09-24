"""Subset algebra: `Spec.is_subset_of` and `Spec.narrowed_to`.

SPEC.md section 5's algebra sentence: write allows shrink, write/read denies
grow, domains shrink, limits tighten pointwise, env allow-names shrink,
channels shrink. Six clauses, exactly -- see task-006's Deliverable for the
clause-to-test mapping the mutation check in AC #10 exercises.
"""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from brig.core.spec import (
    Channel,
    ChannelKind,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    IncomparableSpecs,
    Limits,
    NetworkPolicy,
    ReadModel,
    Spec,
)
from tests.unit.strategies import env_names, spec_and_narrowed, spec_and_widened, specs

# ---------------------------------------------------------------------------
# AC #3: reflexivity.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@given(s=specs())
def test_ec1_reflexive(s: Spec) -> None:
    assert s.is_subset_of(s)


# ---------------------------------------------------------------------------
# AC #4 (amended, decision-017): antisymmetry up to the algebra's two
# declared exclusions. `a.is_subset_of(b) and b.is_subset_of(a)` must imply
# that `a` and `b` agree on every field the six-clause conjunction compares
# -- checked by substituting exactly the two SPEC.md section 5 fields the
# algebra is blind to (`provisioning`, `env.set`) onto `a` and asserting
# plain equality against `b`. Substituting a third field would silently
# widen the law past what SPEC.md section 5 and decision-002 exclude.
#
# Non-vacuity: a property whose premise (`a.is_subset_of(b) and
# b.is_subset_of(a)`) is never satisfied by the strategy would pass on an
# empty branch. `stats` counts how many times the inner function ran
# (hypothesis's generate + reuse/shrink phases, not distinct draws) and how
# many of those invocations reached the mutual-subset branch; the test
# fails if that second count is zero. doc-003's read-only probe measured 75
# of 2137 pairs over 1500 draws with no counterexample -- a reference
# point, not a threshold.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ec1_antisymmetric() -> None:
    """task-057 (decision-105): evaluated as a cut candidate and left
    UNCHANGED -- a deliberate no-reduction, not an oversight. A standalone
    probe (task notes) over 1000 invocations found the mutual-subset branch
    this test's own non-vacuity assertion requires hit on only 50/1000 = 5%
    (two fully-independent `specs()` draws rarely agree on every clause).
    At that rate P(zero hits in N examples) only drops below ~0.1% around
    N=135 -- ABOVE the implicit default of 100 this test already runs at, so
    cutting its example count would raise, not lower, this specific test's
    own flake risk. The tier-wide budget (AC #2 in the task) is already met
    by the other reductions in this file and test_strategies.py without
    touching this one, so it is left at its original sample count rather
    than traded for a smaller, real reliability risk."""
    stats = {"invocations": 0, "mutual_subset": 0}

    @given(data=st.data())
    def check(data: st.DataObject) -> None:
        a = data.draw(specs())
        b = data.draw(specs())
        stats["invocations"] += 1
        if a.is_subset_of(b) and b.is_subset_of(a):
            stats["mutual_subset"] += 1
            normalized_a = dataclasses.replace(
                a,
                provisioning=b.provisioning,
                env=dataclasses.replace(a.env, set=b.env.set),
            )
            assert normalized_a == b

    check()

    print(
        f"antisymmetry non-vacuity: {stats['mutual_subset']} of "
        f"{stats['invocations']} inner-function invocations entered the "
        "mutual-subset branch"
    )
    assert stats["mutual_subset"] > 0, (
        f"non-vacuity failed: 0 of {stats['invocations']} invocations entered "
        "the mutual-subset branch -- the property proved nothing"
    )


# ---------------------------------------------------------------------------
# AC #5: every axis participates -- widening exactly one dimension breaks
# is_subset_of.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_write_allows(data: st.DataObject) -> None:
    spec, widened = data.draw(spec_and_widened(dimension="write_allows"))
    assert not widened.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_denies(data: st.DataObject) -> None:
    spec, widened = data.draw(spec_and_widened(dimension="denies"))
    assert not widened.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_domains(data: st.DataObject) -> None:
    spec, widened = data.draw(spec_and_widened(dimension="domains"))
    assert not widened.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_limits(data: st.DataObject) -> None:
    spec, widened = data.draw(spec_and_widened(dimension="limits"))
    assert not widened.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_env(data: st.DataObject) -> None:
    spec, widened = data.draw(spec_and_widened(dimension="env"))
    assert not widened.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_channels(data: st.DataObject) -> None:
    spec, widened = data.draw(spec_and_widened(dimension="channels"))
    assert not widened.is_subset_of(spec)


# ---------------------------------------------------------------------------
# AC #6: control for the six axis tests -- narrowing (instead of widening)
# the same dimension must still be a subset. Proves a broken `widen`
# generator that accidentally does nothing (or narrows) cannot impersonate
# a working clause.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_write_allows_control_narrowed_is_subset(data: st.DataObject) -> None:
    spec, narrowed = data.draw(spec_and_narrowed(dimension="write_allows"))
    assert narrowed.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_denies_control_narrowed_is_subset(data: st.DataObject) -> None:
    spec, narrowed = data.draw(spec_and_narrowed(dimension="denies"))
    assert narrowed.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_domains_control_narrowed_is_subset(data: st.DataObject) -> None:
    spec, narrowed = data.draw(spec_and_narrowed(dimension="domains"))
    assert narrowed.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_limits_control_narrowed_is_subset(data: st.DataObject) -> None:
    spec, narrowed = data.draw(spec_and_narrowed(dimension="limits"))
    assert narrowed.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_env_control_narrowed_is_subset(data: st.DataObject) -> None:
    spec, narrowed = data.draw(spec_and_narrowed(dimension="env"))
    assert narrowed.is_subset_of(spec)


@pytest.mark.unit
@given(data=st.data())
def test_ec1_axis_channels_control_narrowed_is_subset(data: st.DataObject) -> None:
    spec, narrowed = data.draw(spec_and_narrowed(dimension="channels"))
    assert narrowed.is_subset_of(spec)


# ---------------------------------------------------------------------------
# AC #7: the limits truth table, pinned as explicit parametrized examples.
# 0 = uncapped. parent tightens onto child iff parent == 0 or child <= parent
# (and child != 0 when parent != 0).
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("parent", "child", "expected"),
    [
        (0, 0, True),
        (0, 5, True),
        (5, 0, False),
        (5, 3, True),
        (5, 5, True),
        (5, 7, False),
    ],
)
def test_limits_truth_table(parent: int, child: int, expected: bool) -> None:
    parent_spec = Spec(limits=Limits(wall_seconds=parent))
    child_spec = Spec(limits=Limits(wall_seconds=child))
    assert child_spec.is_subset_of(parent_spec) is expected


# ---------------------------------------------------------------------------
# AC #8: read models are incomparable -- differing ONLY in read_model is
# False in both directions.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_read_models_are_incomparable_both_directions() -> None:
    deny = Spec(fs=FsPolicy(read_model=ReadModel.DENY_LIST))
    allow = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST))
    assert not deny.is_subset_of(allow)
    assert not allow.is_subset_of(deny)


# ---------------------------------------------------------------------------
# AC #9: provisioning is excluded from the comparison entirely.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_provisioning_only_difference_is_mutual_subset() -> None:
    a = Spec(provisioning=dataclasses.replace(Spec().provisioning, closures=("/nix/store/a",)))
    b = Spec(provisioning=dataclasses.replace(Spec().provisioning, closures=("/nix/store/b",)))
    assert a.is_subset_of(b)
    assert b.is_subset_of(a)
    assert a != b


# ---------------------------------------------------------------------------
# AC #13: narrowed_to is the pointwise meet.
# ---------------------------------------------------------------------------


def _channels_incompatible(a: Spec, b: Spec) -> bool:
    a_by_name = {c.name: c for c in a.channels}
    b_by_name = {c.name: c for c in b.channels}
    for name, ca in a_by_name.items():
        cb = b_by_name.get(name)
        # Endpoint only: `LISTEN` is the only `ChannelKind` there is
        # (decision-153), matching `Spec.narrowed_to`'s own check.
        if cb is not None and ca.endpoint != cb.endpoint:
            return True
    return False


@pytest.mark.unit
@settings(max_examples=25)
@given(data=st.data())
def test_ec1_narrowed_to_is_subset_of_both(data: st.DataObject) -> None:
    """task-057 (decision-105): max_examples cut 100 (implicit default) ->
    25. This property carries no internal non-vacuity assertion (it is a
    plain universal claim over every drawn, comparable pair), so a lower
    example count cannot turn it flaky -- it only samples less of the input
    space, exactly the tradeoff decision-105 charters when a named pin
    covers the reduced ground. Pinned below by
    test_ec1_narrowed_to_is_subset_of_both_pinned_example, a concrete pair
    that differs across five of the six axes at once (write_allows, denies,
    domains, limits, env, channels all distinct between the two operands)."""
    s = data.draw(specs())
    t = data.draw(specs())
    assume(s.fs.read_model == t.fs.read_model)
    assume(not _channels_incompatible(s, t))
    meet = s.narrowed_to(t)
    assert meet.is_subset_of(t)
    assert meet.is_subset_of(s)


@pytest.mark.unit
def test_ec1_narrowed_to_is_subset_of_both_pinned_example() -> None:
    """Named pin for the reduction above: s and t differ on write_allows,
    denies, domains, limits, and env at once (same read_model, one shared
    compatibly-bound channel), constructed directly rather than drawn."""
    s = Spec(
        fs=FsPolicy(
            write_allows=("/a", "/b"),
            write_denies=("/x",),
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/r1",),
        ),
        network=NetworkPolicy(allowed_domains=("a.example", "b.example")),
        limits=Limits(wall_seconds=10, cpu_seconds=5),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")),
        channels=(Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="e1"),),
        shared_media=("/m1",),
    )
    t = Spec(
        fs=FsPolicy(
            write_allows=("/b", "/c"),
            write_denies=("/y",),
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/r2",),
        ),
        network=NetworkPolicy(allowed_domains=("b.example", "c.example")),
        limits=Limits(wall_seconds=20, cpu_seconds=0),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("BAR", "BAZ")),
        channels=(
            Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="e1"),
            Channel(name="c2", kind=ChannelKind.LISTEN, endpoint="e2"),
        ),
        shared_media=("/m2",),
    )
    meet = s.narrowed_to(t)
    assert meet.is_subset_of(t)
    assert meet.is_subset_of(s)


# ---------------------------------------------------------------------------
# task-043 AC #4 / decision-080: narrowed_to's meet is GREATEST, not merely
# A lower bound -- AC #3 above (test_ec1_narrowed_to_is_subset_of_both,
# unedited) already proves the meet IS a lower bound. This proves no common
# lower bound reaches further than it does: for any Spec `c` admitted by
# both `a` and `b` (per `is_subset_of`, itself untouched by this task --
# decision-080 scopes the fix to `narrowed_to`'s allow_names expression
# alone), `c` must also be admitted by `a.narrowed_to(b)`.
#
# `c`'s non-env fields are copied from `meet = a.narrowed_to(b)` itself:
# every non-env clause is out of this task's scope (decision-080 rules
# mode= and the other five clauses correct and untouched), and AC #3
# already proves `meet` is a lower bound of both operands on EVERY axis --
# so reusing meet's non-env fields for `c` keeps those clauses trivially
# satisfied (each is a comparison against an identical tuple) without this
# task re-deriving what it does not own.
#
# `c.env` is built independently of `narrowed_to` -- from the allow-name
# bound a correct env meet must respect, computed here with plain set
# operations against `_env_shrink`'s own (unchanged, separately tested)
# three-case rule, never by calling `narrowed_to`. This is exactly what
# lets the property redden on the superseded formula: the old
# `meet.env.allow_names` of `()` in the PASS/SCRUB case refuses a `c.env`
# this bound legitimately allows through -- the identical shape of bug
# AC #2's named regression pins as a single example.
# ---------------------------------------------------------------------------


def _env_lower_bound_names(a_env: EnvPolicy, b_env: EnvPolicy) -> frozenset[str] | None:
    """The allow-names any SCRUB `c.env` may carry and still be admitted by
    BOTH `a_env` and `b_env` under `_env_shrink`'s (unchanged) three-case
    rule. `None` means unrestricted: both operands are PASS, the top
    element (SPEC.md section 5), so ANY names are admitted by both."""
    if a_env.mode is EnvMode.SCRUB and b_env.mode is EnvMode.SCRUB:
        return frozenset(a_env.allow_names) & frozenset(b_env.allow_names)
    if a_env.mode is EnvMode.SCRUB:
        return frozenset(a_env.allow_names)
    if b_env.mode is EnvMode.SCRUB:
        return frozenset(b_env.allow_names)
    return None


@pytest.mark.unit
def test_ec1_narrowed_to_is_greatest_lower_bound() -> None:
    """task-057 (decision-105): max_examples cut 100 (implicit default) ->
    50 on the inner `check`. A standalone probe (task notes) over 321
    invocations found the mixed-PASS/SCRUB-nonempty-bound branch this test's
    own non-vacuity assertion requires hit on 52/321 = 16.2% of invocations,
    so P(zero hits in 50 examples) = (1 - 0.162)**50 ~= 1.5e-4 -- safe
    headroom, not a coin flip. Pinned below by
    test_ec1_narrowed_to_is_greatest_lower_bound_pinned_example: a concrete
    a/b/c triple sitting exactly in that branch, built directly."""
    stats = {"invocations": 0, "mixed_nonempty_bound_used": 0}

    @given(data=st.data())
    @settings(max_examples=50)
    def check(data: st.DataObject) -> None:
        a = data.draw(specs())
        b = data.draw(specs())
        assume(a.fs.read_model == b.fs.read_model)
        assume(not _channels_incompatible(a, b))
        stats["invocations"] += 1

        meet = a.narrowed_to(b)

        bound = _env_lower_bound_names(a.env, b.env)
        if bound is None:
            c_names = tuple(data.draw(st.lists(env_names(), max_size=3, unique=True)))
        elif bound:
            c_names = tuple(data.draw(st.sets(st.sampled_from(sorted(bound)))))
        else:
            c_names = ()

        mixed = (a.env.mode is EnvMode.PASS) != (b.env.mode is EnvMode.PASS)
        if mixed and bound and c_names:
            stats["mixed_nonempty_bound_used"] += 1

        c = dataclasses.replace(meet, env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=c_names))

        # The premise: c is a common lower bound of a and b (checked, not
        # assumed -- the construction above guarantees it mathematically;
        # an assertion failure here would mean the construction itself is
        # wrong, not that a rare draw missed the premise).
        assert c.is_subset_of(a)
        assert c.is_subset_of(b)

        # The claim under test: the meet is GREATEST -- no common lower
        # bound reaches further than it does.
        assert c.is_subset_of(meet)

    check()

    print(
        "GREATEST non-vacuity: "
        f"{stats['mixed_nonempty_bound_used']} of {stats['invocations']} "
        "inner-function invocations drew a mixed PASS/SCRUB pair with a "
        "non-empty bound and a non-empty c.allow_names -- the exact branch "
        "the superseded (pre-task-043) formula got wrong"
    )
    assert stats["mixed_nonempty_bound_used"] > 0, (
        f"non-vacuity failed: 0 of {stats['invocations']} invocations exercised "
        "the mixed PASS/SCRUB, non-empty-names branch -- the property proved "
        "nothing about the fixed defect"
    )


@pytest.mark.unit
def test_ec1_narrowed_to_is_greatest_lower_bound_pinned_example() -> None:
    """Named pin for the max_examples reduction on
    test_ec1_narrowed_to_is_greatest_lower_bound: a concrete a/b/c triple
    sitting directly in the mixed-PASS/SCRUB, non-empty-bound branch that
    test's own non-vacuity check names as the one the superseded
    (pre-task-043) formula got wrong -- constructed, not drawn."""
    a = Spec(env=EnvPolicy(mode=EnvMode.PASS))
    b = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")))
    meet = a.narrowed_to(b)
    assert meet.env.allow_names == ("BAR", "FOO")

    c = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO",)))

    # The premise: c is a common lower bound of a and b.
    assert c.is_subset_of(a)
    assert c.is_subset_of(b)

    # The claim: the meet is GREATEST -- c reaches no further than it does.
    assert c.is_subset_of(meet)


@pytest.mark.unit
def test_narrowed_to_raises_incomparable_on_read_model_mismatch() -> None:
    deny = Spec(fs=FsPolicy(read_model=ReadModel.DENY_LIST))
    allow = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST))
    with pytest.raises(IncomparableSpecs):
        deny.narrowed_to(allow)


@pytest.mark.unit
def test_narrowed_to_raises_incomparable_on_conflicting_channel_binding() -> None:
    """One name bound to two different ENDPOINTS. The kind half of this
    refusal went with `MAILBOX` (decision-153): `LISTEN` is the only kind
    there is, so a name cannot be bound to two kinds."""
    a = Spec(channels=(Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="e1"),))
    b = Spec(channels=(Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="e2"),))
    with pytest.raises(IncomparableSpecs):
        a.narrowed_to(b)


@pytest.mark.unit
def test_narrowed_to_carries_env_set_and_provisioning_from_self() -> None:
    self_prov = dataclasses.replace(Spec().provisioning, closures=("/nix/store/self",))
    other_prov = dataclasses.replace(Spec().provisioning, closures=("/nix/store/other",))
    self_spec = Spec(
        env=EnvPolicy(mode=EnvMode.PASS, set=(("A", "1"),)),
        provisioning=self_prov,
    )
    other_spec = Spec(
        env=EnvPolicy(mode=EnvMode.PASS, set=(("B", "2"),)),
        provisioning=other_prov,
    )
    meet = self_spec.narrowed_to(other_spec)
    assert meet.env.set == self_spec.env.set
    assert meet.provisioning == self_spec.provisioning


@pytest.mark.unit
def test_narrowed_to_env_meet_absorbing_case_carries_receiver_set() -> None:
    """task-043 AC #9: the receiver asymmetry (env.set carried from self)
    stands even in the newly-fixed absorbing case -- a PASS receiver with a
    non-empty env.set still carries that set through, on top of absorbing
    the SCRUB operand's allow-names."""
    self_spec = Spec(env=EnvPolicy(mode=EnvMode.PASS, set=(("A", "1"),)))
    other_spec = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")))
    meet = self_spec.narrowed_to(other_spec)
    assert meet.env.mode is EnvMode.SCRUB
    assert meet.env.allow_names == ("BAR", "FOO")
    assert meet.env.set == self_spec.env.set


# ---------------------------------------------------------------------------
# task-033 / decision-064: "A PASS env policy's reach is the top element of
# the comparison." Three cases, exactly -- a PASS parent admits any child; a
# SCRUB parent never admits a PASS child; two SCRUB policies compare by
# allow-name subset (that third case is where the env axis's independent
# ability to break subset-ness, decision-001, now lives).
#
# AC #1: decision-010's own example. A PASS parent with empty allow_names
# must ADMIT a SCRUB child that lists names -- comparing allow_names
# unconditionally (the pre-task `_env_shrink`) refused this strictly
# narrower child. Confirmed False against the pre-task two-line body:
#
#     def _env_shrink(child: Spec, parent: Spec) -> bool:
#         if parent.env.mode is EnvMode.SCRUB and child.env.mode is EnvMode.PASS:
#             return False
#         return set(child.env.allow_names) <= set(parent.env.allow_names)
#
#   >>> parent = Spec(env=EnvPolicy(mode=EnvMode.PASS))
#   >>> child = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO",)))
#   >>> child.is_subset_of(parent)
#   False
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pass_parent_with_empty_allow_names_admits_scrub_child_listing_names() -> None:
    """decision-010's debt, discharged: a PASS parent's reach is the top
    element, so an empty allow_names list beside it narrows nothing -- a
    SCRUB child that lists names is still strictly narrower and must be
    admitted. False on the pre-task tree (see the module comment above)."""
    parent = Spec(env=EnvPolicy(mode=EnvMode.PASS))
    child = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO",)))
    assert child.is_subset_of(parent)


# ---------------------------------------------------------------------------
# AC #2: the converse move (a) preserves -- a SCRUB parent can never confer
# PASS, so a PASS child is never admitted. Silent widening here would mean a
# SCRUB-scrubbed parent's child could demand the whole environment.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scrub_parent_does_not_admit_pass_child() -> None:
    parent = Spec(env=EnvPolicy(mode=EnvMode.SCRUB))
    child = Spec(env=EnvPolicy(mode=EnvMode.PASS))
    assert not child.is_subset_of(parent)


# ---------------------------------------------------------------------------
# AC #3: six-axis independence (decision-001) survives the PASS-is-top
# rewrite -- it now lives in the SCRUB/SCRUB comparison. Deterministic,
# example-based (decision-026 rule 3: no hypothesis test may be the named
# mutation pairing -- test_ec1_axis_env draws EnvMode.PASS on roughly half
# its widen-branch examples, where `child.env.mode is PASS` short-circuits
# _env_shrink's final line before ever reaching it, so it would redden by
# luck, not by the property. It stays live as corroboration only.)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scrub_parent_does_not_admit_scrub_child_with_extra_allow_name() -> None:
    """The named mutation pairing for AC #3: deleting `_env_shrink`'s final
    `return set(child...) <= set(parent...)` line and replacing it with
    `return True` must turn this test red (see notes for the sha256-proven
    plant/revert)."""
    parent = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO",)))
    child = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")))
    assert not child.is_subset_of(parent)


# ---------------------------------------------------------------------------
# AC #5 (decision-064, move (b)): EnvPolicy's inactive field under PASS is
# refused at construction, not silently ignored -- the same refusal-not-
# downgrade posture SPEC.md section 5 already gives FsPolicy's inactive
# read-model field.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_env_policy_pass_with_allow_names_raises_naming_field_and_mode() -> None:
    with pytest.raises(ValueError, match=r"allow_names.*PASS"):
        EnvPolicy(mode=EnvMode.PASS, allow_names=("FOO",))


@pytest.mark.unit
def test_env_policy_scrub_with_allow_names_constructs() -> None:
    """Control for the refusal above: the same allow_names value is legal
    under the mode where it is active."""
    policy = EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO",))
    assert policy.allow_names == ("FOO",)


@pytest.mark.unit
def test_env_policy_pass_with_no_allow_names_constructs() -> None:
    """Control: PASS with allow_names simply absent is legal -- the refusal
    fires on a populated inactive field, not on the mode itself."""
    policy = EnvPolicy(mode=EnvMode.PASS)
    assert policy.allow_names == ()


# ---------------------------------------------------------------------------
# AC #6 (decision-064, move (b)): from_dict re-runs the refusal. A
# serialized Spec carrying PASS plus allow_names is rejected, not partially
# understood -- built through the ordinary EnvPolicy constructor (task-003's
# posture), so it cannot smuggle in what direct construction refuses.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_dict_revalidates_pass_with_allow_names() -> None:
    d = Spec().to_dict()
    d["env"]["mode"] = "pass"
    d["env"]["allow_names"] = ["FOO"]
    with pytest.raises(ValueError, match=r"allow_names.*PASS"):
        Spec.from_dict(d)


# ---------------------------------------------------------------------------
# AC #7 (task-033) / task-043, decision-080: narrowed_to's env meet,
# exercised as example-based tests on all four EnvMode pairs. mode= is
# SCRUB if either operand is; env.set and provisioning are carried from the
# receiver; allow_names is the three-case rule SPEC.md section 5 states --
# PASS is the identity, SCRUB absorbs PASS carrying its names unchanged,
# SCRUB/SCRUB intersects. The PASS/SCRUB and SCRUB/PASS cases below were
# task-033's deferred residual (decision-064's PASS-is-top contradiction,
# named but not resolved there); decision-080 resolved it and task-043
# fixed the code, retiring task-033 AC #7's `allow_names == ()` record for
# those two cases (decision-041 rule 4). PASS/PASS and SCRUB/SCRUB were
# already correct and are unedited.
# ---------------------------------------------------------------------------


def _assert_env_meet_is_never_pass_with_names(meet_env: EnvPolicy) -> None:
    """Unconditional, not gated behind `if mode is PASS`: three of the four
    mode pairs resolve to SCRUB, so a gated check would never execute its
    body on them and assert nothing (decision-026's vacuous-check failure
    class). The claim is `mode is SCRUB or allow_names == ()` -- always
    evaluated, always meaningful."""
    assert meet_env.mode is EnvMode.SCRUB or meet_env.allow_names == ()


@pytest.mark.unit
def test_narrowed_to_env_meet_pass_pass() -> None:
    a = Spec(env=EnvPolicy(mode=EnvMode.PASS))
    b = Spec(env=EnvPolicy(mode=EnvMode.PASS))
    meet = a.narrowed_to(b)
    assert meet.env.mode is EnvMode.PASS
    assert meet.env.allow_names == ()
    _assert_env_meet_is_never_pass_with_names(meet.env)


@pytest.mark.unit
def test_narrowed_to_env_meet_pass_scrub() -> None:
    """task-043 / decision-080: SCRUB absorbs PASS -- the SCRUB operand's
    allow-names are carried through unchanged, not emptied. Retires
    task-033 AC #7's `allow_names == ()` record (decision-041 rule 4)."""
    a = Spec(env=EnvPolicy(mode=EnvMode.PASS))
    b = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")))
    meet = a.narrowed_to(b)
    assert meet.env.mode is EnvMode.SCRUB
    assert meet.env.allow_names == ("BAR", "FOO")
    _assert_env_meet_is_never_pass_with_names(meet.env)


@pytest.mark.unit
def test_narrowed_to_env_meet_scrub_pass() -> None:
    """task-043 / decision-080: SCRUB absorbs PASS, mirror position -- same
    carried-names claim with the SCRUB operand as the receiver. Retires
    task-033 AC #7's `allow_names == ()` record (decision-041 rule 4)."""
    a = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")))
    b = Spec(env=EnvPolicy(mode=EnvMode.PASS))
    meet = a.narrowed_to(b)
    assert meet.env.mode is EnvMode.SCRUB
    assert meet.env.allow_names == ("BAR", "FOO")
    _assert_env_meet_is_never_pass_with_names(meet.env)


@pytest.mark.unit
def test_narrowed_to_env_meet_scrub_scrub() -> None:
    a = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")))
    b = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("BAR", "BAZ")))
    meet = a.narrowed_to(b)
    assert meet.env.mode is EnvMode.SCRUB
    assert meet.env.allow_names == ("BAR",)
    _assert_env_meet_is_never_pass_with_names(meet.env)


@pytest.mark.unit
def test_narrowed_to_env_meet_named_regression_doc013_decision080() -> None:
    """task-043 AC #2: doc-013's own case, and decision-080's own case, as
    the NAMED regression for the fix -- see task-043 AC #5 for the
    mutation pairing that proves this test actually exercises the
    superseded expression."""
    meet = Spec(env=EnvPolicy(mode=EnvMode.PASS)).narrowed_to(
        Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("FOO", "BAR")))
    )
    assert meet.env.allow_names == ("BAR", "FOO")


# ---------------------------------------------------------------------------
# decision-160 (2026-09-08): an allow entry is a SUBTREE, and both allow axes
# compare and meet that way. The named regression is the gap this closes --
# a child narrowing onto a subtree the parent never spelled out. Each test
# below states one half of the rule; `test_ec1_narrowed_to_is_subset_of_both`
# above (unedited) keeps the meet a lower bound while they do it.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_allows_are_canonicalized_to_an_antichain() -> None:
    """`("/w", "/w/sub")` spells one reach and builds as `("/w",)`. Both
    allow axes; `/wide` is the boundary case that must survive beside `/w`."""
    deny_model = FsPolicy(write_allows=("/w", "/w/sub", "/wide"))
    assert deny_model.write_allows == ("/w", "/wide")

    allow_model = FsPolicy(
        read_model=ReadModel.ALLOW_LIST, read_allows=("/r", "/r/deep/deeper", "/r2")
    )
    assert allow_model.read_allows == ("/r", "/r2")


@pytest.mark.unit
def test_denies_are_not_canonicalized_to_an_antichain() -> None:
    """decision-160 scopes the antichain rule to the two ALLOW axes. Denies
    keep every entry they were given: a deny is not a grant, and pruning one
    is not this decision's to make."""
    fs = FsPolicy(write_denies=("/w", "/w/sub"))
    assert fs.write_denies == ("/w", "/w/sub")


@pytest.mark.unit
def test_a_child_allow_under_a_parent_allow_is_a_subset() -> None:
    """The named regression for decision-160: narrowing to a subtree used to
    require the parent to list that exact subtree."""
    parent = Spec(fs=FsPolicy(write_allows=("/w",)))
    child = Spec(fs=FsPolicy(write_allows=("/w/sub",)))
    assert child.is_subset_of(parent)
    assert not parent.is_subset_of(child)


@pytest.mark.unit
def test_a_sibling_prefix_is_not_a_subset() -> None:
    """The boundary the prefix test must respect: `/w` does not confer
    `/wide`, which merely starts with the same characters."""
    parent = Spec(fs=FsPolicy(write_allows=("/w",)))
    child = Spec(fs=FsPolicy(write_allows=("/wide",)))
    assert not child.is_subset_of(parent)


@pytest.mark.unit
def test_read_allows_compare_by_reach_too() -> None:
    parent = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/r",)))
    child = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/r/sub",)))
    assert child.is_subset_of(parent)
    assert not parent.is_subset_of(child)


@pytest.mark.unit
def test_narrowed_to_meets_allows_as_trees() -> None:
    """The inner entry of each nested pair survives, whichever operand it
    came from; a disjoint pair contributes nothing."""
    a = Spec(fs=FsPolicy(write_allows=("/w", "/other")))
    b = Spec(fs=FsPolicy(write_allows=("/w/sub", "/elsewhere")))
    meet = a.narrowed_to(b)
    assert meet.fs.write_allows == ("/w/sub",)
    assert meet.is_subset_of(a)
    assert meet.is_subset_of(b)


@pytest.mark.unit
def test_narrowed_to_meets_disjoint_allows_to_nothing() -> None:
    meet = Spec(fs=FsPolicy(write_allows=("/a",))).narrowed_to(
        Spec(fs=FsPolicy(write_allows=("/b",)))
    )
    assert meet.fs.write_allows == ()


@pytest.mark.unit
def test_narrowed_to_meets_read_allows_as_trees() -> None:
    a = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/r",)))
    b = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/r/sub", "/gone")))
    meet = a.narrowed_to(b)
    assert meet.fs.read_allows == ("/r/sub",)
    assert meet.is_subset_of(a)
    assert meet.is_subset_of(b)


@pytest.mark.unit
def test_root_allow_confers_every_absolute_path() -> None:
    """'/' is the one normalized path that keeps its trailing separator, so
    the prefix test has to special-case it -- if it did not, '/' would
    confer nothing and the meet with a root-allowing spec would be empty."""
    root = Spec(fs=FsPolicy(write_allows=("/",)))
    child = Spec(fs=FsPolicy(write_allows=("/anywhere",)))
    assert child.is_subset_of(root)
    assert root.narrowed_to(child).fs.write_allows == ("/anywhere",)


@pytest.mark.unit
def test_a_subagent_narrows_onto_a_workspace_subdirectory() -> None:
    """The end-to-end shape decision-160 exists for: a session spec that
    grants the workspace, a subagent asking for one directory inside it, and
    the meet keel's driver runs the child at."""
    session = Spec(fs=FsPolicy(write_allows=("/ws",), write_denies=("/ws/.git",)))
    child = Spec(fs=FsPolicy(write_allows=("/ws/pkg",)))
    meet = session.narrowed_to(child)
    assert meet.fs.write_allows == ("/ws/pkg",)
    assert meet.fs.write_denies == ("/ws/.git",)
    assert meet.is_subset_of(session)
    assert meet.is_subset_of(child)
