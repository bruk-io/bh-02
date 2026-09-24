"""`Step.helpers` actually start, and actually die with the jail.

`Helper` and `HelperLifetime` have been in the mechanism contract since M2
and `CompiledJail.helpers` has been carried through the stack the whole
time -- with nothing ever reading it. `grep -c helpers brig/run/launcher.py`
returned 0 until task-081. That is this codebase's named recurring defect
(CLAUDE.md: "declared but never called"), and M6's `connect_proxy` is the
first mechanism that needs the field to mean something, so it gets proven
here before a proxy is built on top of it.

Every claim in this file is observed from the OS -- a pid's liveness read
through `/bin/kill -0`, a file the helper itself wrote -- never from the
launcher's own bookkeeping. `handle.helper_pids` is what is being GRADED
here; it cannot also be the evidence that the helper ran.

Helpers are spawned with the run token in their argv (`workload_argv`) so
that a helper this file fails to reap is caught by the suite-wide leak
sweep rather than silently outliving the session -- which for M6's real
helper would be a listening socket nobody owns.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import subprocess
import time

import pytest

from brig.core import Spec, unenforced_report
from brig.mech import Helper, HelperLifetime, LaunchFeature
from brig.run import _identity as identity
from brig.run import launcher as launcher_mod
from brig.run import teardown as teardown_mod
from brig.run.handle import Handle
from brig.run.launcher import HelperFailed, IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail
from tests.conftest import workload_argv

pytestmark = pytest.mark.integration

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bh<pid>-<n>` -- never `tmp_path`."""
    return f"/tmp/bh{os.getpid()}-{next(_jail_counter)}"


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
        requires=frozenset[LaunchFeature](),
        mechanism_names=(),
        matrix_version=1,
    )


def _alive(pid: int) -> bool:
    """Liveness read from the OS, not from a Popen this process holds.

    `/bin/kill` by absolute path, never the shell builtin or an alias
    (decision-026). A zombie answers 0 here, which is exactly the
    distinction this file needs to be careful about -- see
    `test_kill_jail_reaps_a_jail_lifetime_helper`, which asserts on
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


def _launch(jail: CompiledJail, run_id: str, jail_dir: str) -> Handle:
    return SubprocessLauncher().launch(
        jail,
        argv=workload_argv(run_id, "sleep 30"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-helpers",
        jail_dir=jail_dir,
    )


def test_jail_lifetime_helper_runs_and_kill_jail_reaps_it(run_id: str) -> None:
    """A JAIL_LIFETIME helper is a live process while the jail lives, and
    is gone after `kill_jail` -- both observed from the OS.

    THE CONTROL is the first half of this test, not a separate one: the
    helper is proven ALIVE (and proven to have executed, by the file it
    wrote) before the kill. Without that, "not alive after kill" would pass
    just as well against a helper that never started -- the vacuous form
    SPEC.md §12 names, and the exact shape the `helpers` field was in
    before this test existed.
    """
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)
    beacon = os.path.join(jail_dir, "helper-ran")

    helper = Helper(
        name="beacon",
        argv=tuple(workload_argv(run_id, f"touch {beacon}; sleep 30")),
        lifetime=HelperLifetime.JAIL_LIFETIME,
    )
    handle = _launch(_jail((helper,)), run_id, jail_dir)
    try:
        assert len(handle.helper_pids) == 1, (
            f"launcher recorded no pid for a JAIL_LIFETIME helper: {handle.helper_pids!r}"
        )
        helper_pid = handle.helper_pids[0]
        # decision-155: a helper is torn down by pid, possibly from a process
        # that never started it, so its pid is recorded WITH the moment that
        # process began -- one stamp per pid, matching what the OS says about
        # this helper right now. A recycled number therefore reads as gone
        # rather than as this helper.
        assert len(handle.helper_stamps) == len(handle.helper_pids)
        assert handle.helper_stamps[0] == identity.start_stamp(helper_pid) != identity.UNKNOWN

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

        # Its own process group: `kill_jail` kills the group, so a helper
        # sharing the launcher's group would take the test runner with it.
        assert os.getpgid(helper_pid) == helper_pid, (
            f"helper {helper_pid} did not get its own process group "
            f"(pgid={os.getpgid(helper_pid)}) -- killpg on it would hit the harness"
        )

        report = teardown_mod.kill_jail(handle)
    finally:
        # Belt and braces: if an assertion above fired before kill_jail ran,
        # do not leak the helper into the suite-wide sweep.
        for pid in handle.helper_pids:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, 9)

    helper_items = [item for item in report.items if item.kind == "helper"]
    assert len(helper_items) == 1, (
        f"kill report has no `helper` item; kinds={[i.kind for i in report.items]!r}"
    )
    assert helper_items[0].identity == str(helper_pid)

    assert _wait_until(lambda: _ps_state(helper_pid) in ("", "Z")), (
        f"helper {helper_pid} survived kill_jail (ps state {_ps_state(helper_pid)!r}) -- "
        "a helper that outlives its jail is the leak this whole field exists to prevent"
    )


def test_launch_scoped_helper_completes_before_the_workload_starts(run_id: str) -> None:
    """LAUNCH_SCOPED means "gone before the workload runs" (SPEC.md §6) --
    a guarantee, so it is asserted on ORDERING, not merely on "it ran".

    The workload reads the file the helper wrote. If the helper were
    started concurrently instead of run to completion, this races and
    fails; if it were skipped entirely, it fails outright.
    """
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)
    prepared = os.path.join(jail_dir, "prepared")
    observed = os.path.join(jail_dir, "workload-saw-it")

    helper = Helper(
        name="prep",
        argv=("/bin/sh", "-c", f"printf ready > {prepared}"),
        lifetime=HelperLifetime.LAUNCH_SCOPED,
    )
    handle = SubprocessLauncher().launch(
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
        assert handle.helper_pids == (), (
            "a LAUNCH_SCOPED helper must not be recorded as a persistent pid: "
            f"{handle.helper_pids!r}"
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
        teardown_mod.kill_jail(handle)


def test_failed_launch_scoped_helper_refuses_the_launch(run_id: str) -> None:
    """A preparation step that failed must not be followed by a workload
    assuming it succeeded.

    THE CONTROL: the identical jail with the helper exiting 0 launches
    fine (the test above). Here the only change is the exit status, so a
    green cannot come from the jail being unlaunchable for some other
    reason.
    """
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)
    marker = os.path.join(jail_dir, "workload-started")

    helper = Helper(
        name="doomed",
        argv=("/bin/sh", "-c", "echo 'no listener available' >&2; exit 3"),
        lifetime=HelperLifetime.LAUNCH_SCOPED,
    )
    with pytest.raises(HelperFailed) as exc_info:
        SubprocessLauncher().launch(
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
    run_id: str, monkeypatch: pytest.MonkeyPatch
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
    monkeypatch.setattr(launcher_mod, "_LAUNCH_SCOPED_TIMEOUT_S", 1.0)
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)
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
