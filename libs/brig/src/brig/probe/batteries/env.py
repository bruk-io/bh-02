"""`env_battery`: a probe battery for the env axis (SPEC.md §6, §12).

**This battery is `ABSENCE`-shaped on its scrub probe, never `DENIAL`
(this task's own "spec anchor", quoting SPEC.md §12 verbatim):**

    A mechanism declaring the empty tuple has no way to reach `PASS` by
    signature at all, which is correct: its axis is proved by the
    battery's positive controls, and every probe against it that merely
    fails is `VACUOUS`.

`env_scrub` (SPEC.md §6) declares the empty denial-signature tuple on
purpose -- scrubbing produces ABSENCE, not denial (a program that fails
because a variable it wanted is simply not there emits generic text no
signature may honestly match, `brig/mech/env_scrub.py`'s own docstring).
So this battery's scrub probe is `ProbeShape.ABSENCE`: it performs a
*permitted* observation (`/usr/bin/env`, no args -- listing the child's
own environment is never denied) and asserts a policy-derived absence in
its stdout, exactly the shape `brig/probe/verdict.py`'s `_classify_absence`
exists for. Routing it through `DENIAL` instead would read the empty
signature tuple as a gap to fill and manufacture a false `PASS` the first
time the probe merely failed to run -- the exact defect `doc-013` §10 ask 3
names.

**The canary.** `env_battery(spec) -> Battery`'s only parameter is `spec`
-- it does not invent a canary env-var name, and it does not read the
process environment (this module stays pure, like every other module in
`brig.probe.batteries`). Instead it exports `CANARY_ENV_NAME`, a single
well-known name both this module and a caller import: the caller (an
integration test, or any embedder wiring this battery up) is responsible
for setting an environment variable with this EXACT name, to any value, in
the process that will LAUNCH the jail, before compiling/launching it --
`brig/run/launcher.py`'s `full_env = {**os.environ, **jail.env}` is what
carries it in. `scrubbed_name_is_absent`'s `Expectation.token` is built
from this same constant, so the probe and the caller's setup are pinned to
one name, not two independently-typed strings that could drift.

This module is pure: no I/O, no clock, no randomness, and it spawns
nothing of its own -- it only returns data describing argv for a caller to
run.
"""

from __future__ import annotations

from typing import Final

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.core.spec import EnvMode, Spec
from brig.probe.battery import Battery, Expectation, Probe

#: `/usr/bin/env` with no argv lists the CALLING process's own visible
#: environment, one `NAME=value` line per variable -- the exact observation
#: both this battery's probes read. `env_scrub`'s own render (`_ENV_UTILITY`
#: in `brig/mech/env_scrub.py`) targets the identical absolute path, so a
#: probe that reaches this argv exercises the same binary the mechanism
#: itself wraps -- no PATH-relative `env` lookup either can silently diverge
#: on.
_ENV_UTILITY = "/usr/bin/env"

#: The well-known canary env-var NAME both this module and a caller share
#: (see this module's docstring). Deliberately not a real credential-shaped
#: name. The battery never reads its VALUE -- only whether a line starting
#: with `"{CANARY_ENV_NAME}="` appears in `/usr/bin/env`'s stdout.
CANARY_ENV_NAME: Final[str] = "BRIG_PROBE_CANARY"


def env_battery(spec: Spec) -> Battery:
    """A battery for the env axis.

    Probes:
    - allowed_name_survives (CONTROL): must succeed -- the FIRST (sorted;
      `EnvPolicy.__post_init__` normalizes `allow_names`) allow-listed name
      must appear in `/usr/bin/env`'s stdout.
    - scrubbed_name_is_absent (ABSENCE): `CANARY_ENV_NAME` must NOT appear
      in `/usr/bin/env`'s stdout -- proof of observed absence, never a
      signature match (see this module's docstring).

    Args:
        spec: A Spec whose `env.mode` is `EnvMode.SCRUB` with a non-empty
            `allow_names`. Raises ValueError, naming the mode, when
            `spec.env.mode` is `EnvMode.PASS` -- PASS confers everything,
            so there is nothing to prove and no allow-name to build the
            required CONTROL probe from. Raises ValueError, naming
            `allow_names`, when `spec.env.allow_names` is empty under
            SCRUB -- the same "no control to build" refusal, one field
            over.

    Returns:
        A Battery on Axis.ENV with two probes.
    """
    policy = spec.env

    if policy.mode is EnvMode.PASS:
        raise ValueError(
            "env_battery (axis env): EnvPolicy.mode is EnvMode.PASS, nothing to "
            "prove -- PASS forwards the parent environment untouched, so there is "
            "no allow-name to build the required CONTROL probe from"
        )

    if not policy.allow_names:
        raise ValueError(
            "env_battery (axis env): EnvPolicy.allow_names is empty under "
            "EnvMode.SCRUB, no allowed name for the required CONTROL probe"
        )

    allow_name = policy.allow_names[0]

    probes = (
        Probe(
            name="allowed_name_survives",
            shape=ProbeShape.CONTROL,
            axis=Axis.ENV,
            argv=(_ENV_UTILITY,),
            expect=Expectation(token=f"{allow_name}="),
        ),
        Probe(
            name="scrubbed_name_is_absent",
            shape=ProbeShape.ABSENCE,
            axis=Axis.ENV,
            argv=(_ENV_UTILITY,),
            expect=Expectation(token=f"{CANARY_ENV_NAME}="),
        ),
    )

    return Battery(name="env", axis=Axis.ENV, probes=probes)


__all__ = ("CANARY_ENV_NAME", "env_battery")
