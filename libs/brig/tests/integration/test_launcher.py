"""`SubprocessLauncher` against a real OS process, and the complete M2
`Handle` shape it returns.

Every test tears its own workload down directly (`os.killpg`/`os.kill` +
reap). Teardown here is deliberately hand-rolled rather than `Handle.kill()`:
a test's cleanup path must not be the code under test, so a teardown bug
cannot hide behind its own helper. `kill_jail` has been functional since
task-020; this is a choice, not a gap. Workloads that are meant to be caught by the
suite-wide leak-check if teardown ever escapes are built through
`tests.conftest.workload_argv`, which stamps the run's token into the
FIRST line of the spawned script (see that function's docstring for why
that placement, not appended after the body, is load-bearing). Jail
directories use a short `/tmp/bg<pid>-<n>` scratch root, never `tmp_path`
(CLAUDE.md: `sun_path` is 104 bytes on darwin -- task-021 will bind a
socket inside a jail directory built the same way this file builds one, so
this file establishes that convention rather than special-casing around
it).

Leak-check note: this whole file runs in well under a second, so
`tests/conftest.py`'s background poller (`_POLL_INTERVAL_S = 0.05`) gets
only a handful of samples and may never record a launched workload's pgid
into `seen_pgids` before that workload is torn down. What actually proves
this file clean is the OTHER arm -- `_sweep_for_leaks`'s direct
`run_id in row[2]` match at session teardown, which is exactly the
realistic leak this file's own teardown could produce (a surviving
`bash -c` leader still carrying the token in its own argv). The
transitive, token-less-descendant arm the poller exists for is real but
not what a green run of this fast a file demonstrates.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import signal
import subprocess

import pytest

from brig.core import (
    AXES,
    Channel,
    ChannelKind,
    EnforcementReport,
    EventKind,
    Grade,
    Spec,
    unenforced_report,
)
from brig.mech import EventPayload, EventSource, ExitOutcome, LaunchFeature, StagedFile
from brig.run import exec_ as exec_mod
from brig.run import readiness as readiness_mod

# Aliased `teardown_mod`, not `teardown_module`: pytest's xunit-style
# module-teardown hook is looked up by that exact name on this test module,
# and would try (and fail) to call the imported `brig.run.teardown` module
# as if it were that hook.
from brig.run import teardown as teardown_mod
from brig.run._exit_status import WorkloadSpawnFailed
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, LaunchRefused, SubprocessLauncher
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>-<n>` -- never `tmp_path`."""
    return f"/tmp/bg{os.getpid()}-{next(_jail_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


class _FixedSensor:
    """A pure `EventSource` whose `known_at_compile` returns one payload
    the launcher must stamp, and whose `classify_exit` says nothing. Its
    whole job is to be something for AC #7 to observe reaching
    `Handle.compile_events`."""

    def __init__(self, marker: str) -> None:
        self._marker = marker

    def known_at_compile(self) -> tuple[EventPayload, ...]:
        return (EventPayload(kind=EventKind.SPAWN, data={"marker": self._marker}),)

    def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
        del outcome
        return None


def _compiled_jail(
    *,
    requires: frozenset[LaunchFeature] = frozenset(),
    spec: Spec | None = None,
    report: EnforcementReport | None = None,
    staged: tuple[StagedFile, ...] = (),
    sensors: tuple[EventSource, ...] = (),
) -> CompiledJail:
    """A minimal, mechanism-free `CompiledJail`: the empty stack's shape
    (SPEC.md §3: "the empty stack ... grades every axis unenforced") by
    default, with `requires`/`spec`/`report`/`staged` overridable -- most
    tests in this file take every default, which is exactly why one test
    (`test_launch_writes_staged_files_and_handle_round_trips_channels_and_detail`)
    deliberately does not: an empty-stack `Spec` has no channels and
    `unenforced_report()`'s `detail` is `""` on every axis, so leaving
    every test at the defaults would make `Handle`'s `channels`/`detail`
    round-trip and `_write_staged_files` pass vacuously."""
    return CompiledJail(
        spec=spec if spec is not None else Spec(),
        report=report if report is not None else unenforced_report(),
        wrap=_identity_wrap,
        env={},
        staged=staged,
        helpers=(),
        requires=requires,
        mechanism_names=(),
        matrix_version=1,
        sensors=sensors,
    )


def _launch(
    argv: list[str],
    *,
    cwd: str,
    jail: CompiledJail | None = None,
    jail_id: str = "jail-under-test",
    jail_dir: str | None = None,
    io: IoPolicy | None = None,
) -> Handle:
    launcher = SubprocessLauncher()
    return launcher.launch(
        jail if jail is not None else _compiled_jail(),
        argv=argv,
        cwd=cwd,
        io=io if io is not None else IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir if jail_dir is not None else _new_jail_dir(),
    )


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


def _children_of(pid: int) -> list[int]:
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,ppid="], capture_output=True, text=True, check=True
    )
    children: list[int] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and int(parts[1]) == pid:
            children.append(int(parts[0]))
    return children


def _teardown_group(handle: Handle) -> None:
    """Group-kill a workload launched WITH `start_new_session`. The kill is
    deliberately hand-rolled (`killpg`) rather than `kill_jail`: a test's
    cleanup path must not be the code under test, so a teardown bug cannot
    hide behind its own helper. `kill_jail` has been functional since
    task-020; this is a choice, not a gap. `handle.wait()` blocks until the
    launcher's exit-waiter has reaped it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _kill_shared_pgid_workload(pid: int) -> None:
    """Tear down a workload spawned WITHOUT `start_new_session` (it shares
    THIS process's own pgid). Never `killpg` here -- that would signal the
    test runner itself. Kill the leader and any children it forked
    individually instead."""
    children = _children_of(pid)
    for child_pid in children:
        with contextlib.suppress(ProcessLookupError):
            os.kill(child_pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


# ---------------------------------------------------------------------------
# AC #2 / #3 -- detachment, observed against a control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_detached_workload_leads_its_own_process_group(run_id: str) -> None:
    """AC #2: the child's real pgid, read from `/bin/ps`, equals the
    child's own pid (it leads its own group) and differs from the pytest
    harness's own pgid, read the same way."""
    jail_dir = _new_jail_dir()
    argv = workload_argv(run_id, "sleep 5")
    handle = _launch(argv, cwd=jail_dir, jail_dir=jail_dir)
    try:
        child_pgid = _ps_pgid(handle.pid)
        harness_pgid = _ps_pgid(os.getpid())
        assert child_pgid == handle.pid
        assert child_pgid != harness_pgid
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_control_workload_without_new_session_shares_pytest_pgid(run_id: str) -> None:
    """AC #3: the control. The SAME workload shape, spawned by a test-local
    `Popen` WITHOUT `start_new_session`, shares this process's own pgid --
    proof the previous test's "differs from the pytest pgid" assertion is
    discriminating, not a tautology true of any freshly-minted pid."""
    argv = workload_argv(run_id, "sleep 5")
    harness_pgid = _ps_pgid(os.getpid())
    proc = subprocess.Popen(argv, cwd="/tmp")
    try:
        child_pgid = _ps_pgid(proc.pid)
        assert child_pgid == harness_pgid
    finally:
        _kill_shared_pgid_workload(proc.pid)
        proc.wait(timeout=5.0)


# ---------------------------------------------------------------------------
# AC #4 -- stdio to files, exact content.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stdio_lands_in_exactly_the_files_the_handle_names(run_id: str) -> None:
    """AC #4: a known token on stdout, a different (non-overlapping) token
    on stderr -- exact content in each file, not substring containment."""
    out_token = "STDOUT-TOKEN-4f9c2a"
    err_token = "STDERR-TOKEN-7b31de"
    body = f"( printf '%s' '{out_token}'; printf '%s' '{err_token}' 1>&2 )"
    argv = workload_argv(run_id, body)
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail_dir=jail_dir)
    try:
        handle.wait(timeout=20.0)
        with open(handle.stdout_path) as f:
            stdout_content = f.read()
        with open(handle.stderr_path) as f:
            stderr_content = f.read()
        assert stdout_content == out_token
        assert stderr_content == err_token
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #5 / #6 -- capability refusal, and its control.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_launch_refuses_a_jail_that_requires_pty(run_id: str) -> None:
    """AC #5: `requires` including `PTY` (which `SubprocessLauncher` does
    NOT claim) raises, and the structured `missing` field -- not
    `str(exc)` -- names `PTY`. No process is spawned."""
    jail = _compiled_jail(requires=frozenset({LaunchFeature.PTY}))
    jail_dir = _new_jail_dir()
    launcher = SubprocessLauncher()
    with pytest.raises(LaunchRefused) as exc_info:
        launcher.launch(
            jail,
            argv=workload_argv(run_id, "true"),
            cwd=jail_dir,
            io=IoPolicy(),
            jail_id="jail-refused",
            jail_dir=jail_dir,
        )
    assert LaunchFeature.PTY in exc_info.value.missing
    # Nothing was ever spawned or created for a refused jail.
    assert not os.path.exists(jail_dir)


@pytest.mark.integration
def test_launch_refusal_control_new_process_group_is_within_capabilities(run_id: str) -> None:
    """AC #6: the control. A `CompiledJail` requiring only
    `NEW_PROCESS_GROUP` (which IS in `SubprocessLauncher.capabilities`)
    launches successfully -- without this, the refusal test above cannot
    distinguish "requires exceeded capabilities" from "launch always
    refuses"."""
    jail = _compiled_jail(requires=frozenset({LaunchFeature.NEW_PROCESS_GROUP}))
    argv = workload_argv(run_id, "true")
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail=jail, jail_dir=jail_dir)
    try:
        handle.wait(timeout=20.0)
        assert handle.pid > 0
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #7 -- the launcher is the call site for `known_at_compile`.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_known_at_compile_payloads_are_stamped_onto_the_handle(run_id: str) -> None:
    """AC #7. This AC used to read the first line of the jail's events file
    and assert it decoded to a `SPAWN` record carrying the wrapped argv,
    pid, pgid and cwd. decision-152 (2026-09-08) deleted that file, and the
    facts it carried are all on the `Handle` itself and always were -- a
    record restating them was a second copy, not a second source.

    What replaces it is the thing the launcher does that nothing else can:
    it is `run`'s call site for `EventSource.known_at_compile()`, stamping
    `ts` and `jail_id` -- the two fields SPEC.md section 6 reserves to
    `run` -- onto every payload and handing the result back on
    `Handle.compile_events`. CONTROL: a jail with no sensors gets the
    empty tuple, so this cannot pass by stamping something unconditionally.
    """
    argv = workload_argv(run_id, "true")
    jail_dir = _new_jail_dir()
    jail = _compiled_jail(sensors=(_FixedSensor("sensor-a"), _FixedSensor("sensor-b")))
    handle = _launch(argv, cwd=jail_dir, jail=jail, jail_id="jail-sensor-evt", jail_dir=jail_dir)
    try:
        handle.wait(timeout=20.0)
        assert [e.kind for e in handle.compile_events] == [EventKind.SPAWN, EventKind.SPAWN]
        assert [e.data["marker"] for e in handle.compile_events] == ["sensor-a", "sensor-b"]
        assert {e.jail_id for e in handle.compile_events} == {"jail-sensor-evt"}
        assert all(e.ts > 0 for e in handle.compile_events)

        # They survive the round trip a rehydrating process makes.
        assert Handle.from_dict(handle.to_dict()).compile_events == handle.compile_events
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_a_jail_with_no_sensors_stamps_nothing(run_id: str) -> None:
    """AC #7's control: the empty stack has no `EventSource` at all, so
    `compile_events` is empty -- the stamping above is a consequence of the
    sensors, not of launching."""
    argv = workload_argv(run_id, "true")
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail_id="jail-no-sensor", jail_dir=jail_dir)
    try:
        handle.wait(timeout=20.0)
        assert handle.compile_events == ()
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #8 -- to_dict / from_dict round trip, in-process.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_handle_round_trips_in_process_and_refuses_an_extra_key(run_id: str) -> None:
    """AC #8: `from_dict(handle.to_dict())` equals the original field for
    field; `from_dict` on a dict carrying an unknown key raises. (The
    separate-process proof is task-023's, not claimed here.)"""
    argv = workload_argv(run_id, "sleep 5")
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail_dir=jail_dir)
    try:
        d = handle.to_dict()
        rehydrated = Handle.from_dict(d)
        assert rehydrated == handle

        bad = dict(d)
        bad["bogus_extra_key"] = "unexpected"
        with pytest.raises(ValueError):
            Handle.from_dict(bad)
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_launch_writes_staged_files_and_handle_round_trips_channels_and_detail(
    run_id: str,
) -> None:
    """Non-vacuity closer for the empty-stack defaults every other test in
    this file uses: an empty-stack `Spec` has no channels and
    `unenforced_report()`'s `detail` is `""` on every axis, so AC #8's
    round-trip above never actually exercises `Channel` construction, the
    `ChannelKind` enum lookup, a non-empty `detail`, or the unknown-key
    refusal inside channel decoding -- `{} == {}` and `"" == ""` would
    still pass with `_channels_from_list` completely broken. This test
    gives the jail one real channel and a named `detail`, and separately
    proves `_write_staged_files` (Deliverable step 2) actually lands a
    staged file with its content and mode, which no other test in this
    file exercises either (all use `staged=()`)."""
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint="ctl.sock")
    spec = Spec(channels=(channel,))
    report = unenforced_report("m2: no mechanisms enforce anything yet")
    staged = (StagedFile(relpath="profile.txt", content="staged-content-xyz", mode=0o640),)
    jail = _compiled_jail(spec=spec, report=report, staged=staged)

    argv = workload_argv(run_id, "true")
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail=jail, jail_dir=jail_dir)
    try:
        handle.wait(timeout=20.0)

        # Deliverable step 2: the staged file actually landed, with its
        # content and mode -- not merely reachable code.
        staged_path = os.path.join(jail_dir, "profile.txt")
        with open(staged_path) as f:
            assert f.read() == "staged-content-xyz"
        assert os.stat(staged_path).st_mode & 0o777 == 0o640

        # The channel and the non-empty detail are on the live handle...
        assert handle.channels["ctl"] == channel
        assert all(
            graded.detail == "m2: no mechanisms enforce anything yet"
            for graded in handle.report.axes.values()
        )

        # ...and survive the to_dict/from_dict round trip.
        d = handle.to_dict()
        rehydrated = Handle.from_dict(d)
        assert rehydrated == handle
        assert rehydrated.channels["ctl"] == channel
        assert rehydrated.channels["ctl"].kind is ChannelKind.LISTEN
        assert rehydrated.channels["ctl"].endpoint == "ctl.sock"

        # The unknown-key refusal inside channel decoding actually fires
        # (dead code in AC #8's test above, which never has a channel).
        bad = dict(d)
        bad["channels"] = [{**d["channels"][0], "bogus": "unexpected"}]
        with pytest.raises(ValueError):
            Handle.from_dict(bad)

        # Same refusal, inside a `report` per-axis entry: an unknown key
        # nested inside one axis's dict (as opposed to an unknown top-level
        # key, which AC #8's test above already covers) must also raise --
        # SPEC.md §5's "an unknown key at any level is a refusal", applied
        # to the one nesting level `_report_from_dict` did not check.
        bad_report = dict(d)
        bad_report["report"] = dict(d["report"])
        bad_report["report"]["fs_read"] = {
            **d["report"]["fs_read"],
            "bogus_axis_key": "unexpected",
        }
        with pytest.raises(ValueError):
            Handle.from_dict(bad_report)
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #9 -- alive() is both-valued.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_alive_is_true_while_running_false_after_kill_and_reap(run_id: str) -> None:
    """AC #9: `alive()` is true while the workload runs, and false after
    the test kills its group and reaps it."""
    argv = workload_argv(run_id, "sleep 5")
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail_dir=jail_dir)
    try:
        assert handle.alive() is True
    finally:
        _teardown_group(handle)
    assert handle.alive() is False


# ---------------------------------------------------------------------------
# AC #10 -- stat().
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stat_returns_the_pid_and_a_report_matching_the_compiled_jail(run_id: str) -> None:
    """AC #10: `stat().pids` names the workload pid; `stat().report`
    matches the `CompiledJail`'s report exactly, all seven axes
    `UNENFORCED`."""
    jail = _compiled_jail()
    argv = workload_argv(run_id, "sleep 5")
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail=jail, jail_dir=jail_dir)
    try:
        stat = handle.stat()
        assert handle.pid in stat.pids
        assert stat.report == jail.report
        for axis in AXES:
            assert stat.report.axes[axis].grade is Grade.UNENFORCED
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #10 (task-027) -- decision-041's positive replacement for the retired
# task-019 AC #11 (a pin on three seams that used to raise a stub error
# naming the task that would fill them in): the three seams task-020,
# task-021 and task-022 filled are FUNCTIONAL, asserted against a real
# handle, not against a stub's raise.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_filled_seams_are_functional_not_stubs(run_id: str) -> None:
    """task-027 AC #10, decision-041's authorized positive replacement for
    task-019's retired AC #11 pin -- task-020, task-021 and task-022 have
    since filled the three seams that pin only ever proved were raising
    stubs:

    - `exec_in_jail` returns an `ExecHandle` whose `wait()` is `0` for a
      command that exits `0`.
    - `wait_ready` raises its OWN named timeout type (`WaitReadyTimeout`)
      for a channel that never binds -- asserted on the type, and never
      the retired stub's error or a stand-in subclass of it (see the
      comment at the assertion below for how both are excluded).
    - `kill_jail` returns a `KillReport` whose workload item outcome is
      `ENDED`.
    """
    never_binds = Channel(
        name="never-binds",
        kind=ChannelKind.LISTEN,
        endpoint=f"/tmp/bg{os.getpid()}-ac10-nobind.sock",
    )
    jail = _compiled_jail(spec=Spec(channels=(never_binds,)))
    argv = workload_argv(run_id, "sleep 5")
    jail_dir = _new_jail_dir()
    handle = _launch(argv, cwd=jail_dir, jail=jail, jail_dir=jail_dir)
    try:
        # exec_in_jail: functional, not a raising stub.
        exec_handle = exec_mod.exec_in_jail(handle, ["true"])
        assert exec_handle.wait(timeout=5.0) == 0

        # wait_ready: raises its OWN named timeout type. `pytest.raises`
        # here only catches `WaitReadyTimeout` and its subclasses, so a
        # raise of the retired stub's (unrelated-hierarchy) error type
        # would propagate past this block and ERROR the test rather than
        # pass it -- that is the whole discharge of "not the stub's
        # error". The identity check (not `isinstance`) then excludes a
        # stand-in subclass too.
        with pytest.raises(readiness_mod.WaitReadyTimeout) as exc_info:
            readiness_mod.wait_ready(handle, "never-binds", 0.2)
        assert exc_info.type is readiness_mod.WaitReadyTimeout

        # kill_jail: functional, not a raising stub.
        report = teardown_mod.kill_jail(handle)
        assert report.items[0].kind == "workload_group"
        assert report.items[0].outcome is teardown_mod.KillOutcome.ENDED
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# decision-156 -- a workload that cannot be spawned is still a LAUNCH failure.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_workload_that_cannot_be_exec_d_fails_the_launch(run_id: str) -> None:
    """The exit wrapper spawns the jail's argv as its own child, which moves
    the `exec` failure out of this process -- so the launcher reads a ready
    token back through a pipe and turns "the wrapper could not spawn it" into
    a refusal HERE, where it was before.

    Without that, `launch()` would return a `Handle` for a jail that was
    already dead and the mistake would surface later and somewhere else, as a
    readiness timeout naming a channel that was never the problem.

    THE CONTROL, in the same test: the identical call with a real argv
    returns a handle, so the refusal is attributable to the missing binary
    rather than to launch being broken.
    """
    jail_dir = _new_jail_dir()
    missing = os.path.join(jail_dir, "no-such-binary")
    assert not os.path.exists(missing)

    with pytest.raises(WorkloadSpawnFailed) as exc_info:
        _launch([missing], cwd=jail_dir, jail_dir=jail_dir)
    assert missing in str(exc_info.value), str(exc_info.value)

    handle = _launch(workload_argv(run_id, "true"), cwd=jail_dir, jail_dir=jail_dir)
    try:
        assert handle.wait(timeout=20.0) == 0
    finally:
        _teardown_group(handle)
