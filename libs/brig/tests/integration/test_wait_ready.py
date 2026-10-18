"""`Process.wait_ready` against a real Unix-socket bind, a real timeout, and a
real stale-socket control.

Until decision-186 (TASK-0079.32) these drove `Jail.wait_ready(channel)` over
a path the `Spec` declared; that is gone with the path. They now drive the
process's own readiness, through the runtime's dial, on a socket the jail
reserved in its channel directory, and assert what they did: the same
timings, the same stale-socket control, the same refusal of an unknown name.

SPEC.md §10.1 (folded by decision-036, ambiguity A5, verbatim): "Observable
means a connect succeeds -- not that the endpoint path exists... Readiness
connects and closes; path-existence is never readiness." AC #4's
stale-socket control is what this file exists to prove: an implementation
that merely `os.path.exists()`d the endpoint would pass the positive test
(AC #2) AND the plain timeout test (AC #3, since no file ever appears there
at all) -- it would only be caught out by a socket FILE that exists with
nothing listening behind it, which is exactly what AC #4 manufactures (bind,
then close without unlinking -- a dead process's leftover, reproduced on
purpose).

This is the ONLY M2 integration file that binds a Unix socket, so both
environment traps CLAUDE.md and this task name are live here and nowhere
else in the tier:

- `sun_path` is 104 bytes on darwin. Every endpoint here lives under a short
  scratch root from `tests/conftest.py`'s `jail_dir`, never pytest's
  `tmp_path` (AC #5 pins the arithmetic that makes this a hard exclusion, not
  a style preference).
- `/tmp` is a symlink to `/private/tmp` on darwin. `os.path.realpath` is
  applied before any assertion that compares two independently-obtained
  spellings of the same path (AC #6).

Every workload is spawned through `tests.conftest.workload_argv` so the
suite-wide leak-check (task-013) can find it without cooperation, and every
test removes its own jail directory in `finally` -- process teardown alone
does not satisfy AC #9's "no socket file survives the run", since a socket
file outlives the process that bound it (the same fact SPEC.md's readiness
definition itself turns on).
"""

from __future__ import annotations

import os
import pathlib
import socket
import sys
import time
from collections.abc import Callable

import pytest

from brig.core import Channel, ChannelKind, Spec, unenforced_report
from brig.run import (
    HostRuntime,
    IoPolicy,
    Jail,
    Process,
    Reservation,
    UnknownChannel,
    WaitReadyTimeout,
)
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail(*, spec: Spec) -> CompiledJail:
    """A minimal, mechanism-free `CompiledJail` carrying the given `Spec`
    (which is where the declared channels live) -- same empty-stack shape
    `test_jail_launch.py` uses, with only `spec` ever varied in this file."""
    return CompiledJail(
        spec=spec,
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
    argv_for: Callable[[str], list[str]], *, jail_dir: str, spec: Spec
) -> tuple[Jail, Process, Reservation]:
    """A jail whose first process is started on a socket reserved for `ctl`:
    `argv_for` gets the path it binds (decision-184)."""
    jail = Jail.create(
        _compiled_jail(spec=spec),
        runtime=HostRuntime(),
        cwd=jail_dir,
        jail_id="jail-wait-ready",
        jail_dir=jail_dir,
    )
    reservation = jail.channel("ctl")
    try:
        process = jail.start(
            argv_for(reservation.bound_path), cwd=jail_dir, io=IoPolicy(), channel=reservation
        )
    except BaseException:
        jail.destroy()
        raise
    return jail, process, reservation


def _teardown(process: Process) -> None:
    """Group-kill the workload. (AC #9's "no socket file survives" needs the
    file itself deleted, not merely the process that created it ended: the
    test's `jail_dir` is removed after it.) The kill is deliberately
    hand-rolled (`killpg`) rather than `Jail.destroy`: a test's cleanup path
    must not be the code under test, so a teardown bug cannot hide behind its
    own helper. `Jail.destroy` has been functional since task-020; this is a
    choice, not a gap. `process.wait()` blocks until the launcher's exit-waiter
    has reaped it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(process)


def _bind_script(endpoint: str, *, delay: float) -> str:
    """A single-line `python3 -c` invocation -- no embedded newlines, since
    `workload_argv` appends `&` to whatever this returns, and a multi-line
    body would background only its last line. Optionally sleeps `delay`
    seconds, then binds+listens on `endpoint` and sleeps long enough to
    outlive every test that spawns it."""
    code = (
        f"import socket,time;time.sleep({delay});"
        "s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM);"
        f's.bind("{endpoint}");s.listen(1);time.sleep(30)'
    )
    return f"python3 -c '{code}'"


def _bind_and_record_cwd_script(endpoint: str, cwd_file: str) -> str:
    """Like `_bind_script` (immediate bind), but the child also writes its
    own `os.getcwd()` to `cwd_file` first -- used by AC #6 to show what the
    OS itself reports for a cwd spelled with the `/tmp` prefix."""
    code = (
        "import socket,os;"
        f'open("{cwd_file}","w").write(os.getcwd());'
        "s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM);"
        f's.bind("{endpoint}");s.listen(1);'
        "import time;time.sleep(30)"
    )
    return f"python3 -c '{code}'"


# ---------------------------------------------------------------------------
# AC #2 -- positive: returns after a real bind appears.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_wait_ready_returns_after_a_real_bind_appears(run_id: str, jail_dir: str) -> None:
    """AC #2: a workload that sleeps ~0.5s and then binds+listens on the
    declared endpoint makes `wait_ready(timeout=10)` RETURN -- elapsed is at
    least the sleep (it actually waited for the bind, not an instant false
    positive) and well under the timeout (it noticed promptly, not merely
    eventually)."""
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN)
    spec = Spec(channels=(channel,))
    jail, process, _ = _launch(
        lambda path: workload_argv(run_id, _bind_script(path, delay=0.5)),
        jail_dir=jail_dir,
        spec=spec,
    )
    try:
        start = time.monotonic()
        process.wait_ready(timeout=10.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.5, f"returned before the bind could have appeared: elapsed={elapsed}"
        assert elapsed < 5.0, f"returned suspiciously close to the 10s timeout: elapsed={elapsed}"
    finally:
        _teardown(process)


# ---------------------------------------------------------------------------
# AC #3 -- negative: times out cleanly when the bind never appears.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_wait_ready_times_out_cleanly_when_the_bind_never_appears(
    run_id: str, jail_dir: str
) -> None:
    """AC #3: a workload that never binds makes `wait_ready(timeout=1.0)`
    raise `WaitReadyTimeout` carrying the channel name, the endpoint, and
    1.0 as structured fields (not just a message). Elapsed is at least 1.0
    (it wasn't a premature give-up) and under 3.0 (clean means promptly)."""
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN)
    spec = Spec(channels=(channel,))
    # never touches its socket
    jail, process, reservation = _launch(
        lambda _path: workload_argv(run_id, "sleep 30"), jail_dir=jail_dir, spec=spec
    )
    try:
        start = time.monotonic()
        with pytest.raises(WaitReadyTimeout) as exc_info:
            process.wait_ready(timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0, f"raised before the deadline: elapsed={elapsed}"
        assert elapsed < 3.0, f"raised long after the deadline, not promptly: elapsed={elapsed}"
        assert exc_info.value.channel == "ctl"
        assert exc_info.value.endpoint == reservation.endpoint
        assert exc_info.value.timeout == 1.0
    finally:
        _teardown(process)


# ---------------------------------------------------------------------------
# AC #4 -- the discriminating control: a stale socket FILE still times out.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stale_socket_file_still_times_out(run_id: str, jail_dir: str) -> None:
    """AC #4, the discriminating one. A socket FILE exists at the endpoint
    (bound, then closed WITHOUT unlinking -- exactly what a dead process
    leaves behind), but nothing is listening behind it. `wait_ready` must
    still time out. This is what distinguishes a connect-based readiness
    probe from an `os.path.exists` one: without this control, the positive
    test above would also pass for an implementation that only stats the
    path -- a stat sees this stale file too."""
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN)
    spec = Spec(channels=(channel,))
    # never touches its socket either
    jail, process, reservation = _launch(
        lambda _path: workload_argv(run_id, "sleep 30"), jail_dir=jail_dir, spec=spec
    )
    endpoint = reservation.endpoint
    try:
        # The stale socket file: bind, then close without unlinking, then
        # confirm the workload above (which never binds) hasn't raced us.
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(endpoint)
        stale.close()
        assert os.path.exists(endpoint), (
            "the stale file must actually exist -- an os.path.exists-based "
            "wait_ready would read this as ready, which is the wrong reading "
            "this test exists to catch"
        )

        start = time.monotonic()
        with pytest.raises(WaitReadyTimeout):
            process.wait_ready(timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0, (
            f"a path-exists implementation would return here instantly: elapsed={elapsed}"
        )
        assert elapsed < 3.0
    finally:
        _teardown(process)


# ---------------------------------------------------------------------------
# AC #5 -- sun_path pin.
# ---------------------------------------------------------------------------


#: `sun_path`'s capacity, per platform: 104 bytes on darwin, 108 on linux.
#: A number the C header fixes, so it is written down per platform rather
#: than measured -- and the darwin figure is the smaller of the two, which
#: is why this suite's scratch roots are sized for it everywhere.
_SUN_PATH_MAX = {"darwin": 104}.get(sys.platform, 108)


@pytest.mark.integration
def test_endpoint_fits_sun_path(jail_dir: str) -> None:
    """AC #5, the half that holds on every platform: this suite's actual
    scratch-root endpoint fits `sun_path` with room to spare: a reserved
    socket, `<jail_dir>/chan/<16 hex>.sock` (decision-184), the longest name
    the runtime makes there."""
    endpoint = os.path.join(jail_dir, "chan", f"{'0' * 16}.sock")
    real_len = len(os.fsencode(endpoint))
    print(f"AC#5: scratch-root endpoint = {endpoint!r}, byte length = {real_len}")
    assert real_len < _SUN_PATH_MAX


@pytest.mark.integration
@pytest.mark.skipif(
    sys.platform != "darwin",
    reason=(
        "the tmp_path-overflow claim is darwin's: darwin puts tmp_path under "
        "/private/var/folders/<two long opaque segments>/ and caps sun_path at "
        "104 bytes, while linux roots it at /tmp/pytest-of-<user> and allows "
        "108 -- where a tmp_path endpoint fits, and this measurement would "
        "prove nothing"
    ),
)
def test_a_tmp_path_endpoint_would_overflow_sun_path_on_darwin(
    tmp_path: pathlib.Path,
) -> None:
    """AC #5, the half that is a fact about darwin: a hypothetical pytest
    `tmp_path`-based endpoint would NOT have fit, which is why every jail
    dir in this suite is a short scratch root instead. `tmp_path` is used
    here ONLY to measure a would-be string length -- nothing is ever bound
    at it, per CLAUDE.md's exclusion.

    This was one test with the one above until the suite was first run on
    linux (2026-09-08), where the assertion failed for a reason that was
    not a defect: the exclusion is still right there, just not for THIS
    reason. Splitting it keeps the platform-independent half running
    everywhere and makes the darwin half skip by name rather than fail."""
    hypothetical = os.path.join(str(tmp_path), "jail-wait-ready", "ctl.sock")
    hypothetical_len = len(os.fsencode(hypothetical))

    print(f"AC#5: tmp_path-based endpoint = {hypothetical!r}, byte length = {hypothetical_len}")
    assert hypothetical_len >= _SUN_PATH_MAX, (
        "expected the tmp_path-based endpoint to overflow sun_path -- if this "
        "ever fails, tmp_path has gotten shorter and the exclusion should be "
        "re-examined, not silently kept"
    )


# ---------------------------------------------------------------------------
# AC #6 -- /tmp vs /private/tmp resolution.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_tmp_resolves_to_private_tmp_before_path_comparison(run_id: str, jail_dir: str) -> None:
    """AC #6: darwin symlinks `/tmp` -> `/private/tmp`, so the OS itself
    reports a spawned child's cwd with the `/private/tmp` spelling even
    though this file always builds `jail_dir` with the `/tmp` prefix. Every
    assertion in this file that compares two independently-obtained path
    spellings resolves both sides with `os.path.realpath` first -- this
    test is the one that would actually catch a missing resolution, by
    reading the child's own `os.getcwd()` back and comparing it against
    `os.path.realpath(jail_dir)`."""
    cwd_file = os.path.join(jail_dir, "cwd.txt")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN)
    spec = Spec(channels=(channel,))
    jail, process, _ = _launch(
        lambda path: workload_argv(run_id, _bind_and_record_cwd_script(path, cwd_file)),
        jail_dir=jail_dir,
        spec=spec,
    )
    try:
        process.wait_ready(timeout=5.0)
        with open(cwd_file) as f:
            child_reported_cwd = f.read()

        resolved_jail_dir = os.path.realpath(jail_dir)  # the resolution call
        assert child_reported_cwd == resolved_jail_dir
        if child_reported_cwd != jail_dir:
            print(
                f"AC#6: unresolved jail_dir {jail_dir!r} != child-reported cwd "
                f"{child_reported_cwd!r} -- os.path.realpath() reconciles them"
            )
    finally:
        _teardown(process)


# ---------------------------------------------------------------------------
# AC #7 -- MAILBOX rejection, and its control. DELETED by decision-153
# (2026-09-08) along with `ChannelKind.MAILBOX` and `NotAListenChannel`
# itself: `LISTEN` is the only kind there is, so there is no wrong-kind
# channel left to reject and no branch left to prove immediate.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AC #8 -- unknown channel name, and its control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_wait_ready_on_unknown_channel_name_raises_and_names_it(run_id: str, jail_dir: str) -> None:
    """AC #8: an unknown channel name raises `UnknownChannel`, naming it as
    a structured field. Control: the declared name does not raise."""
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN)
    spec = Spec(channels=(channel,))
    jail, process, _ = _launch(
        lambda path: workload_argv(run_id, _bind_script(path, delay=0.0)),
        jail_dir=jail_dir,
        spec=spec,
    )
    try:
        with pytest.raises(UnknownChannel) as exc_info:
            jail.channel("does-not-exist")
        assert exc_info.value.channel == "does-not-exist"

        # Control: the declared name does not raise, and its process is ready.
        jail.channel("ctl")
        process.wait_ready(timeout=5.0)
    finally:
        _teardown(process)
