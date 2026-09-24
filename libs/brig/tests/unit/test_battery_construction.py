"""Tests for brig.probe.battery: Probe, Expectation, Battery.

SPEC.md §12 ("Every battery includes positive controls ... so a broken probe
mechanism cannot impersonate a perfect jail"), SPEC.md §2 law 10 ("prove
gates by planting violations"), doc-013 §10 ask 1 / decision-097 (a battery
whose control is missing should not construct -- structural, not a
convention an orchestrator enforces).
"""

from dataclasses import replace

import pytest

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.probe.battery import Battery, Expectation, Probe

_DENIAL_PROBE = Probe(
    name="write_outside_workspace",
    shape=ProbeShape.DENIAL,
    axis=Axis.FS_WRITE,
    argv=("touch", "/etc/should-not-write"),
    expect=Expectation(),
)

_CONTROL_PROBE = Probe(
    name="write_inside_workspace",
    shape=ProbeShape.CONTROL,
    axis=Axis.FS_WRITE,
    argv=("touch", "workspace/ok"),
    expect=Expectation(token="ok"),
)


@pytest.mark.unit
def test_a_battery_without_a_control_does_not_construct() -> None:
    """ask 1, made structural (decision-097): a battery whose probes are all
    DENIAL-shaped -- no CONTROL among them -- refuses to construct. The
    battery's name is deliberately disjoint from its axis's token
    ("workspace_writes" vs. "fs_write") so the two assertions below cannot
    be satisfied by one substring doing double duty."""
    with pytest.raises(ValueError, match="workspace_writes") as exc_info:
        Battery(name="workspace_writes", axis=Axis.FS_WRITE, probes=(_DENIAL_PROBE,))
    assert "fs_write" in str(exc_info.value)


@pytest.mark.unit
def test_the_same_battery_with_a_control_constructs() -> None:
    """Control for the test above: the identical probe tuple plus one
    CONTROL-shaped probe constructs cleanly -- the discriminating pair,
    proving the refusal above is about the missing control and nothing
    else about the battery."""
    battery = Battery(
        name="workspace_writes",
        axis=Axis.FS_WRITE,
        probes=(_DENIAL_PROBE, _CONTROL_PROBE),
    )
    assert battery.name == "workspace_writes"
    assert len(battery.probes) == 2


@pytest.mark.unit
def test_empty_probes_refuses() -> None:
    """An empty `probes` tuple refuses to construct; the corrected input --
    a single CONTROL-shaped probe on the same axis -- constructs, in the
    same test. The match is the distinguishing phrase "must not be empty",
    not the bare word "empty" -- the battery's own name ("no_probes_at_all")
    is deliberately free of that word, and every other refusal in this
    module ("no positive control", "duplicate probe name", "claims axis")
    does not contain the phrase either, so this match cannot be satisfied
    by a different refusal firing instead."""
    with pytest.raises(ValueError, match="must not be empty"):
        Battery(name="no_probes_at_all", axis=Axis.NETWORK, probes=())

    control_probe = replace(_CONTROL_PROBE, axis=Axis.NETWORK)
    battery = Battery(name="no_probes_at_all", axis=Axis.NETWORK, probes=(control_probe,))
    assert len(battery.probes) == 1


@pytest.mark.unit
def test_duplicate_probe_name_refuses() -> None:
    """Two probes sharing a `name` refuse to construct; the corrected input
    -- distinct names -- constructs, in the same test. The shared name
    ("write_twice") is deliberately not a substring of the word
    "duplicate", so the match cannot be satisfied by the refusal's own
    prose alone."""
    denial = replace(_DENIAL_PROBE, name="write_twice")
    control = replace(_CONTROL_PROBE, name="write_twice")
    with pytest.raises(ValueError, match="write_twice"):
        Battery(name="dup_battery", axis=Axis.FS_WRITE, probes=(denial, control))

    battery = Battery(
        name="dup_battery",
        axis=Axis.FS_WRITE,
        probes=(_DENIAL_PROBE, _CONTROL_PROBE),
    )
    assert len(battery.probes) == 2


@pytest.mark.unit
def test_probe_on_a_foreign_axis_refuses() -> None:
    """A probe whose `axis` differs from the battery's own `axis` refuses
    to construct; the corrected input -- a matching axis -- constructs, in
    the same test."""
    foreign = replace(_DENIAL_PROBE, axis=Axis.NETWORK)
    with pytest.raises(ValueError, match="network"):
        Battery(
            name="workspace_writes",
            axis=Axis.FS_WRITE,
            probes=(foreign, _CONTROL_PROBE),
        )

    battery = Battery(
        name="workspace_writes",
        axis=Axis.FS_WRITE,
        probes=(_DENIAL_PROBE, _CONTROL_PROBE),
    )
    assert len(battery.probes) == 2
