"""`Step.helpers` actually start, and actually die with the jail.

`Helper` and `HelperLifetime` have been in the mechanism contract since M2
and `CompiledJail.helpers` has been carried through the stack the whole
time -- with nothing ever reading it. `grep -c helpers brig/run/host.py`
returned 0 until task-081. That is this codebase's named recurring defect
(CLAUDE.md: "declared but never called"), and M6's `connect_proxy` is the
first mechanism that needs the field to mean something, so it gets proven
here before a proxy is built on top of it.

Every claim in this file is observed from the OS -- a pid's liveness read
through `/bin/kill -0`, a file the helper itself wrote -- never from the
launcher's own bookkeeping. `jail._base.helper_pids` is what is being GRADED
here; it cannot also be the evidence that the helper ran.

Helpers are spawned with the run token in their argv (`workload_argv`) so
that a helper this file fails to reap is caught by the suite-wide leak
sweep rather than silently outliving the session -- which for M6's real
helper would be a listening socket nobody owns.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time

import pytest

from brig.core import Spec, unenforced_report
from brig.core.runtime import Capability
from brig.mech import Helper, HelperLifetime
from brig.run import HelperFailed, HostRuntime, IoPolicy, Jail, Process
from brig.run import _identity as identity
from brig.run import host as host_mod
from brig.stack import CompiledJail
from tests.conftest import launch, workload_argv

pytestmark = pytest.mark.integration


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _jail(helpers: tuple[Helper, ...]) -> CompiledJail:
    return CompiledJail(
        spec=Spec(),
        report=unenforced_report(),
        wrap=_identity_wrap,
        env={},
        staged=(),
        helpers=helpers,
        requires=frozenset[Capability](),
        mechanism_names=(),
        matrix_version=1,
    )


def _alive(pid: int) -> bool:
    """Liveness read from the OS, not from a Popen this process holds.

    `/bin/kill` by absolute path, never the shell builtin or an alias
    (decision-026). A zombie answers 0 here, which is exactly the
    distinction this file needs to be careful about -- see
    `test_jail_lifetime_helper_runs_and_destroy_reaps_it`, which asserts on
    `/bin/ps` state, not on this, for the post-kill claim.
    """
    return subprocess.run(["/bin/kill", "-0", str(pid)], capture_output=True).returncode == 0


def _ps_state(pid: int) -> str:
    """`/bin/ps` state letter for `pid`, or "" if it is gone entirely."""
    done = subprocess.run(
        ["/bin/ps", "-o", "state=", "-p", str(pid)], capture_output=True, text=True
    )
    return done.stdout.strip()


def _read(path: str) -> str:
    """`path`'s contents, or `""` while it is absent -- the two states a
    file a workload is about to write can be in."""
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return ""


def _wait_until(predicate, timeout: float = 5.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _launch(jail: CompiledJail, run_id: str, jail_dir: str) -> tuple[Jail, Process]:
    return launch(
        jail,
        argv=workload_argv(run_id, "sleep 30"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-helpers",
        jail_dir=jail_dir,
    )


def test_jail_lifetime_helper_runs_and_destroy_reaps_it(run_id: str, jail_dir: str) -> None:
    """A JAIL_LIFETIME helper is a live process while the jail lives, and
    is gone after `Jail.destroy` -- both observed from the OS.

    THE CONTROL is the first half of this test, not a separate one: the
    helper is proven ALIVE (and proven to have executed, by the file it
    wrote) before the kill. Without that, "not alive after kill" would pass
    just as well against a helper that never started -- the vacuous form
    SPEC.md §12 names, and the exact shape the `helpers` field was in
    before this test existed.
    """
    beacon = os.path.join(jail_dir, "helper-ran")

    helper = Helper(
        name="beacon",
        argv=tuple(workload_argv(run_id, f"touch {beacon}; sleep 30")),
        lifetime=HelperLifetime.JAIL_LIFETIME,
    )
    jail, process = _launch(_jail((helper,)), run_id, jail_dir)
    try:
        assert len(jail._base.helper_pids) == 1, (
            f"launcher recorded no pid for a JAIL_LIFETIME helper: {jail._base.helper_pids!r}"
        )
        helper_pid = jail._base.helper_pids[0]
        # decision-155: a helper is torn down by pid, possibly from a process
        # that never started it, so its pid is recorded WITH the moment that
        # process began -- one stamp per pid, matching what the OS says about
        # this helper right now. A recycled number therefore reads as gone
        # rather than as this helper.
        assert len(jail._base.helper_stamps) == len(jail._base.helper_pids)
        assert jail._base.helper_stamps[0] == identity.start_stamp(helper_pid) != identity.UNKNOWN

        # It RAN: the helper's own side effect, not our bookkeeping.
        assert _wait_until(lambda: os.path.exists(beacon)), (
            f"helper process {helper_pid} never wrote {beacon} -- it was recorded but not started"
        )
        # It is STILL RUNNING: a LAUNCH_SCOPED-style run-to-completion would
        # fail here, which is what makes the two lifetimes distinguishable.
        assert _alive(helper_pid), f"JAIL_LIFETIME helper {helper_pid} exited before the workload"
        assert _ps_state(helper_pid) not in ("", "Z"), (
            f"helper {helper_pid} is a zombie or gone while the jail is still up"
        )

        # Its own process group: `Jail.destroy` kills the group, so a helper
        # sharing the launcher's group would take the test runner with it.
        assert os.getpgid(helper_pid) == helper_pid, (
            f"helper {helper_pid} did not get its own process group "
            f"(pgid={os.getpgid(helper_pid)}) -- killpg on it would hit the harness"
        )

        report = jail.destroy()
    finally:
        # Belt and braces: if an assertion above fired before destroy ran,
        # do not leak the helper into the suite-wide sweep.
        for pid in jail._base.helper_pids:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, 9)

    helper_items = [item for item in report.items if item.kind == "helper"]
    assert len(helper_items) == 1, (
        f"kill report has no `helper` item; kinds={[i.kind for i in report.items]!r}"
    )
    assert helper_items[0].identity == str(helper_pid)

    assert _wait_until(lambda: _ps_state(helper_pid) in ("", "Z")), (
        f"helper {helper_pid} survived destroy (ps state {_ps_state(helper_pid)!r}) -- "
        "a helper that outlives its jail is the leak this whole field exists to prevent"
    )


def test_launch_scoped_helper_completes_before_the_workload_starts(
    run_id: str, jail_dir: str
) -> None:
    """LAUNCH_SCOPED means "gone before the workload runs" (SPEC.md §6) --
    a guarantee, so it is asserted on ORDERING, not merely on "it ran".

    The workload reads the file the helper wrote. If the helper were
    started concurrently instead of run to completion, this races and
    fails; if it were skipped entirely, it fails outright.
    """
    prepared = os.path.join(jail_dir, "prepared")
    observed = os.path.join(jail_dir, "workload-saw-it")

    helper = Helper(
        name="prep",
        argv=("/bin/sh", "-c", f"printf ready > {prepared}"),
        lifetime=HelperLifetime.LAUNCH_SCOPED,
    )
    jail, process = launch(
        _jail((helper,)),
        # The workload copies the prepared file the instant it starts. Any
        # ordering violation shows up as a missing or empty `observed`.
        argv=workload_argv(run_id, f"cat {prepared} > {observed} 2>/dev/null; sleep 30"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-helpers-scoped",
        jail_dir=jail_dir,
    )
    try:
        assert jail._base.helper_pids == (), (
            "a LAUNCH_SCOPED helper must not be recorded as a persistent pid: "
            f"{jail._base.helper_pids!r}"
        )
        # The wait is for CONTENT, never for existence: `> observed` is a
        # shell redirect, so the file appears the instant the workload's
        # `cat` starts and is empty until it succeeds. A reader that
        # returned at existence would read `""` under any scheduling delay
        # and report an ordering violation that did not happen.
        assert _wait_until(lambda: _read(observed) != ""), (
            "the workload never wrote anything: either it never ran, or its "
            "LAUNCH_SCOPED helper had not prepared the file it copies"
        )
        assert _read(observed) == "ready", (
            "the workload started before its LAUNCH_SCOPED helper finished preparing"
        )
    finally:
        jail.destroy()


def test_failed_launch_scoped_helper_refuses_the_launch(run_id: str, jail_dir: str) -> None:
    """A preparation step that failed must not be followed by a workload
    assuming it succeeded.

    THE CONTROL: the identical jail with the helper exiting 0 launches
    fine (the test above). Here the only change is the exit status, so a
    green cannot come from the jail being unlaunchable for some other
    reason.
    """
    marker = os.path.join(jail_dir, "workload-started")

    helper = Helper(
        name="doomed",
        argv=("/bin/sh", "-c", "echo 'no listener available' >&2; exit 3"),
        lifetime=HelperLifetime.LAUNCH_SCOPED,
    )
    with pytest.raises(HelperFailed) as exc_info:
        launch(
            _jail((helper,)),
            argv=workload_argv(run_id, f"touch {marker}; sleep 30"),
            cwd=jail_dir,
            io=IoPolicy(),
            jail_id="jail-helpers-doomed",
            jail_dir=jail_dir,
        )

    assert exc_info.value.helper_name == "doomed"
    assert exc_info.value.returncode == 3
    assert "no listener available" in exc_info.value.stderr

    # And the workload genuinely never ran -- the point of refusing.
    time.sleep(0.2)
    assert not os.path.exists(marker), "the workload was started behind a failed preparation step"


def test_a_launch_scoped_helper_that_never_exits_fails_instead_of_hanging(
    run_id: str, monkeypatch: pytest.MonkeyPatch, jail_dir: str
) -> None:
    """Found by a mutation check, not by design review.

    Flipping `connect_proxy`'s proxy from JAIL_LIFETIME to LAUNCH_SCOPED
    (a plausible one-word mistake in a new mechanism) wedged the launcher
    permanently: `LAUNCH_SCOPED` runs to completion, the proxy runs
    forever, and the unbounded wait produced no error, no workload, and no
    output of any kind. A hang is the worst failure shape available -- it
    looks like slowness, and slowness looks like the machine.

    The timeout is monkeypatched down so this test costs a second rather
    than the real ceiling. That is the ONE thing faked here; the helper
    really does run forever, the launcher really does hit the bound, and
    the workload really is never started.
    """
    monkeypatch.setattr(host_mod, "_LAUNCH_SCOPED_TIMEOUT_S", 1.0)
    marker = os.path.join(jail_dir, "workload-started")

    helper = Helper(
        name="forever",
        argv=tuple(workload_argv(run_id, "sleep 300")),
        lifetime=HelperLifetime.LAUNCH_SCOPED,
    )
    started = time.monotonic()
    with pytest.raises(HelperFailed) as exc_info:
        _launch(_jail((helper,)), run_id, jail_dir)
    elapsed = time.monotonic() - started

    assert elapsed < 30, (
        f"the launcher took {elapsed:.1f}s to give up on a helper that never "
        "exits -- the bound is not being applied"
    )
    assert exc_info.value.helper_name == "forever"
    assert "JAIL_LIFETIME" in exc_info.value.stderr, (
        f"the failure does not tell the mechanism author what to change: {exc_info.value.stderr!r}"
    )
    assert not os.path.exists(marker), "the workload ran anyway"


def _ready_probe(ready: str, saw: str) -> str:
    """The shell a helper runs: write what it finds at its own ready path the instant
    it starts (`present` or `absent`) to `saw`, then publish the ready file, as a
    helper does once it is ready."""
    return (
        f"if [ -e {ready} ]; then printf present > {saw}; else printf absent > {saw}; fi; "
        f"printf published > {ready}"
    )


@pytest.mark.parametrize(
    "lifetime", [HelperLifetime.JAIL_LIFETIME, HelperLifetime.LAUNCH_SCOPED], ids=lambda e: e.name
)
def test_a_ready_file_an_earlier_jail_left_is_gone_before_the_helper_starts(
    run_id: str, lifetime: HelperLifetime, jail_dir: str
) -> None:
    """TASK-0150, decision-204: the jail directory is reused, so the file a helper
    publishes when it is ready can already be there, an earlier jail's, and whatever
    waits for it would read it as this one's. `create` removes the declared
    `ready_path` before it starts the helper.

    Observed from the helper's side, in its own process, at its own start: the file
    was `absent` when it looked. THE CONTROLS: the file was planted and was there
    when `create` was called (so `absent` is the removal's doing, not an empty
    directory's); a neighbour the helper does not declare survives (the removal is
    one file, not the directory); and the file the helper then publishes is there at
    the end, so the removal does not stand in the way of the thing it protects."""
    ready = os.path.join(jail_dir, "helper.ready")
    neighbour = os.path.join(jail_dir, "neighbour")
    saw = os.path.join(jail_dir, "saw")
    for path, text in ((ready, "stale"), (neighbour, "kept")):
        with open(path, "w") as fh:
            fh.write(text)
    assert _read(ready) == "stale", "the stale ready file was not planted"

    probe = _ready_probe(ready, saw)
    helper = Helper(
        name="publisher",
        # The leak sweep finds a helper by the run token in its argv; a LAUNCH_SCOPED one is
        # gone before the workload starts and needs none.
        argv=(
            ("/bin/sh", "-c", probe)
            if lifetime is HelperLifetime.LAUNCH_SCOPED
            else tuple(workload_argv(run_id, f"{{ {probe}; sleep 30; }}"))
        ),
        lifetime=lifetime,
        ready_path=ready,
    )
    jail, _process = _launch(_jail((helper,)), run_id, jail_dir)
    try:
        assert _wait_until(lambda: _read(ready) == "published"), (
            f"the helper never published its ready file; it found {_read(saw)!r} at its start"
        )
        assert _read(saw) == "absent", (
            "the helper started with an earlier jail's ready file still in place, "
            f"so a reader would have taken it for this launch's: it found {_read(saw)!r}"
        )
        assert _read(neighbour) == "kept", "the removal took a file the helper did not declare"
    finally:
        jail.destroy()


def test_a_ready_file_that_cannot_be_removed_refuses_the_create_before_any_helper_starts(
    run_id: str,
    jail_dir: str,
) -> None:
    """A declared ready file that is there and cannot be removed (here a directory)
    is an `OSError` from `create` with a note saying what to do, and NO helper has
    started, the one declared before the stubborn one included: the failure that
    matters is a file that might still be read, and a half-started jail is the
    caller's to find and end.

    THE CONTROL, in the same test: with the directory gone, the same helpers start
    and the first one runs, so the refusal was the directory's and not a jail that
    could not start for another reason."""
    ready = os.path.join(jail_dir, "helper.ready")
    ran = os.path.join(jail_dir, "first-ran")
    os.mkdir(ready)

    first = Helper(
        name="first",
        argv=tuple(workload_argv(run_id, f"touch {ran}; sleep 30")),
        lifetime=HelperLifetime.JAIL_LIFETIME,
    )
    second = Helper(
        name="second",
        argv=tuple(workload_argv(run_id, "sleep 30")),
        lifetime=HelperLifetime.JAIL_LIFETIME,
        ready_path=ready,
    )
    with pytest.raises(OSError) as refused:
        Jail.create(
            _jail((first, second)),
            runtime=HostRuntime(),
            cwd=jail_dir,
            jail_id="jail-ready-stuck",
            jail_dir=jail_dir,
        )
    assert any("remove it, or choose another jail directory" in n for n in refused.value.__notes__)
    time.sleep(0.5)
    assert not os.path.exists(ran), "a helper started although the create was refused"

    os.rmdir(ready)
    jail = Jail.create(
        _jail((first, second)),
        runtime=HostRuntime(),
        cwd=jail_dir,
        jail_id="jail-ready-stuck",
        jail_dir=jail_dir,
    )
    try:
        assert _wait_until(lambda: os.path.exists(ran)), (
            "the control jail did not start its first helper either"
        )
    finally:
        jail.destroy()
