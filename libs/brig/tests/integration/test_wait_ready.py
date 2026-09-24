"""`wait_ready` against a real Unix-socket bind, a real timeout, and a real
stale-socket control.

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
  `/tmp/bg<pid>wr<n>` scratch root, never pytest's `tmp_path` (AC #5 pins the
  arithmetic that makes this a hard exclusion, not a style preference).
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

import itertools
import os
import pathlib
import shutil
import socket
import sys
import time

import pytest

from brig.core import Channel, ChannelKind, Spec, unenforced_report
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.run.readiness import UnknownChannel, WaitReadyTimeout, wait_ready
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>wr<n>` -- never `tmp_path`
    (CLAUDE.md: `sun_path` is 104 bytes on darwin; see
    `test_endpoint_fits_sun_path_and_a_tmp_path_endpoint_would_not` for why
    that is a hard exclusion here, not a preference)."""
    return f"/tmp/bg{os.getpid()}wr{next(_jail_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail(*, spec: Spec) -> CompiledJail:
    """A minimal, mechanism-free `CompiledJail` carrying the given `Spec`
    (which is where the declared channels live) -- same empty-stack shape
    `test_launcher.py` uses, with only `spec` ever varied in this file."""
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


def _launch(argv: list[str], *, jail_dir: str, spec: Spec) -> Handle:
    launcher = SubprocessLauncher()
    return launcher.launch(
        _compiled_jail(spec=spec),
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-wait-ready",
        jail_dir=jail_dir,
    )


def _teardown(handle: Handle, jail_dir: str) -> None:
    """Group-kill the workload, then remove the whole jail directory -- AC
    #9's "no socket file survives" requires deleting the file itself, not
    merely ending the process that created it. The kill is deliberately
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
    shutil.rmtree(jail_dir, ignore_errors=True)


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
def test_wait_ready_returns_after_a_real_bind_appears(run_id: str) -> None:
    """AC #2: a workload that sleeps ~0.5s and then binds+listens on the
    declared endpoint makes `wait_ready(timeout=10)` RETURN -- elapsed is at
    least the sleep (it actually waited for the bind, not an instant false
    positive) and well under the timeout (it noticed promptly, not merely
    eventually)."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint)
    spec = Spec(channels=(channel,))
    argv = workload_argv(run_id, _bind_script(endpoint, delay=0.5))
    handle = _launch(argv, jail_dir=jail_dir, spec=spec)
    try:
        start = time.monotonic()
        wait_ready(handle, "ctl", timeout=10.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.5, f"returned before the bind could have appeared: elapsed={elapsed}"
        assert elapsed < 5.0, f"returned suspiciously close to the 10s timeout: elapsed={elapsed}"
    finally:
        _teardown(handle, jail_dir)


# ---------------------------------------------------------------------------
# AC #3 -- negative: times out cleanly when the bind never appears.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_wait_ready_times_out_cleanly_when_the_bind_never_appears(run_id: str) -> None:
    """AC #3: a workload that never binds makes `wait_ready(timeout=1.0)`
    raise `WaitReadyTimeout` carrying the channel name, the endpoint, and
    1.0 as structured fields (not just a message). Elapsed is at least 1.0
    (it wasn't a premature give-up) and under 3.0 (clean means promptly)."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint)
    spec = Spec(channels=(channel,))
    argv = workload_argv(run_id, "sleep 30")  # never touches the endpoint
    handle = _launch(argv, jail_dir=jail_dir, spec=spec)
    try:
        start = time.monotonic()
        with pytest.raises(WaitReadyTimeout) as exc_info:
            wait_ready(handle, "ctl", timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0, f"raised before the deadline: elapsed={elapsed}"
        assert elapsed < 3.0, f"raised long after the deadline, not promptly: elapsed={elapsed}"
        assert exc_info.value.channel == "ctl"
        assert exc_info.value.endpoint == endpoint
        assert exc_info.value.timeout == 1.0
    finally:
        _teardown(handle, jail_dir)


# ---------------------------------------------------------------------------
# AC #4 -- the discriminating control: a stale socket FILE still times out.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stale_socket_file_still_times_out(run_id: str) -> None:
    """AC #4, the discriminating one. A socket FILE exists at the endpoint
    (bound, then closed WITHOUT unlinking -- exactly what a dead process
    leaves behind), but nothing is listening behind it. `wait_ready` must
    still time out. This is what distinguishes a connect-based readiness
    probe from an `os.path.exists` one: without this control, the positive
    test above would also pass for an implementation that only stats the
    path -- a stat sees this stale file too."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint)
    spec = Spec(channels=(channel,))
    argv = workload_argv(run_id, "sleep 30")  # never touches the endpoint either
    handle = _launch(argv, jail_dir=jail_dir, spec=spec)
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
            wait_ready(handle, "ctl", timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0, (
            f"a path-exists implementation would return here instantly: elapsed={elapsed}"
        )
        assert elapsed < 3.0
    finally:
        _teardown(handle, jail_dir)


# ---------------------------------------------------------------------------
# AC #5 -- sun_path pin.
# ---------------------------------------------------------------------------


#: `sun_path`'s capacity, per platform: 104 bytes on darwin, 108 on linux.
#: A number the C header fixes, so it is written down per platform rather
#: than measured -- and the darwin figure is the smaller of the two, which
#: is why this suite's scratch roots are sized for it everywhere.
_SUN_PATH_MAX = {"darwin": 104}.get(sys.platform, 108)


@pytest.mark.integration
def test_endpoint_fits_sun_path() -> None:
    """AC #5, the half that holds on every platform: this suite's actual
    scratch-root endpoint fits `sun_path` with room to spare."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
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
def test_tmp_resolves_to_private_tmp_before_path_comparison(run_id: str) -> None:
    """AC #6: darwin symlinks `/tmp` -> `/private/tmp`, so the OS itself
    reports a spawned child's cwd with the `/private/tmp` spelling even
    though this file always builds `jail_dir` with the `/tmp` prefix. Every
    assertion in this file that compares two independently-obtained path
    spellings resolves both sides with `os.path.realpath` first -- this
    test is the one that would actually catch a missing resolution, by
    reading the child's own `os.getcwd()` back and comparing it against
    `os.path.realpath(jail_dir)`."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
    cwd_file = os.path.join(jail_dir, "cwd.txt")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint)
    spec = Spec(channels=(channel,))
    argv = workload_argv(run_id, _bind_and_record_cwd_script(endpoint, cwd_file))
    handle = _launch(argv, jail_dir=jail_dir, spec=spec)
    try:
        wait_ready(handle, "ctl", timeout=5.0)
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
        _teardown(handle, jail_dir)


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
def test_wait_ready_on_unknown_channel_name_raises_and_names_it(run_id: str) -> None:
    """AC #8: an unknown channel name raises `UnknownChannel`, naming it as
    a structured field. Control: the declared name does not raise."""
    jail_dir = _new_jail_dir()
    endpoint = os.path.join(jail_dir, "ctl.sock")
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint)
    spec = Spec(channels=(channel,))
    argv = workload_argv(run_id, _bind_script(endpoint, delay=0.0))
    handle = _launch(argv, jail_dir=jail_dir, spec=spec)
    try:
        with pytest.raises(UnknownChannel) as exc_info:
            wait_ready(handle, "does-not-exist", timeout=1.0)
        assert exc_info.value.channel == "does-not-exist"

        # Control: the declared name does not raise.
        wait_ready(handle, "ctl", timeout=5.0)
    finally:
        _teardown(handle, jail_dir)
