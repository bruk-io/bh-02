"""`Jail.start`, `Jail.channel` and `Process.wait_ready`, exercised as BOUND methods.

`Jail.wait_ready(channel)` was the second subject here until decision-186
(TASK-0079.32) deleted it with the path a channel declared; its two tests now
drive readiness where it went, `jail.channel` then `process.wait_ready`, and
assert what they did.

task-030 / decision-053, on doc-007 §6 D-7's finding: SPEC.md §9's `exec`
criterion (MILESTONES.md M2 EC4) reads `handle.exec(["pwd"])` -- a sibling
`jail.start(["pwd"])` since decision-183 -- and `Jail.wait_ready`'s signature
is likewise part of that same public block, but each is a short delegate (to
the jail's supervisor, and to `readiness.wait_ready`). decision-053, quoted:
"**a public surface is not discharged one hop away.** A test that reaches
past the method an embedder calls, into the function that method delegates
to, proves the delegate's callee and not the delegate."

This file exists to close exactly that gap, and only that gap -- it does not
replace or duplicate the module-function coverage `test_exec.py` and
`test_wait_ready.py` already carry; it adds the one thing they structurally
cannot prove, which is that the bound method wires its arguments to its
delegate correctly. Nothing here imports the delegate-callee functions or
their private module paths at all, by construction.

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
from brig.run import HostRuntime, IoPolicy, Jail, Process
from brig.stack import CompiledJail
from tests.conftest import launch, teardown_group, workload_argv

_counter = itertools.count()


class _NamedTimeout(Protocol):
    """The structured-field shape of the timeout `Jail.wait_ready` is
    expected to raise, reproduced locally as a `Protocol` so this file can
    type-check the caught exception's fields under `mypy --strict` without
    importing the concrete exception class -- the same reason this module
    checks the exception's class *name* rather than its identity (see the
    module docstring)."""

    channel: str
    endpoint: str
    timeout: float


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
) -> tuple[Jail, Process]:
    return launch(_compiled_jail(spec=spec), argv, cwd=cwd, jail_id=jail_id, jail_dir=jail_dir)


def _launch_on_a_reserved_socket(
    body: str, *, run_id: str, jail_dir: str, spec: Spec
) -> tuple[Jail, Process, str]:
    """A jail whose one process is started on a socket `jail.channel("ctl")`
    reserved; `body` is a format string given the socket's path as `{path}`.
    Returns the reservation's endpoint too."""
    os.makedirs(jail_dir, exist_ok=True)
    jail = Jail.create(
        _compiled_jail(spec=spec),
        runtime=HostRuntime(),
        cwd=jail_dir,
        jail_id="jail-under-test",
        jail_dir=jail_dir,
    )
    reservation = jail.channel("ctl")
    try:
        process = jail.start(
            workload_argv(run_id, body.format(path=reservation.bound_path)),
            cwd=jail_dir,
            io=IoPolicy(),
            channel=reservation,
        )
    except BaseException:
        jail.destroy()
        raise
    return jail, process, reservation.endpoint


def _teardown_group(process: Process, jail_dir: str | None = None) -> None:
    """Group-kill the workload (`Jail.destroy()` is out of this task's scope);
    `process.wait()` blocks until the exit waiter has reaped it
    (task-073). When `jail_dir` is given, also remove it -- a bound socket
    file outlives the process that bound it, so process teardown alone would
    leave one behind for the readiness tests below."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(process)
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
# AC #1 -- Jail.start, called as a bound method.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_jail_start_pwd_writes_the_jail_cwd_through_the_bound_method(run_id: str) -> None:
    """`jail.start(["pwd"])` -- the BOUND method, never the private
    function it delegates to -- runs a sibling in the jail's own `cwd`.
    Same literal claim MILESTONES.md M2 EC4 makes; this is the one place in
    the suite that reaches it through `Jail.start` itself."""
    cwd_dir = _new_cwd_dir()
    jail_dir = _new_jail_dir()
    jail, process = _launch(
        workload_argv(run_id, "sleep 5"),
        cwd=cwd_dir,
        jail_dir=jail_dir,
    )
    try:
        sibling = jail.start(["pwd"])
        assert sibling.wait(timeout=5.0) == 0
        with open(sibling.stdout_path) as f:
            content = f.read().strip()
        assert os.path.realpath(content) == os.path.realpath(cwd_dir)
    finally:
        _teardown_group(process)


@pytest.mark.integration
def test_jail_start_forwards_the_cwd_keyword_through_the_bound_method(run_id: str) -> None:
    """decision-053 names TWO failure shapes for a wrong delegation: wrong
    argument order (task-030 AC #3's mutation) AND a DROPPED keyword. This
    test is what would catch the second shape: `jail.start(["pwd"],
    cwd=other)` -- the BOUND method -- must run in `other`, which only holds
    if `Jail.start` actually forwards `cwd` to its supervisor. A dropped
    keyword would silently fall back to the jail's own cwd. Control, same
    bound method, no `cwd`: the sibling runs in the jail's cwd -- both
    invocations reached only through `Jail.start`.

    Until decision-183 this test forwarded `interactive=True` through
    `exec`, which could only refuse for want of `PTY`; that keyword went
    with it, and `cwd` is the keyword `start` forwards now."""
    cwd_dir = _new_cwd_dir()
    other_dir = _new_cwd_dir()
    jail_dir = _new_jail_dir()
    jail, process = _launch(
        workload_argv(run_id, "sleep 5"),
        cwd=cwd_dir,
        jail_dir=jail_dir,
    )
    try:
        moved = jail.start(["pwd"], cwd=other_dir)
        assert moved.wait(timeout=5.0) == 0
        with open(moved.stdout_path) as f:
            assert os.path.realpath(f.read().strip()) == os.path.realpath(other_dir)

        # Control: the same bound method, no cwd, runs in the jail's own.
        stayed = jail.start(["pwd"])
        assert stayed.wait(timeout=5.0) == 0
        with open(stayed.stdout_path) as f:
            assert os.path.realpath(f.read().strip()) == os.path.realpath(cwd_dir)
    finally:
        _teardown_group(process)


# ---------------------------------------------------------------------------
# AC #2 / AC #5 -- readiness, called as bound methods (`jail.channel`, then
# `process.wait_ready`, since decision-186): positive control (the bind DOES
# appear) and the negative (it never does).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_handle_wait_ready_returns_after_a_real_bind_appears_through_the_bound_method(
    run_id: str,
) -> None:
    """Positive control (AC #5): a workload that sleeps ~0.5s and then
    binds+listens on its reserved socket makes `process.wait_ready` --
    the BOUND method -- RETURN, with elapsed time consistent with having
    actually waited for the bind rather than an instant false positive.
    Without this case, the timeout test below could pass for a probe that
    never worked at all -- 'always raises' is not evidence of a working
    timeout unless something in the same suite proves the non-timeout path
    genuinely returns."""
    jail_dir = _new_jail_dir()
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN)
    spec = Spec(channels=(channel,))
    _jail, process, _ = _launch_on_a_reserved_socket(
        _bind_script("{path}", delay=0.5), run_id=run_id, jail_dir=jail_dir, spec=spec
    )
    try:
        start = time.monotonic()
        process.wait_ready(timeout=10.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.5, f"returned before the bind could have appeared: elapsed={elapsed}"
        assert elapsed < 5.0, f"returned suspiciously close to the 10s timeout: elapsed={elapsed}"
    finally:
        _teardown_group(process, jail_dir)


@pytest.mark.integration
def test_handle_wait_ready_raises_the_named_timeout_type_through_the_bound_method(
    run_id: str,
) -> None:
    """Negative half: a workload that never binds makes `process.wait_ready`
    -- the BOUND method -- raise the named timeout type, carrying the
    channel, endpoint and timeout as structured fields, within the expected
    window (not premature, not silently swallowed past the deadline). The
    exact class is checked by name rather than by importing it, so this
    file never has a reason to import the module `Process.wait_ready`
    delegates to."""
    jail_dir = _new_jail_dir()
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN)
    spec = Spec(channels=(channel,))
    # never touches its socket
    _jail, process, endpoint = _launch_on_a_reserved_socket(
        "sleep 30", run_id=run_id, jail_dir=jail_dir, spec=spec
    )
    try:
        start = time.monotonic()
        with pytest.raises(TimeoutError) as exc_info:
            process.wait_ready(timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0, f"raised before the deadline: elapsed={elapsed}"
        assert elapsed < 3.0, f"raised long after the deadline, not promptly: elapsed={elapsed}"
        assert type(exc_info.value).__name__ == "WaitReadyTimeout"
        err = cast(_NamedTimeout, exc_info.value)
        assert err.channel == "ctl"
        assert err.endpoint == endpoint
        assert err.timeout == 1.0
    finally:
        _teardown_group(process, jail_dir)
