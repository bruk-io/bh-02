"""Tests for brig.probe.batteries.env and brig.probe.batteries.limits:
task-053's unit tier (AC #5, #6).

`env_battery`'s two probes:
- allowed_name_survives (CONTROL)
- scrubbed_name_is_absent (ABSENCE)

`limits_battery`'s two probes:
- short_command_completes (CONTROL)
- cpu_spin_is_killed (DENIAL)
"""

from __future__ import annotations

import pytest

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.core.spec import EnvMode, EnvPolicy, Limits, Spec
from brig.probe.batteries.env import CANARY_ENV_NAME, env_battery
from brig.probe.batteries.limits import limits_battery


@pytest.mark.unit
def test_env_battery_refuses_under_pass_mode() -> None:
    """AC #5, env half: `env_battery` refuses a PASS-mode spec with a
    `ValueError` naming the mode -- PASS confers everything, so there is
    nothing to prove and no allow-name to control on. Control, in the same
    test: the identical shape of Spec but SCRUB-mode, with a non-empty
    allow-list, constructs without raising."""
    with pytest.raises(ValueError, match="mode"):
        env_battery(Spec(env=EnvPolicy(mode=EnvMode.PASS)))

    # Control: the SCRUB spec constructs.
    battery = env_battery(Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",))))
    assert battery.axis is Axis.ENV


@pytest.mark.unit
def test_limits_battery_refuses_an_uncapped_cpu() -> None:
    """AC #5, limits half: `limits_battery` refuses `cpu_seconds=0`
    (SPEC.md §5: "0 = uncapped") with a `ValueError` naming `cpu_seconds`.
    Control, in the same test: `cpu_seconds=1` constructs."""
    with pytest.raises(ValueError, match="cpu_seconds"):
        limits_battery(Spec(limits=Limits(cpu_seconds=0)))

    # Control: cpu_seconds=1 constructs.
    battery = limits_battery(Spec(limits=Limits(cpu_seconds=1)))
    assert battery.axis is Axis.LIMITS


@pytest.mark.unit
def test_env_battery_refuses_empty_allow_names_under_scrub() -> None:
    """A guard the task's Deliverable table implies but does not spell a
    dedicated AC for: SCRUB with an empty allow-list has no name to build
    the required CONTROL probe from, same "nothing to control on" shape as
    the PASS-mode refusal above -- but a DIFFERENT field is named."""
    with pytest.raises(ValueError, match="allow_names"):
        env_battery(Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=())))


@pytest.mark.unit
def test_every_probe_name_and_shape_matches_the_table() -> None:
    """AC #6: both batteries' (name, shape) pairs, in order, match the two
    tables quoted in task-053's Deliverable, literally."""
    env = env_battery(Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",))))
    expected_env = [
        ("allowed_name_survives", ProbeShape.CONTROL),
        ("scrubbed_name_is_absent", ProbeShape.ABSENCE),
    ]
    assert [(p.name, p.shape) for p in env.probes] == expected_env

    limits = limits_battery(Spec(limits=Limits(cpu_seconds=1)))
    expected_limits = [
        ("short_command_completes", ProbeShape.CONTROL),
        ("cpu_spin_is_killed", ProbeShape.DENIAL),
    ]
    assert [(p.name, p.shape) for p in limits.probes] == expected_limits


@pytest.mark.unit
def test_env_battery_argv_is_bare_usr_bin_env() -> None:
    """Both env probes' argv is exactly `("/usr/bin/env",)`, per the
    Deliverable table -- no extra flags, no shell wrapping."""
    battery = env_battery(Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",))))
    for probe in battery.probes:
        assert probe.argv == ("/usr/bin/env",)


@pytest.mark.unit
def test_env_battery_control_uses_the_first_sorted_allow_name() -> None:
    """`allowed_name_survives`'s expected token is `<first allow_name>=`
    -- `EnvPolicy.__post_init__` sorts `allow_names`, so "first" is the
    alphabetically-first name, not insertion order."""
    battery = env_battery(Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("ZEBRA", "ALPHA"))))
    control = next(p for p in battery.probes if p.shape is ProbeShape.CONTROL)
    assert control.expect.token == "ALPHA="


@pytest.mark.unit
def test_env_battery_absence_token_is_the_shared_canary_constant() -> None:
    """`scrubbed_name_is_absent`'s expected token is built from the
    module's own exported `CANARY_ENV_NAME` -- the constant a caller must
    import and set in the launching environment (this module's docstring)
    -- not an independently-typed literal that could drift from it."""
    battery = env_battery(Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",))))
    absence = next(p for p in battery.probes if p.shape is ProbeShape.ABSENCE)
    assert absence.expect.token == f"{CANARY_ENV_NAME}="


@pytest.mark.unit
def test_limits_battery_argv_matches_the_table() -> None:
    """Both limits probes' argv matches the Deliverable table exactly."""
    battery = limits_battery(Spec(limits=Limits(cpu_seconds=1)))
    probes_by_name = {p.name: p for p in battery.probes}
    assert probes_by_name["short_command_completes"].argv == (
        "/bin/sh",
        "-c",
        "printf brig-ok",
    )
    assert probes_by_name["cpu_spin_is_killed"].argv == (
        "/bin/sh",
        "-c",
        "while :; do :; done",
    )
