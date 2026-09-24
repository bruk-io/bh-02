"""Test the brig.core public surface: exports, sorting, and availability."""

import pytest

import brig.core


@pytest.mark.unit
def test_exact_public_surface_set() -> None:
    """AC #1: __all__ contains exactly the literal set of names specified.

    A missing or invented export is red.
    """
    expected = {
        "AXES",
        "Axis",
        "AxisClaim",
        "BARE_REPO_TOPLEVEL",
        "BEST_EFFORT",
        "Battery",
        "COOPERATIVE",
        "CREDENTIAL_READ_DENIES_HOME_RELATIVE",
        "Channel",
        "ChannelKind",
        "DataValue",
        "ENFORCED",
        "EVENT_VERSION",
        "EnforcementReport",
        "EnvMode",
        "EnvPolicy",
        "Event",
        "EventKind",
        "FloorViolation",
        "Floors",
        "FsPolicy",
        "GRADES_ORDERED",
        "Grade",
        "Graded",
        "IncomparableSpecs",
        "Limits",
        "NetworkPolicy",
        "ProbeOutcome",
        "ProbeReport",
        "ProbeShape",
        "Provisioning",
        "ReadModel",
        "SELF_MODIFY_WORKSPACE_RELATIVE",
        "SPEC_VERSION",
        "Shortfall",
        "SignatureBook",
        "Spec",
        "UNENFORCED",
        "UnsupportedSpecVersion",
        "Verdict",
        "denial_subject",
        "require",
        "unenforced_report",
    }
    actual = set(brig.core.__all__)
    assert actual == expected, (
        f"Public surface mismatch. Missing: {expected - actual}. Extra: {actual - expected}."
    )


@pytest.mark.unit
def test_all_names_resolve_via_getattr() -> None:
    """AC #2: Every name in __all__ resolves via getattr(brig.core, name)."""
    for name in brig.core.__all__:
        obj = getattr(brig.core, name, None)
        assert obj is not None, (
            f"Name {name!r} in __all__ does not resolve via getattr(brig.core, {name!r})"
        )


@pytest.mark.unit
def test_all_is_sorted() -> None:
    """AC #2: __all__ is sorted (no duplicates, in sorted order)."""
    actual_list = list(brig.core.__all__)
    expected_list = sorted(brig.core.__all__)
    assert actual_list == expected_list, f"__all__ is not sorted. Got: {actual_list}"


@pytest.mark.unit
def test_all_has_no_duplicates() -> None:
    """AC #2: __all__ has no duplicate entries."""
    all_list = list(brig.core.__all__)
    all_set = set(brig.core.__all__)
    assert len(all_list) == len(all_set), (
        f"__all__ has duplicates: {len(all_list)} items but {len(all_set)} unique"
    )
