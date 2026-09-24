"""decision-143 / task-083: `EnvPolicy.set` values transit host argv, and this
DEMONSTRATES it rather than asserting it.

`env_scrub` grades `Axis.ENV` as ENFORCED, scoped to the child. That scope is
real and the grade stands (decision-143): a jailed process cannot recover a
scrubbed value. But a `set` value -- whose entire purpose is injecting
something the embedder chose, which may be a credential -- travels through
`/bin/sh`'s and `/usr/bin/env`'s own argv on its way in, where any process on
this host can read it with `ps`.

**What measuring it changed.** task-083 asked for a test that reads the
value out of `/bin/ps`. That was written first and it does not work: 25
spawns, each raced by a thread polling `ps -axww -o args=` in a tight loop,
caught the value **0 times**. Both `exec`s in
`/bin/sh -c 'exec /usr/bin/env -i <assignments> "$@"' sh <argv...>` collapse
the chain in microseconds, so by the time any `ps` runs only the workload's
own argv is left, and it never carried the value.

The exposure is still real -- the value IS in an argv, and `execve` auditing
or a debugger do not care how brief that is -- but "readable via `ps`"
overstated it, and overstating a gap is its own form of dishonest reporting.
So the exposure is asserted STRUCTURALLY, on the rendered argv, which is
deterministic; the `ps` measurement is recorded here rather than shipped as
a race that would be flaky at best and silently vacuous at worst.

**Both halves, or neither is worth anything.** The exposure alone would be
equally satisfied by a scrub that never ran, so the controls prove the
jailed child still cannot recover a scrubbed value, and that the scrub is a
FILTER rather than a blanket failure.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest

from brig.core import Axis, EnvMode, EnvPolicy, Spec
from brig.mech import CompileCtx
from brig.mech.env_scrub import env_scrub

pytestmark = pytest.mark.integration

_CTX = CompileCtx(jail_dir="/private/tmp/envset", platform=sys.platform)


def _wrapped(policy: EnvPolicy, argv: tuple[str, ...]) -> tuple[str, ...]:
    return env_scrub.compile(Spec(env=policy), _CTX).wrap(argv)


def test_the_exposure_a_set_value_is_placed_verbatim_into_the_rendered_argv() -> None:
    """THE EXPOSURE, asserted where it is deterministic.

    `EnvPolicy.set`'s value appears verbatim in the argv brig hands the
    kernel -- inside `/bin/sh`'s `-c` script, as one of `env -i`'s assignment
    tokens. Anything that can read that argv during the exec chain sees the
    secret. That is the whole of decision-093's declared embedder contract,
    and decision-143 is what put it in the report's own detail instead of
    leaving it in a docstring.

    Asserted against the rendered argv rather than raced against `ps` for the
    reason this module's docstring measures: the window is real but far too
    short for `ps` to sample.
    """
    secret = f"brigsecret{uuid.uuid4().hex}"
    policy = EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",), set=(("TOKEN", secret),))
    argv = _wrapped(policy, ("/bin/sh", "-c", "sleep 5"))

    assert any(secret in token for token in argv), (
        f"the set value must be traceable in the argv brig renders; got {argv!r}"
    )


def test_the_grade_detail_tells_a_report_reader_about_that_argv_exposure() -> None:
    """decision-143 (2). The gap has to reach whoever reads the REPORT, not
    only whoever reads this module's source -- the report is what lands in
    the log and in an embedder's hands. Before this, the detail was `""`."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.SCRUB)), _CTX)
    detail = step.grades[Axis.ENV].detail

    assert "argv" in detail
    assert "AGAINST THE CHILD" in detail


def test_control_the_jailed_child_still_cannot_recover_a_scrubbed_value() -> None:
    """THE CONTROL, and the reason the test above is about host visibility
    rather than a broken scrub.

    A variable present in the PARENT's environment and absent from
    `allow_names` must be unrecoverable inside the wrapped child. If this
    failed, the finding above would be the far less interesting "env_scrub
    does not work".
    """
    marker = f"brigscrubbed{uuid.uuid4().hex}"
    env = {**os.environ, "SHOULD_BE_SCRUBBED": marker}
    policy = EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",))
    argv = _wrapped(policy, ("/bin/sh", "-c", 'printf "%s" "${SHOULD_BE_SCRUBBED-ABSENT}"'))

    done = subprocess.run(argv, env=env, capture_output=True, text=True, check=False, timeout=30)

    assert marker not in done.stdout, f"the scrubbed value leaked INTO the child: {done.stdout!r}"
    assert done.stdout.strip() == "ABSENT", done


def test_control_the_same_variable_survives_when_it_is_allow_listed() -> None:
    """THE SECOND CONTROL. The test above would also pass if the wrap simply
    broke every variable, or ran nothing at all. Allow-listing the same name
    must let the same value through, which proves the scrub is a FILTER and
    not a blanket failure."""
    marker = f"brigallowed{uuid.uuid4().hex}"
    env = {**os.environ, "SHOULD_SURVIVE": marker}
    policy = EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH", "SHOULD_SURVIVE"))
    argv = _wrapped(policy, ("/bin/sh", "-c", 'printf "%s" "${SHOULD_SURVIVE-ABSENT}"'))

    done = subprocess.run(argv, env=env, capture_output=True, text=True, check=False, timeout=30)

    assert done.stdout.strip() == marker, done
