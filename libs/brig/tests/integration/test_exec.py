"""`exec_in_jail` against a real OS process: MILESTONES.md M2 exit criterion
4 verbatim -- `handle.exec(["pwd"])` runs in the jail's cwd; the exec is
durably registered so a later process can reap it -- plus SPEC.md §9's
same-Spec-env law (the jail's own declared overlay reaches the sibling, and
wins over the calling process's environment).

The registration used to be an `EXEC` record in the per-jail event stream;
decision-152 (2026-09-08) deleted that stream and `brig/run/_execs.py`'s
one-file-per-live-sibling directory replaced it. The assertions here follow
the medium; the clause they enforce -- durability outside the live object --
is unchanged.

Every test tears its own long-lived workload down directly
(`os.killpg`/`os.kill` + reap), same as `test_launcher.py`. Teardown here is
deliberately hand-rolled rather than `Handle.kill()`: a test's cleanup path
must not be the code under test, so a teardown bug cannot hide behind its
own helper. `kill_jail` has been functional since task-020; this is a
choice, not a gap. The workload each test launches
(a `sleep` the exec runs alongside) is built through
`tests.conftest.workload_argv` so the leak sweep catches anything that
escapes; the exec'd commands themselves (`pwd`, `true`, `bash -c "exit N"`,
a `python -c` one-liner) are short-lived and always `wait()`-ed on
synchronously within the test, so they need no token of their own -- by the
time a test returns, `ExecHandle.wait()` has already reaped them.

**`cwd` and `jail_dir` are deliberately two different directories in every
test here**, not the same one as `test_launcher.py`'s convenience default:
an `exec_in_jail` that returned `jail_dir` instead of `handle.cwd` would
still pass a test where the two happen to coincide.

Short `/tmp/bg<pid>ex<n>` scratch roots throughout, never `tmp_path`
(`sun_path` is 104 bytes on darwin); paths are compared through
`os.path.realpath` so `/tmp` vs `/private/tmp` on darwin cannot cause a
false negative.
"""

from __future__ import annotations

import itertools
import os
import signal
import subprocess
import sys

import pytest

from brig.core import Spec, unenforced_report
from brig.mech import LaunchFeature
from brig.run import _identity as identity
from brig.run._execs import live as live_execs
from brig.run.exec_ import ExecFidelity, ExecRefused, exec_in_jail
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv

_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>ex<n>` -- never `tmp_path`."""
    return f"/tmp/bg{os.getpid()}ex{next(_counter)}"


def _new_cwd_dir() -> str:
    """A separate short scratch root for `cwd`, distinct from any
    `jail_dir` -- see the module docstring for why the two must never be
    the same path in this file."""
    path = f"/tmp/bg{os.getpid()}ex{next(_counter)}-cwd"
    os.makedirs(path, exist_ok=True)
    return path


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail(
    *,
    env: dict[str, str] | None = None,
    requires: frozenset[LaunchFeature] = frozenset(),
) -> CompiledJail:
    """A minimal, mechanism-free `CompiledJail` -- the empty stack's shape,
    same idiom as `test_launcher.py`'s helper of the same name."""
    return CompiledJail(
        spec=Spec(),
        report=unenforced_report(),
        wrap=_identity_wrap,
        env=env if env is not None else {},
        staged=(),
        helpers=(),
        requires=requires,
        mechanism_names=(),
        matrix_version=1,
    )


def _launch(
    argv: list[str],
    *,
    cwd: str,
    jail: CompiledJail | None = None,
    jail_id: str = "jail-under-test",
    jail_dir: str | None = None,
) -> Handle:
    launcher = SubprocessLauncher()
    return launcher.launch(
        jail if jail is not None else _compiled_jail(),
        argv=argv,
        cwd=cwd,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir if jail_dir is not None else _new_jail_dir(),
    )


def _teardown_group(handle: Handle) -> None:
    """Group-kill the long-lived workload. The kill here is deliberately
    hand-rolled (`killpg`) rather than `kill_jail`: a test's cleanup path
    must not be the code under test, so a teardown bug cannot hide behind its
    own helper. `kill_jail` has been functional since task-020; this is a
    choice, not a gap. `handle.wait()` blocks until the launcher's exit-waiter
    has reaped it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _ps_pgid(pid: int) -> int:
    """Read a live pid's real process-group id via `/bin/ps` (alias-proof,
    decision-026 -- never a bare `ps`)."""
    proc = subprocess.run(
        ["/bin/ps", "-o", "pgid=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(proc.stdout.strip())


def _registered(handle: Handle) -> list[tuple[int, int, str]]:
    """`(pid, pgid, start_time)` for every sibling still registered against
    this jail -- read off disk, the way a rehydrated handle in another
    process would read it. The third field is decision-155's start-time
    stamp."""
    return live_execs(handle.jail_dir)


def _new_handle(
    run_id: str, *, jail: CompiledJail | None = None, jail_id: str = "jail-under-test"
) -> Handle:
    """A handle whose workload is a `sleep 5` the exec runs alongside --
    `run_id`-tagged so the leak sweep catches it if this test's own
    teardown fails."""
    return _launch(
        workload_argv(run_id, "sleep 5"),
        cwd=_new_cwd_dir(),
        jail=jail,
        jail_id=jail_id,
        jail_dir=_new_jail_dir(),
    )


# ---------------------------------------------------------------------------
# AC #2 / #3 -- EC4 literal, and its discriminating control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_pwd_writes_exactly_the_jail_cwd(run_id: str) -> None:
    """AC #2, MILESTONES.md M2 EC4 literal: `handle.exec(["pwd"])` writes
    exactly the jail's `cwd` (resolved through `/private/tmp`) to its
    stdout file -- exact equality after strip, not containment."""
    handle = _new_handle(run_id)
    try:
        exec_handle = exec_in_jail(handle, ["pwd"])
        assert exec_handle.wait(timeout=5.0) == 0
        with open(exec_handle.stdout_path) as f:
            content = f.read().strip()
        assert os.path.realpath(content) == os.path.realpath(handle.cwd)
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_exec_pwd_control_two_handles_different_cwds(run_id: str) -> None:
    """AC #3: the discriminating control. Two handles launched with
    DIFFERENT cwds each exec `pwd` and each returns its OWN cwd -- without
    this, AC #2's assertion passes for an implementation that inherited the
    test runner's cwd and happened to match."""
    handle_a = _new_handle(run_id, jail_id="jail-cwd-a")
    handle_b = _new_handle(run_id, jail_id="jail-cwd-b")
    assert handle_a.cwd != handle_b.cwd
    try:
        exec_a = exec_in_jail(handle_a, ["pwd"])
        exec_b = exec_in_jail(handle_b, ["pwd"])
        assert exec_a.wait(timeout=5.0) == 0
        assert exec_b.wait(timeout=5.0) == 0
        with open(exec_a.stdout_path) as f:
            content_a = f.read().strip()
        with open(exec_b.stdout_path) as f:
            content_b = f.read().strip()
        assert os.path.realpath(content_a) == os.path.realpath(handle_a.cwd)
        assert os.path.realpath(content_b) == os.path.realpath(handle_b.cwd)
        assert content_a != content_b
    finally:
        _teardown_group(handle_a)
        _teardown_group(handle_b)


# ---------------------------------------------------------------------------
# AC #4 / #5 -- env positive and negative, one exec, two markers.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_env_jail_overlay_reaches_the_sibling_and_wins(run_id: str) -> None:
    """AC #4 (positive) and AC #5 (the real assertion) as one exec, one
    process, two markers -- proving the reader works AND that the jail's
    own overlay is what decides, not this process's environment.

    `present_marker` comes from the `CompiledJail`'s `env` (what a
    mechanism would set). `contested_marker` is set in the jail's env AND,
    after launch, in THIS process's `os.environ` with a different value:
    `exec_in_jail` composes `{**os.environ, **handle.jail_env}`, so the
    jail's value must win. An exec that inherited the calling process's
    environment *over* the jail's overlay would be a weaker confinement
    than the workload's own -- SPEC.md §9's law, and what this pins.

    What this test no longer claims (decision-152, 2026-09-08): that a
    variable set in this process after launch is INVISIBLE to the sibling.
    That was a property of `Handle.env`, a launch-time snapshot of the
    launching process's whole environment, which is deleted -- a serialized
    handle carrying the operator's environment is a handle no embedder can
    put in its own log. The overlay, which is the mechanism-declared half
    and the only half that was ever policy, still wins.
    """
    present_marker = f"BRIG_JAIL_ENV_{run_id}"
    contested_marker = f"BRIG_CONTESTED_{run_id}"
    jail = _compiled_jail(env={present_marker: "jail-value-xyz", contested_marker: "jail-wins"})
    handle = _new_handle(run_id, jail=jail)
    try:
        # The premise the second half rests on, made explicit.
        assert handle.jail_env[present_marker] == "jail-value-xyz"

        os.environ[contested_marker] = "host-value-should-lose"
        try:
            script = (
                "import os, sys\n"
                f"sys.stdout.write('PRESENT=[' + os.environ.get({present_marker!r}, '') + ']\\n')\n"
                f"sys.stdout.write('CONTESTED=[' + os.environ.get({contested_marker!r}, '') + ']\\n')\n"
            )
            exec_handle = exec_in_jail(handle, [sys.executable, "-c", script])
            assert exec_handle.wait(timeout=5.0) == 0
            with open(exec_handle.stdout_path) as f:
                lines = f.read().splitlines()
        finally:
            del os.environ[contested_marker]

        assert lines == ["PRESENT=[jail-value-xyz]", "CONTESTED=[jail-wins]"]
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #6 -- the sibling's durable registration, and its removal.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_registers_the_sibling_and_wait_deregisters_it(run_id: str) -> None:
    """AC #6, EC4 second half: `exec` records the sibling somewhere a LATER
    process can read (SPEC.md §9's binding durability clause) -- carrying
    both `pid` and `pgid`, because teardown signals the GROUP -- and the
    first `wait()` that observes an exit status takes it back off the live
    list. Asserted by reading the registration off disk, never from the
    live `ExecHandle`."""
    handle = _new_handle(run_id, jail_id="jail-exec-evt")
    try:
        assert _registered(handle) == []

        exec_handle = exec_in_jail(handle, ["sleep", "5"])
        registered = _registered(handle)
        assert [pid for pid, _pgid, _stamp in registered] == [exec_handle.pid]
        assert registered[0][1] == _ps_pgid(exec_handle.pid)
        # decision-155: the registration carries WHEN this sibling started as
        # well as its number, so a teardown running later cannot mistake a
        # recycled pid for a sibling it still has to reap.
        assert registered[0][2] == identity.start_stamp(exec_handle.pid) != identity.UNKNOWN

        os.killpg(registered[0][1], signal.SIGKILL)
        exec_handle.wait(timeout=5.0)
        assert _registered(handle) == []
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_wait_is_idempotent_and_deregisters_once(run_id: str) -> None:
    """Mutation-target for `ExecHandle._ended`: calling `wait()` twice
    returns the same status both times, and the second call does not fail
    on an already-removed registration."""
    handle = _new_handle(run_id)
    try:
        exec_handle = exec_in_jail(handle, ["true"])
        first = exec_handle.wait(timeout=5.0)
        second = exec_handle.wait(timeout=5.0)
        assert first == second == 0
        assert _registered(handle) == []
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #7 -- exit status propagates, with a control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exit_status_propagates_and_control_is_zero(run_id: str) -> None:
    """AC #7: `wait()` on a command that exits 3 returns 3; the control,
    the same shape exiting 0, returns 0."""
    handle = _new_handle(run_id)
    try:
        exec_three = exec_in_jail(handle, ["bash", "-c", "exit 3"])
        assert exec_three.wait(timeout=5.0) == 3

        exec_zero = exec_in_jail(handle, ["bash", "-c", "exit 0"])
        assert exec_zero.wait(timeout=5.0) == 0
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #8 -- interactive=True refuses naming PTY, and its control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_interactive_refuses_naming_pty_control_noninteractive_succeeds(run_id: str) -> None:
    """AC #8: `interactive=True` refuses, naming `PTY` on the structured
    `missing` field (not `str(exc)`), and spawns nothing -- no sibling is
    registered for the refused attempt. The control: the same call with
    `interactive=False` succeeds and IS registered."""
    handle = _new_handle(run_id)
    try:
        assert _registered(handle) == []

        with pytest.raises(ExecRefused) as exc_info:
            exec_in_jail(handle, ["true"], interactive=True)
        assert LaunchFeature.PTY in exc_info.value.missing

        assert _registered(handle) == []

        exec_handle = exec_in_jail(handle, ["sleep", "5"])
        assert len(_registered(handle)) == 1

        os.killpg(_registered(handle)[0][1], signal.SIGKILL)
        exec_handle.wait(timeout=5.0)
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #9 -- fidelity is honest, and the same-Spec claim is checkable.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_fidelity_is_plain_and_spec_matches_handles(run_id: str) -> None:
    """AC #9: the empty stack's exec grades `ExecFidelity.PLAIN`, asserted
    as the enum member (not a string); `exec_handle.spec` equals
    `handle.spec` -- SPEC.md §9's same-Spec claim, made checkable."""
    handle = _new_handle(run_id)
    try:
        exec_handle = exec_in_jail(handle, ["true"])
        assert exec_handle.wait(timeout=5.0) == 0
        assert exec_handle.fidelity is ExecFidelity.PLAIN
        assert exec_handle.spec == handle.spec
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #10 -- sibling, not child: distinct pid AND distinct pgid, workload survives.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_exec_is_a_sibling_with_its_own_pgid_and_workload_survives(run_id: str) -> None:
    """AC #10: the exec pid differs from the workload pid -- and, the
    discriminating half, the exec's OWN process group (read from
    `/bin/ps`, while it is still running) differs from `handle.pgid`, not
    merely from the test's own pgid. Without the pgid check, an
    implementation that exec'd *into* the workload's process group would
    still pass on pid alone.

    The workload-survives clause is asserted TWICE, deliberately: `alive()`
    alone is non-discriminating here (the workload is `sleep 5`, the exec
    is `sleep 0.5` -- the workload would read alive at that moment
    regardless of what `exec_in_jail` did to it, since 0.5s < 5s and
    nothing in the exec path signals anything). The `/bin/ps`-read pgid
    check after `wait()` is what actually proves the workload is
    untouched: still leading its OWN group (`handle.pgid`, unchanged), not
    reparented into or absorbed by the exec's group."""
    handle = _new_handle(run_id)
    try:
        assert handle.alive() is True
        workload_pgid_before = _ps_pgid(handle.pid)
        assert workload_pgid_before == handle.pgid

        exec_handle = exec_in_jail(handle, ["sleep", "0.5"])
        assert exec_handle.pid != handle.pid
        exec_pgid = _ps_pgid(exec_handle.pid)
        assert exec_pgid == exec_handle.pid  # leads its own group
        assert exec_pgid != handle.pgid

        assert exec_handle.wait(timeout=5.0) == 0
        assert handle.alive() is True
        assert _ps_pgid(handle.pid) == handle.pgid  # still its own group, untouched
    finally:
        _teardown_group(handle)
