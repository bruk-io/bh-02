"""`Handle.exec` and `Handle.wait_ready`, exercised as BOUND methods.

task-030 / decision-053, on doc-007 §6 D-7's finding: SPEC.md §9's `exec`
criterion (MILESTONES.md M2 EC4) reads `handle.exec(["pwd"])`, and
`Handle.wait_ready`'s signature is likewise part of that same public block --
but `handle.py`'s two methods here are each a short delegate to a private
module function, and every existing test in the suite calls that private
function directly rather than the bound method an embedder actually calls.
decision-053, quoted: "**a public surface is not discharged one hop away.**
A test that reaches past the method an embedder calls, into the function
that method delegates to, proves the delegate's callee and not the
delegate."

This file exists to close exactly that gap, and only that gap -- it does not
replace or duplicate the module-function coverage `test_exec.py` and
`test_wait_ready.py` already carry; it adds the one thing they structurally
cannot prove, which is that the bound method wires its arguments to that
function correctly. Nothing here imports the delegate-callee functions or
their private module paths at all, by construction: a test that could still
pass after importing around `Handle.exec`/`Handle.wait_ready` would not be
testing them.

Same environment traps as every other M2 integration file touching a jail or
a socket (CLAUDE.md, this task's own text): short `/tmp/bg<pid>hd<n>` scratch
roots throughout, never pytest's `tmp_path` (`sun_path` is 104 bytes on
darwin); paths compared through `os.path.realpath` so `/tmp` vs
`/private/tmp` on darwin cannot cause a false negative. Every workload is
spawned through `tests.conftest.workload_argv` so the suite-wide leak sweep
(task-013/task-027) can find it without any cooperation from this file. The
scratch-root and workload-shape helpers below are deliberately copied from
`test_exec.py`/`test_wait_ready.py`, not imported from them -- this task's
own Deliverable text asks for that, so this file stays coupled only to
`tests.conftest`, never to another test module.
"""

from __future__ import annotations

import itertools
import os
import shutil
import time
from typing import Protocol, cast

import pytest

from brig.core import Channel, ChannelKind, Spec, unenforced_report
from brig.mech import LaunchFeature
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv

_counter = itertools.count()


class _NamedTimeout(Protocol):
    """The structured-field shape of the timeout `Handle.wait_ready` is
    expected to raise, reproduced locally as a `Protocol` so this file can
    type-check the caught exception's fields under `mypy --strict` without
    importing the concrete exception class -- the same reason this module
    checks the exception's class *name* rather than its identity (see the
    module docstring)."""

    channel: str
    endpoint: str
    timeout: float


class _NamedExecRefusal(Protocol):
    """Same idiom as `_NamedTimeout`, for the exception `Handle.exec` is
    expected to raise on `interactive=True` -- `LaunchFeature` is imported
    (it lives in `brig.mech`, a layer below `brig.run`, not in the module
    this file is forbidden from importing), but the exception class itself
    is still checked by name only."""

    missing: frozenset[LaunchFeature]


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>hd<n>` -- never `tmp_path`."""
    return f"/tmp/bg{os.getpid()}hd{next(_counter)}"


def _new_cwd_dir() -> str:
    """A separate short scratch root for `cwd`, distinct from any
    `jail_dir` -- same discipline as `test_exec.py`: an implementation that
    conflated `jail_dir` with `cwd` must not be able to pass by accident."""
    path = f"/tmp/bg{os.getpid()}hd{next(_counter)}-cwd"
    os.makedirs(path, exist_ok=True)
    return path


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail(*, spec: Spec | None = None) -> CompiledJail:
    """A minimal, mechanism-free `CompiledJail` -- the empty stack's shape,
    same idiom every M2 integration file uses."""
    return CompiledJail(
        spec=spec if spec is not None else Spec(),
        report=unenforced_report(),
        wrap=_identity_wrap,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        mechanism_names=(),
        matrix_version=1,
    )


def _launch(
    argv: list[str],
    *,
    cwd: str,
    jail_dir: str,
    spec: Spec | None = None,
    jail_id: str = "jail-under-test",
) -> Handle:
    launcher = SubprocessLauncher()
    return launcher.launch(
        _compiled_jail(spec=spec),
        argv=argv,
        cwd=cwd,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _teardown_group(handle: Handle, jail_dir: str | None = None) -> None:
    """Group-kill the workload (`Handle.kill()` is out of this task's scope);
    `handle.wait()` blocks until the launcher's exit-waiter has reaped it
    (task-073). When `jail_dir` is given, also remove it -- a bound socket
    file outlives the process that bound it, so process teardown alone would
    leave one behind for the readiness tests below."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)
    if jail_dir is not None:
        shutil.rmtree(jail_dir, ignore_errors=True)


def _bind_script(endpoint: str, *, delay: float) -> str:
    """A single-line `python3 -c` invocation. Sleeps `delay` seconds, then
    binds+listens on `endpoint` and sleeps long enough to outlive every
    test that spawns it."""
    code = (
        f"import socket,time;time.sleep({delay});"
        "s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM);"
        f's.bind("{endpoint}");s.listen(1);time.sleep(30)'
    )
    return f"python3 -c '{code}'"


# ---------------------------------------------------------------------------
# AC #1 -- Handle.exec, called as a bound method.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_handle_exec_pwd_writes_the_jail_cwd_through_the_bound_method(run_id: str) -> None:
    """`handle.exec(["pwd"])` -- the BOUND method, never the private
    function it delegates to -- runs a sibling in the jail's own `cwd`.
    Same literal claim MILESTONES.md M2 EC4 makes; this is the one place in
    the suite that reaches it through `Handle.exec` itself."""
    cwd_dir = _new_cwd_dir()
    jail_dir = _new_jail_dir()
    handle = _launch(
        workload_argv(run_id, "sleep 5"),
        cwd=cwd_dir,
        jail_dir=jail_dir,
    )
    try:
        exec_handle = handle.exec(["pwd"])
        assert exec_handle.wait(timeout=5.0) == 0
        with open(exec_handle.stdout_path) as f:
            content = f.read().strip()
        assert os.path.realpath(content) == os.path.realpath(handle.cwd)
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_handle_exec_forwards_the_interactive_keyword_through_the_bound_method(
    run_id: str,
) -> None:
    """decision-053 names TWO failure shapes for a wrong delegation: wrong
    argument order (task-030 AC #3's mutation) AND a DROPPED keyword. This
    test is what would catch the second shape, which a swapped-positional
    mutation does not exercise: `handle.exec([...], interactive=True)` --
    the BOUND method -- must refuse, naming `PTY` on the structured
    `missing` field (same posture as `test_exec.py`'s AC #8), which only
    holds if `Handle.exec` actually forwards `interactive` through to its
    delegate. A dropped `interactive` keyword would silently fall back to
    the delegate's own default (`False`) and let this spawn a live process
    instead of refusing. Control, same bound method, `interactive=False`
    succeeds -- both invocations reached only through `Handle.exec`."""
    cwd_dir = _new_cwd_dir()
    jail_dir = _new_jail_dir()
    handle = _launch(
        workload_argv(run_id, "sleep 5"),
        cwd=cwd_dir,
        jail_dir=jail_dir,
    )
    try:
        with pytest.raises(ValueError) as exc_info:
            handle.exec(["true"], interactive=True)
        assert type(exc_info.value).__name__ == "ExecRefused"
        refusal = cast(_NamedExecRefusal, exc_info.value)
        assert LaunchFeature.PTY in refusal.missing

        # Control: the same bound method, interactive=False, succeeds.
        exec_handle = handle.exec(["true"], interactive=False)
        assert exec_handle.wait(timeout=5.0) == 0
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #2 / AC #5 -- Handle.wait_ready, called as a bound method: positive
# control (the bind DOES appear) and the negative (it never does).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_handle_wait_ready_returns_after_a_real_bind_appears_through_the_bound_method(
    run_id: str,
) -> None:
    """Positive control (AC #5): a workload that sleeps ~0.5s and then
    binds+listens on the declared endpoint makes `handle.wait_ready` --
    the BOUND method -- RETURN, with elapsed time consistent with having
    actually waited for the bind rather than an instant false positive.
    Without this case, the timeout test below could pass for a probe that
    never worked at all -- 'always raises' is not evidence of a working
    timeout unless something in the same suite proves the non-timeout path
    genuinely returns."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint)
    spec = Spec(channels=(channel,))
    argv = workload_argv(run_id, _bind_script(endpoint, delay=0.5))
    handle = _launch(argv, cwd=jail_dir, jail_dir=jail_dir, spec=spec)
    try:
        start = time.monotonic()
        handle.wait_ready("ctl", timeout=10.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.5, f"returned before the bind could have appeared: elapsed={elapsed}"
        assert elapsed < 5.0, f"returned suspiciously close to the 10s timeout: elapsed={elapsed}"
    finally:
        _teardown_group(handle, jail_dir)


@pytest.mark.integration
def test_handle_wait_ready_raises_the_named_timeout_type_through_the_bound_method(
    run_id: str,
) -> None:
    """Negative half: a workload that never binds makes `handle.wait_ready`
    -- the BOUND method -- raise the named timeout type, carrying the
    channel, endpoint and timeout as structured fields, within the expected
    window (not premature, not silently swallowed past the deadline). The
    exact class is checked by name rather than by importing it, so this
    file never has a reason to import the module `Handle.wait_ready`
    delegates to."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint)
    spec = Spec(channels=(channel,))
    argv = workload_argv(run_id, "sleep 30")  # never touches the endpoint
    handle = _launch(argv, cwd=jail_dir, jail_dir=jail_dir, spec=spec)
    try:
        start = time.monotonic()
        with pytest.raises(TimeoutError) as exc_info:
            handle.wait_ready("ctl", timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0, f"raised before the deadline: elapsed={elapsed}"
        assert elapsed < 3.0, f"raised long after the deadline, not promptly: elapsed={elapsed}"
        assert type(exc_info.value).__name__ == "WaitReadyTimeout"
        err = cast(_NamedTimeout, exc_info.value)
        assert err.channel == "ctl"
        assert err.endpoint == endpoint
        assert err.timeout == 1.0
    finally:
        _teardown_group(handle, jail_dir)
