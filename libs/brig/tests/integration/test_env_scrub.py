"""`env_scrub` against a real OS process: task-034's EC1 -- a workload
launched through a stack containing `env_scrub` prints its own environment,
observed from INSIDE the jail, never asserted from the outside via argv.

Every workload here is reaped synchronously within its own test
(`os.waitpid` with a poll loop and a hard timeout), so nothing needs a
`workload_argv` run-id token to survive past the test that launched it --
same posture as `tests/integration/test_trampoline.py`'s own docstring:
`env_scrub`'s render `exec`s all the way through (`/bin/sh` -> `env` ->
the workload), so no intermediate process is left to leak, and by the time
a test here returns, the final process has already exited and been
reaped. `workload_argv`'s run-id token is still embedded (belt and
braces against a hang), so the session-teardown sweep would catch it if a
test's own wait ever failed to return.

Jail directories use a short `/tmp/bg<pid>es<n>` scratch root, never
`tmp_path` (CLAUDE.md: `sun_path` is 104 bytes on darwin; the `es` infix
avoids colliding with sibling integration files -- see `_new_jail_dir`'s
own docstring below).
"""

from __future__ import annotations

import itertools
import os
import subprocess
import sys

import pytest

from brig.core import Axis, EnvMode, EnvPolicy, Spec
from brig.mech import CompileCtx, Mechanism
from brig.mech.env_scrub import env_scrub
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack
from tests.conftest import workload_argv

_jail_counter = itertools.count()

#: The env var name this project's spec author chose to KEEP (SCRUB mode's
#: allow-list) -- deliberately not a real credential-shaped name, so a
#: reader can't mistake this file's test data for a real secret.
_ALLOWED_NAME = "BRIG_TEST_ALLOWED"
_ALLOWED_VALUE = "keep-me-please"

#: The canary: a name NOT on the allow-list. If this ever shows up in a
#: child's printed environment, `env_scrub` failed to scrub it.
_CANARY_NAME = "BRIG_TEST_SECRET_CANARY"
_CANARY_VALUE = "topsecret-do-not-leak"

_SET_KEY = "BRIG_TEST_SET_KEY"
_SET_VALUE = "set-by-policy"

_WAIT_TIMEOUT_S = 10.0


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>es<n>` -- never `tmp_path`. The
    `es` infix (matching `test_kill_group.py`'s `kg`,
    `test_teardown_exec.py`'s `te`, `test_handle_rehydration.py`'s `rh`)
    keeps this file's jail dirs from colliding with another integration
    file's plain `bg<pid>-<n>` counter when both run in the same session:
    several sibling files never clean up their own jail dirs, and a
    same-numbered path a sibling already populated fails a `not
    os.path.exists(jail_dir)` assertion in THAT file for a directory THIS
    file created, not the sibling's own bug."""
    return f"/tmp/bg{os.getpid()}es{next(_jail_counter)}"


def _parse_env_lines(text: str) -> dict[str, str]:
    """Parse `NAME=VALUE` lines (as `/usr/bin/env` with no args prints)
    into a dict, split on the FIRST `=` only (a value may itself contain
    `=`). Blank lines are skipped. This is the "assert on the parsed name
    set, not substring presence" machinery task-034 AC #2/#4 require."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line or "=" not in line:
            continue
        name, _sep, value = line.partition("=")
        result[name] = value
    return result


def _launch_and_collect_stdout(
    *,
    spec: Spec,
    argv: list[str],
    jail_dir: str,
    mechanisms: tuple[Mechanism, ...] = (env_scrub,),
) -> str:
    """Compile `spec` through a `Stack` of `mechanisms` (default: just
    `env_scrub` -- "a stack containing env_scrub", task-034 AC #2's own
    wording), launch `argv` through it, wait for it to exit, and return the
    workload's stdout, read from the jail's own log file (never from argv
    or from the compiled Step -- SPEC.md's "observe from inside the jail,
    not from the outside")."""
    ctx = CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    jail = Stack(mechanisms).compile(spec, ctx=ctx)
    launcher = SubprocessLauncher()
    handle = launcher.launch(
        jail,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="env-scrub-under-test",
        jail_dir=jail_dir,
    )
    handle.wait()
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC #2 (positive, from inside the jail) + AC #4 (control against a broken
# probe).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_env_scrub_hides_the_canary_and_forwards_the_allowlist(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #2: a workload launched through a stack containing `env_scrub`
    prints its own environment; the scrubbed canary name is ABSENT and the
    allow-listed name is PRESENT with its EXACT value -- asserted on the
    PARSED name set/value, never a substring check. AC #4's control lives
    in the SAME test, not a separate one: the allow-listed assertion IS the
    proof the workload's env-printing actually works (if the probe printed
    nothing, or `env` itself failed to run, `_ALLOWED_NAME` would be
    absent too, and this test would fail exactly the same way a real
    scrub-failure would -- so "absent" here is never ambiguous between
    "scrubbed" and "probe broken")."""
    monkeypatch.setenv(_CANARY_NAME, _CANARY_VALUE)
    monkeypatch.setenv(_ALLOWED_NAME, _ALLOWED_VALUE)

    jail_dir = _new_jail_dir()
    spec = Spec(
        env=EnvPolicy(
            mode=EnvMode.SCRUB,
            allow_names=(_ALLOWED_NAME,),
            set=((_SET_KEY, _SET_VALUE),),
        )
    )
    argv = workload_argv(run_id, "env")
    stdout = _launch_and_collect_stdout(spec=spec, argv=argv, jail_dir=jail_dir)

    names = _parse_env_lines(stdout)

    # The scrubbed canary: ABSENT.
    assert _CANARY_NAME not in names, (
        f"{_CANARY_NAME!r} leaked into the child's environment: {names!r}"
    )
    # The control (AC #4): the allow-listed name arrived, with its EXACT
    # forwarded value -- proves the probe itself works.
    assert _ALLOWED_NAME in names
    assert names[_ALLOWED_NAME] == _ALLOWED_VALUE
    # The `set` pair: PRESENT with its literal compiled-in value.
    assert _SET_KEY in names
    assert names[_SET_KEY] == _SET_VALUE


@pytest.mark.integration
def test_allow_listed_name_absent_in_parent_stays_absent_not_empty(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An allow-listed name the LAUNCHING process never had at all must be
    ABSENT from the child, not silently defined as an empty string.
    `${NAME:+"NAME=$NAME"}` (see `env_scrub.py`'s `_assignment_tokens`
    docstring) exists specifically to distinguish this from the simpler,
    WRONG `NAME="$NAME"` form, which still creates the binding even when
    `/bin/sh` never inherited the name -- observed directly on this host
    (this task's notes) before this render shape was chosen. The CONTROL
    lives in THIS test, not only in a sibling: a `set` pair travels
    alongside the (absent) allow-listed name in the SAME spec/probe run,
    so a probe that printed nothing at all (workload never ran, `env`
    failed to exec) would fail this test on the `set`-pair assertion even
    though `_ALLOWED_NAME not in names` would otherwise pass vacuously --
    a cross-test pointer to a sibling does not, by itself, discharge the
    control rule for a test that can be green on a broken probe."""
    monkeypatch.delenv(_ALLOWED_NAME, raising=False)

    jail_dir = _new_jail_dir()
    spec = Spec(
        env=EnvPolicy(
            mode=EnvMode.SCRUB, allow_names=(_ALLOWED_NAME,), set=((_SET_KEY, _SET_VALUE),)
        )
    )
    argv = workload_argv(run_id, "env")
    stdout = _launch_and_collect_stdout(spec=spec, argv=argv, jail_dir=jail_dir)

    names = _parse_env_lines(stdout)
    assert _ALLOWED_NAME not in names, (
        f"{_ALLOWED_NAME!r} was never inherited by the launching process, "
        f"yet arrived in the child's environment (even if empty): {names!r}"
    )
    # The control: proves this probe run actually executed and printed a
    # real environment, not an empty/failed capture.
    assert names.get(_SET_KEY) == _SET_VALUE


@pytest.mark.integration
def test_env_scrub_pass_mode_forwards_everything_and_applies_set(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PASS mode's own positive case (task-033's ruling: PASS confers
    everything): the "canary" here is not scrubbed by design -- present,
    same as any other inherited var -- and a `set` pair still overrides on
    top of full inheritance, via `Step.env` (see `env_scrub.py`'s module
    docstring on why PASS routes `set` differently than SCRUB does)."""
    monkeypatch.setenv(_CANARY_NAME, _CANARY_VALUE)

    jail_dir = _new_jail_dir()
    spec = Spec(env=EnvPolicy(mode=EnvMode.PASS, set=((_SET_KEY, _SET_VALUE),)))
    argv = workload_argv(run_id, "env")
    stdout = _launch_and_collect_stdout(spec=spec, argv=argv, jail_dir=jail_dir)

    names = _parse_env_lines(stdout)
    assert names.get(_CANARY_NAME) == _CANARY_VALUE
    assert names.get(_SET_KEY) == _SET_VALUE


# ---------------------------------------------------------------------------
# AC #3: the mutation check MILESTONES names explicitly. This is the
# PERMANENT half proving the probe above is discriminating (CLAUDE.md:
# "prefer a control ... over an assertion in isolation") -- the ONE-TIME
# manual plant/revert against the working tree itself (with its own
# scratch-copy + sha256 evidence) is recorded separately in this task's
# notes, per WORKFLOW.md's binding restoration discipline.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_control_without_env_scrub_the_same_probe_sees_the_secret(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #3's permanent control: the identical Spec, identical probe
    (`env`, parsed the same way), through the EMPTY stack instead of
    `[env_scrub]` -- i.e. `env_scrub` "removed from the stack". Every
    run of this suite re-proves that without the mechanism, the SAME
    probe that passed above now sees the secret -- the ongoing, always-
    green form of the falsifiability MILESTONES.md's EC1 mutation check
    asks for."""
    monkeypatch.setenv(_CANARY_NAME, _CANARY_VALUE)
    monkeypatch.setenv(_ALLOWED_NAME, _ALLOWED_VALUE)

    jail_dir = _new_jail_dir()
    spec = Spec(
        env=EnvPolicy(
            mode=EnvMode.SCRUB,
            allow_names=(_ALLOWED_NAME,),
            set=((_SET_KEY, _SET_VALUE),),
        )
    )
    argv = workload_argv(run_id, "env")
    # The mutation: `mechanisms=()` -- env_scrub REMOVED from the stack.
    stdout = _launch_and_collect_stdout(spec=spec, argv=argv, jail_dir=jail_dir, mechanisms=())

    names = _parse_env_lines(stdout)
    assert names.get(_CANARY_NAME) == _CANARY_VALUE, (
        "expected the SAME probe to see the secret with env_scrub removed "
        f"from the stack -- got {names!r}"
    )


# ---------------------------------------------------------------------------
# AC #5: grade honesty -- attempted recovery of a scrubbed value from
# inside the jail.
# ---------------------------------------------------------------------------

_RECOVERY_SCRIPT = (
    "echo ---environ---; "
    "cat /proc/self/environ 2>&1; "
    "echo ---ps-eww---; "
    "ps eww $$ 2>&1; "
    "echo ---reexec-sh---; "
    "sh -c env 2>&1; "
    "echo ---reexec-bash---; "
    "bash -c env 2>&1"
)


@pytest.mark.integration
def test_scrubbed_value_is_not_recoverable_from_inside_the_jail(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #5: the attempted-recovery evidence the grade honesty rule
    requires, run for real rather than only reasoned about -- reading
    `/proc/self/environ` (absent on darwin: no `/proc`), trying
    `ps eww $$` (this host's `ps` does not print environment for a process,
    darwin or not -- confirmed empirically, not assumed), and re-execing a
    fresh shell (`sh -c env`, `bash -c env`) from INSIDE the already-
    scrubbed process, which can only ever inherit what that process itself
    already has -- never the original, pre-scrub value. If ANY of these
    recovered the canary, `Grade.ENFORCED` would be wrong and this test
    documents that outcome instead of hiding it."""
    monkeypatch.setenv(_CANARY_NAME, _CANARY_VALUE)
    monkeypatch.setenv(_ALLOWED_NAME, _ALLOWED_VALUE)

    jail_dir = _new_jail_dir()
    spec = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=(_ALLOWED_NAME,)))
    argv = workload_argv(run_id, _RECOVERY_SCRIPT)
    stdout = _launch_and_collect_stdout(spec=spec, argv=argv, jail_dir=jail_dir)

    assert _CANARY_VALUE not in stdout, (
        f"a recovery attempt exposed the scrubbed canary value -- grade must "
        f"not be ENFORCED. Full output:\n{stdout}"
    )
    # Control: the allow-listed value legitimately appears (at least in the
    # first `env` dump) -- proves the recovery attempts' own output capture
    # actually works, same "control against a broken probe" posture as
    # AC #4's test above.
    assert _ALLOWED_VALUE in stdout


# ---------------------------------------------------------------------------
# AC #7's mutation-pairing control: `env_scrub`'s single claimed axis.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_axes_claim_is_the_env_axis_alone_end_to_end() -> None:
    """A `Stack([env_scrub])` compiles with `env` claimed and every other
    axis falling back to `unenforced` -- the coverage step's own proof
    that `env_scrub` claims exactly one axis, exercised through the real
    `Stack.compile` path rather than reading `.axes` in isolation (the
    unit tier already covers that; see
    `tests/unit/test_env_scrub_compile.py::test_axes_is_exactly_env`)."""
    ctx = CompileCtx(jail_dir=_new_jail_dir(), platform=sys.platform)
    jail = Stack([env_scrub]).compile(Spec(), ctx=ctx)
    assert jail.report.axes[Axis.ENV].grade.value == "enforced"
    for axis in Axis:
        if axis is Axis.ENV:
            continue
        assert jail.report.axes[axis].grade.value == "unenforced"


@pytest.mark.integration
def test_portability_rendered_argv_runs_directly_via_usr_bin_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC #8: run the RENDERED argv directly (not through the launcher, not
    reasoned about) and confirm `/usr/bin/env` actually ran and the
    workload received the constructed environment -- decision-066's named
    risk ("the darwin/GNU env -i divergence must be RUN as evidence"),
    exercised for real on this host."""
    monkeypatch.setenv(_ALLOWED_NAME, _ALLOWED_VALUE)
    monkeypatch.setenv(_CANARY_NAME, _CANARY_VALUE)

    ctx = CompileCtx(jail_dir=_new_jail_dir(), platform=sys.platform)
    policy = EnvPolicy(
        mode=EnvMode.SCRUB, allow_names=(_ALLOWED_NAME,), set=((_SET_KEY, _SET_VALUE),)
    )
    step = env_scrub.compile(Spec(env=policy), ctx)
    rendered = step.wrap(("bash", "-c", "env"))

    result = subprocess.run(rendered, capture_output=True, text=True, timeout=10, check=True)
    names = _parse_env_lines(result.stdout)
    assert _CANARY_NAME not in names
    assert names[_ALLOWED_NAME] == _ALLOWED_VALUE
    assert names[_SET_KEY] == _SET_VALUE
