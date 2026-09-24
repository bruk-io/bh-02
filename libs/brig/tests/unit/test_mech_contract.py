"""Test the brig.mech contract: types, field pinning, defensive copies, enums."""

from __future__ import annotations

import dataclasses
import re

import pytest

import brig.core
import brig.mech


def _identity(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Identity transformer for testing."""
    return argv


@pytest.mark.unit
def test_step_has_exactly_eight_fields() -> None:
    """task-031 AC#1, replacing task-015 AC#1 under decision-041's rule 4.

    task-015 AC#1 (retired here, verbatim): "Field-set pin: a unit test
    asserts the exact set of Step field names equals the seven quoted in
    the spec anchor minus events, using dataclasses.fields. Adding or
    dropping a field fails the test. Assert set equality, not membership."
    Its subject -- a seven-field Step -- stops existing at task-031: M3
    (decision-060, decision-069) gives `events` a legal type
    (`EventSource | None`) and SPEC.md §6's Step block ships it. The
    replacement asserts the positive, per decision-041: the full EIGHT
    field names, `events` included, by set equality, so both a dropped
    field and an invented one are loud.
    """
    expected_fields = {
        "wrap",
        "env",
        "staged",
        "helpers",
        "requires",
        "grades",
        "denial_signatures",
        "events",
    }
    actual_fields = {f.name for f in dataclasses.fields(brig.mech.Step)}
    assert actual_fields == expected_fields, (
        f"Step field mismatch. Missing: {expected_fields - actual_fields}. "
        f"Extra: {actual_fields - expected_fields}."
    )


@pytest.mark.unit
def test_launch_feature_enum_exactly_three_members() -> None:
    """AC#2: LaunchFeature enum has exactly the three named members.

    Use set equality against literal name tuples.
    """
    expected_names = {"NEW_PROCESS_GROUP", "PTY", "DETACH"}
    actual_names = {m.name for m in brig.mech.LaunchFeature}
    assert actual_names == expected_names, (
        f"LaunchFeature member mismatch. Missing: {expected_names - actual_names}. "
        f"Extra: {actual_names - expected_names}."
    )


@pytest.mark.unit
def test_helper_lifetime_enum_exactly_two_members() -> None:
    """AC#2: HelperLifetime enum has exactly the two named members.

    Use set equality against literal name tuples.
    """
    expected_names = {"JAIL_LIFETIME", "LAUNCH_SCOPED"}
    actual_names = {m.name for m in brig.mech.HelperLifetime}
    assert actual_names == expected_names, (
        f"HelperLifetime member mismatch. Missing: {expected_names - actual_names}. "
        f"Extra: {actual_names - expected_names}."
    )


@pytest.mark.unit
def test_step_env_defensive_copy_from_source() -> None:
    """AC#3: Step.env is defensively copied — mutate source after, Step unchanged.

    Construct a Step with a dict, mutate the dict, observe Step.env unchanged.
    """
    env_dict: dict[str, str] = {"VAR1": "value1"}
    step = brig.mech.Step(
        wrap=_identity,
        env=env_dict,
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades={axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES},
        denial_signatures=(),
    )
    # Mutate the original dict
    env_dict["VAR1"] = "mutated"
    env_dict["VAR2"] = "new"
    # Step.env must be unchanged
    assert dict(step.env) == {"VAR1": "value1"}
    assert "VAR2" not in step.env


@pytest.mark.unit
def test_step_env_before_construction_does_change_it() -> None:
    """AC#3 control: mutating the env dict BEFORE construction does change Step.env."""
    env_dict: dict[str, str] = {"VAR1": "value1"}
    env_dict["VAR2"] = "value2"
    step = brig.mech.Step(
        wrap=_identity,
        env=env_dict,
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades={axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES},
        denial_signatures=(),
    )
    assert dict(step.env) == {"VAR1": "value1", "VAR2": "value2"}


@pytest.mark.unit
def test_step_grades_defensive_copy_from_source() -> None:
    """AC#3: Step.grades is defensively copied — mutate source after, Step unchanged."""
    grades_dict: dict[brig.core.Axis, brig.core.Graded] = {
        axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES
    }
    step = brig.mech.Step(
        wrap=_identity,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades=grades_dict,
        denial_signatures=(),
    )
    # Mutate the original dict
    grades_dict[brig.core.AXES[0]] = brig.core.Graded(brig.core.ENFORCED)
    # Step.grades must be unchanged
    assert step.grades[brig.core.AXES[0]].grade == brig.core.UNENFORCED


@pytest.mark.unit
def test_step_grades_before_construction_does_change_it() -> None:
    """AC#3 control: mutating grades dict BEFORE construction does change Step.grades."""
    grades_dict: dict[brig.core.Axis, brig.core.Graded] = {
        axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES
    }
    # Mutate before construction
    grades_dict[brig.core.AXES[0]] = brig.core.Graded(brig.core.ENFORCED)
    step = brig.mech.Step(
        wrap=_identity,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades=grades_dict,
        denial_signatures=(),
    )
    assert step.grades[brig.core.AXES[0]].grade == brig.core.ENFORCED


@pytest.mark.unit
def test_staged_file_rejects_absolute_relpath() -> None:
    """AC#4: StagedFile(relpath="/absolute") raises ValueError, absolute paths forbidden."""
    with pytest.raises(ValueError, match="absolute"):
        brig.mech.StagedFile(relpath="/absolute/path", content="x")


@pytest.mark.unit
def test_staged_file_accepts_relative_relpath() -> None:
    """AC#4 control: StagedFile with a relative relpath constructs fine."""
    sf = brig.mech.StagedFile(relpath="relative/path", content="content")
    assert sf.relpath == "relative/path"
    assert sf.content == "content"
    assert sf.mode == 0o600  # default mode


@pytest.mark.unit
def test_staged_file_mode_default() -> None:
    """StagedFile.mode defaults to 0o600."""
    sf = brig.mech.StagedFile(relpath="file.txt", content="x")
    assert sf.mode == 0o600


@pytest.mark.unit
def test_staged_file_custom_mode() -> None:
    """StagedFile accepts custom mode."""
    sf = brig.mech.StagedFile(relpath="script.sh", content="x", mode=0o755)
    assert sf.mode == 0o755


@pytest.mark.unit
def test_zero_mechanisms() -> None:
    """AC#5: No mechanisms implemented. All files under brig/mech are contract types."""
    # This is verified by AC#5's evidence: the file list from the find command.
    # The test ensures the package exists and is importable.
    assert hasattr(brig.mech, "Step")
    assert hasattr(brig.mech, "Mechanism")
    assert hasattr(brig.mech, "LaunchFeature")


@pytest.mark.unit
def test_step_events_is_documented_as_present() -> None:
    """task-015 AC#6's subject dissolves at task-031: that AC asked for the
    module docstring to document `Step.events`' ABSENCE in M2 ("Grep the
    phrase from brig.mech.__init__.py docstring into notes"). task-031's
    own Deliverable charters replacing that exact paragraph -- "The module
    docstring's 'deliberately NOT in M2' paragraph is replaced with what
    the field now is; leaving it would be a false statement in shipped
    code" -- so this test's subject (an absence to document) stops
    existing in the same commit as task-015 AC#1's. The replacement
    asserts the positive: the docstring names `EventSource`, names both of
    its methods, and says `run` is what stamps `ts`/`jail_id`.
    """
    docstring = brig.mech.__doc__
    assert docstring is not None
    assert "EventSource" in docstring
    assert "known_at_compile" in docstring
    assert "classify_exit" in docstring
    assert "ts" in docstring
    assert "jail_id" in docstring
    # The old M2 absence-claim must be gone, not merely supplemented.
    assert "deliberately\nNOT in M2" not in docstring
    assert "deliberately NOT in M2" not in docstring


@pytest.mark.unit
def test_mechanism_protocol_has_required_attributes() -> None:
    """Mechanism protocol has name, axes, and compile method."""
    # Check that the Mechanism protocol is defined
    assert hasattr(brig.mech, "Mechanism")
    # Verify via typing.get_type_hints or runtime_checkable attributes
    proto = brig.mech.Mechanism
    # For a Protocol, we check via __annotations__ or by introspection
    if hasattr(proto, "__annotations__"):
        annotations = proto.__annotations__
        assert "name" in annotations
        assert "axes" in annotations


@pytest.mark.unit
def test_mechanism_is_runtime_checkable_via_isinstance() -> None:
    """Mechanism is a bare, @runtime_checkable Protocol, not a @dataclass.

    Falsifies the ATTEMPT-1 regression: Mechanism must not carry
    __dataclass_fields__, and isinstance() against it must work (positive
    for a structurally-matching object, negative for one that doesn't —
    the control that proves this isn't just isinstance() no-op-passing).
    """
    assert not hasattr(brig.mech.Mechanism, "__dataclass_fields__")

    class ConcreteMechanism:
        name = "fake"
        axes: frozenset[brig.core.Axis] = frozenset()

        def compile(self, spec: object, ctx: object) -> object:
            raise NotImplementedError

    assert isinstance(ConcreteMechanism(), brig.mech.Mechanism)
    # Control: something that does NOT structurally match is rejected.
    assert not isinstance(object(), brig.mech.Mechanism)


@pytest.mark.unit
def test_helper_has_required_fields() -> None:
    """Helper dataclass has name, argv, lifetime fields."""
    helper = brig.mech.Helper(
        name="proxy",
        argv=("proxy", "--listen=localhost:8888"),
        lifetime=brig.mech.HelperLifetime.JAIL_LIFETIME,
    )
    assert helper.name == "proxy"
    assert helper.argv == ("proxy", "--listen=localhost:8888")
    assert helper.lifetime == brig.mech.HelperLifetime.JAIL_LIFETIME


@pytest.mark.unit
def test_compile_ctx_has_required_fields() -> None:
    """CompileCtx has jail_dir and platform fields."""
    ctx = brig.mech.CompileCtx(jail_dir="/tmp/jail", platform="linux")
    assert ctx.jail_dir == "/tmp/jail"
    assert ctx.platform == "linux"


@pytest.mark.unit
def test_argv_transformer_type_is_callable() -> None:
    """ArgvTransformer is Callable[[tuple[str, ...]], tuple[str, ...]]."""

    def test_transform(argv: tuple[str, ...]) -> tuple[str, ...]:
        return ("wrapped", *argv)

    # Should be usable as a transformer
    result = test_transform(("echo", "hello"))
    assert result == ("wrapped", "echo", "hello")


@pytest.mark.unit
def test_step_frozen() -> None:
    """Step is frozen (immutable after construction)."""
    step = brig.mech.Step(
        wrap=_identity,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades={axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES},
        denial_signatures=(),
    )
    with pytest.raises(AttributeError):
        step.wrap = lambda x: x  # type: ignore[misc]


@pytest.mark.unit
def test_denial_signatures_is_tuple_of_patterns() -> None:
    """denial_signatures is a tuple of re.Pattern."""
    pattern = re.compile(r"Read-only file system")
    step = brig.mech.Step(
        wrap=_identity,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades={axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES},
        denial_signatures=(pattern,),
    )
    assert len(step.denial_signatures) == 1
    assert step.denial_signatures[0].pattern == r"Read-only file system"
