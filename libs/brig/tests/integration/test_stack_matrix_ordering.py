"""task-037 AC #7: the ordering rationale's own two consequences, VERIFIED.

`brig/stack/__init__.py`'s `_ENV_SCRUB_RLIMITS_RATIONALE` makes two claims
that must be RUN, not merely accepted on the rationale's own say-so:

1. **The env claim.** With `rlimits` composed outermost, the trampoline
   briefly holds the UNSCRUBBED parent environment before it execs into
   `env_scrub`'s own `/bin/sh -c 'exec env -i ...'` wrapper -- acceptable
   only because both intermediate process images are brig's own trusted
   code and both `exec` away, so the FINAL workload's environ is still
   scrubbed by the time it runs.
2. **The cpu claim -- the actual security reason FOR rlimits-outermost.**
   Because `RLIMIT_CPU` is inherited across every later `exec` in the same
   pid, the cap set by the trampoline reaches through `env_scrub`'s own
   `/bin/sh` and `/usr/bin/env` pre-exec images to the final workload.
   Nothing else in the tree runs this: `test_trampoline_composition.py`
   proves SIGXCPU survives a wrapper stacked OUTSIDE the trampoline (the
   opposite direction), `test_rlimits.py` runs `rlimits` alone, and this
   file's own env test (below) deliberately uses a generous limit so the
   cpu axis is explicitly not what it exercises. Without a test that
   actually composes both mechanisms under a TIGHT limit, the cpu claim
   would rest on POSIX exec/rlimit semantics plus the trampoline's own
   docstring -- true, but exactly the "claim that reads stronger than
   what was tested" defect class CLAUDE.md names. This file closes that
   gap.

This file runs the REAL `Stack([env_scrub, rlimits])`, compiled through the
REAL matrix (no monkeypatching), launched via the REAL `SubprocessLauncher`
-- the same "observe from inside the jail" posture
`tests/integration/test_env_scrub.py` already establishes for `env_scrub`
alone, extended here to the composed two-mechanism stack the unit tier
(`tests/unit/test_stack_compile.py`) can only reason about via argv shape,
never actually run.

`sun_path` is 104 bytes on darwin: every scratch path here is a short
`/tmp/bg<pid>sm<n>` root, never `tmp_path` (CLAUDE.md's trap list; the `sm`
infix -- "stack matrix" -- keeps this file's jail dirs from colliding with
a sibling integration file's own counter, matching
`tests/integration/test_env_scrub.py::_new_jail_dir`'s own convention).
"""

from __future__ import annotations

import itertools
import os
import signal
import sys
import time

import pytest

import brig.stack
from brig.core import EnvMode, EnvPolicy, Limits, Spec
from brig.mech import CompileCtx
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack
from tests.conftest import workload_argv

_jail_counter = itertools.count()

#: Not on the allow-list -- must NOT reach the workload under either
#: mechanism, let alone the composed stack.
_CANARY_NAME = "BRIG_T037_SECRET_CANARY"
_CANARY_VALUE = "topsecret-do-not-leak-t037"

#: On the allow-list -- the control against a vacuous pass (see the test's
#: own docstring): if this were also absent, "the canary is absent" could
#: mean "scrubbed correctly" or "the probe never ran", indistinguishably.
_ALLOWED_NAME = "BRIG_T037_ALLOWED"
_ALLOWED_VALUE = "keep-me-t037"

#: Embedded as the spin loop's own first source line so it shows up in
#: `/bin/ps`'s command column while the process is alive -- same
#: convention as `test_rlimits.py`'s `_SPIN_LOOP_MARKER` and
#: `test_trampoline_composition.py`'s marker of the same purpose.
_SPIN_LOOP_MARKER = "T037_SPIN_MARKER"
_SPIN_LOOP = f"# {_SPIN_LOOP_MARKER}\nx = 0\nwhile True:\n    x += 1\n"


def _new_jail_dir() -> str:
    return f"/tmp/bg{os.getpid()}sm{next(_jail_counter)}"


def _parse_env_lines(text: str) -> dict[str, str]:
    """Parse `NAME=VALUE` lines (as `/usr/bin/env` with no args prints)
    into a dict, split on the FIRST `=` only. Same shape as
    `tests/integration/test_env_scrub.py`'s own helper of the same name."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line or "=" not in line:
            continue
        name, _sep, value = line.partition("=")
        result[name] = value
    return result


@pytest.mark.integration
def test_composed_stack_rlimits_outermost_workload_environ_still_scrubbed(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """task-037 AC #7: under the REAL, matrix-ordered `Stack([env_scrub,
    rlimits])` (rlimits outermost, per the shipped matrix -- not asserted,
    read from the live module), a workload launched through the REAL
    `SubprocessLauncher` prints its own environment from INSIDE the jail;
    the unlisted canary is ABSENT and the allow-listed name is PRESENT
    with its exact value.

    The `cpu_seconds=60` limit is deliberately generous: this test's
    subject is the ENV axis's ordering consequence, not the cpu axis
    (`tests/integration/test_rlimits.py` and
    `tests/integration/test_trampoline_composition.py` already cover
    SIGXCPU tripping under a tight limit) -- a workload that died on
    SIGXCPU before printing its environment would make this test fail for
    the wrong reason, indistinguishable from a real scrub failure.
    """
    assert brig.stack.COMPATIBILITY_MATRIX[frozenset({"env_scrub", "rlimits"})].outer == (
        "rlimits"
    )  # the property under test is real, not a stale docstring claim
    monkeypatch.setenv(_CANARY_NAME, _CANARY_VALUE)
    monkeypatch.setenv(_ALLOWED_NAME, _ALLOWED_VALUE)

    jail_dir = _new_jail_dir()
    ctx = CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    spec = Spec(
        limits=Limits(cpu_seconds=60),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=(_ALLOWED_NAME,)),
    )
    jail = Stack([env_scrub, rlimits]).compile(spec, ctx=ctx)

    # The composed argv itself: the trampoline (rlimits) is OUTERMOST --
    # the exact argv-shape claim task-037 AC #2 pins at the unit tier,
    # reconfirmed here against the REAL compiled jail this test actually
    # launches (not merely reasoned about).
    argv = list(workload_argv(run_id, "env"))
    composed = jail.wrap(tuple(argv))
    assert composed[:6] == (sys.executable, "-m", "brig.mech.trampoline", "--cpu", "60", "--")
    assert composed[6] == "/bin/sh"

    launcher = SubprocessLauncher()
    handle = launcher.launch(
        jail,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="t037-composed",
        jail_dir=jail_dir,
    )
    handle.wait(timeout=20.0)
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout = f.read()

    names = _parse_env_lines(stdout)

    # The consequence under test: the FINAL workload's environ is
    # scrubbed, even though rlimits -- not env_scrub -- is outermost.
    assert _CANARY_NAME not in names, (
        f"{_CANARY_NAME!r} leaked into the composed stack's child "
        f"environment with rlimits outermost: {names!r}"
    )
    # Control against a vacuous pass: the allow-listed name legitimately
    # arrived, proving the probe (and env_scrub's own forwarding) actually
    # ran, rather than the workload having failed to launch or print at
    # all.
    assert _ALLOWED_NAME in names
    assert names[_ALLOWED_NAME] == _ALLOWED_VALUE


@pytest.mark.integration
def test_composed_stack_rlimits_cpu_cap_still_reaches_through_env_scrubs_pre_exec_images(
    run_id: str,
) -> None:
    """task-037 AC #7: the rationale's OTHER consequence -- the actual
    security reason for `rlimits` outermost, not merely the ordering's
    side effect on env. A `cpu_seconds=1` spin loop, launched through the
    SAME REAL, matrix-ordered `Stack([env_scrub, rlimits])` as the test
    above (env_scrub's SCRUB-mode `/bin/sh` and `/usr/bin/env` pre-exec
    images sitting BETWEEN the trampoline and the workload), still dies on
    `SIGXCPU` -- proving the cap set on the trampoline genuinely reaches
    through those images to the workload, not merely "the same behaviour
    as `rlimits` alone" (`test_rlimits.py`) or "survives a wrapper stacked
    OUTSIDE the trampoline" (`test_trampoline_composition.py`, the
    opposite direction from what env_scrub's inner nesting requires).

    The workload argv is a bare `sys.executable` (an absolute path) rather
    than routed through `bash`/`workload_argv`: `env_scrub`'s SCRUB-mode
    render clears `PATH` (`env -i`), but `execvp` with an argument
    containing a `/` never consults `PATH` at all (POSIX: PATH search
    happens only for a bare name) -- an absolute interpreter path is
    exec'd directly regardless, so this is not something that needs `PATH`
    to be forwarded to work.
    """
    assert int(signal.SIGXCPU) == 24  # platform pin, asserted not assumed
    jail_dir = _new_jail_dir()
    ctx = CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    spec = Spec(
        limits=Limits(cpu_seconds=1),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=()),
    )
    jail = Stack([env_scrub, rlimits]).compile(spec, ctx=ctx)
    launcher = SubprocessLauncher()

    argv = [sys.executable, "-c", _SPIN_LOOP]
    start = time.monotonic()
    handle = launcher.launch(
        jail,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"t037-cpu-{run_id[:8]}",
        jail_dir=jail_dir,
    )
    status = handle.wait(timeout=20.0)
    wall_time = time.monotonic() - start

    assert status == -signal.SIGXCPU, (
        f"expected death by SIGXCPU ({-signal.SIGXCPU}), got {status} -- "
        "the cpu cap set on the trampoline did not reach through env_scrub's "
        "pre-exec images to the workload; the ordering rationale's cpu claim "
        "would be wrong"
    )
    assert wall_time < 10.0
