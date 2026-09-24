"""MILESTONES.md M4 EC1, executed literally against a real `degraded()`
jail (task-053), verbatim:

    1. Against `degraded()`: env and cpu probes PASS, fs/network probes
       report honestly (FAIL where genuinely unenforced -- a FAIL against
       an `unenforced` grade is *consistent*, not a contradiction).

Every REAL jail this file launches is built through the REAL `degraded()`
preset (or `Stack([])` for the discriminating controls), the REAL
`SubprocessLauncher`, and `handle.probe` -- no monkeypatching of
enforcement, same "observe from inside the jail" posture
`tests/integration/test_probe_runner.py` and `test_env_scrub.py` already
established. Every long-lived JAIL WORKLOAD (`sleep 100`) is built through
`tests.conftest.workload_argv` so the suite's leak sweep catches anything a
test's own teardown misses; the probes themselves are `wait()`-ed on
synchronously by `run_battery` before this file's own assertions run (same
posture as `test_probe_runner.py`'s own docstring) -- except
`test_control_limits_battery_against_the_empty_stack_is_not_consistent`,
whose own docstring explains the one deliberate exception.

Short `/tmp/bg<pid>e1<run_id[:8]><n>` scratch roots throughout -- never
`tmp_path` (`sun_path` is 104 bytes on darwin; CLAUDE.md's own trap list).

--------------------------------------------------------------------------
**AC #2 is a REAL, green assertion -- decision-104's rename, not
`runner.py`'s algorithm, is what makes it reachable.** `env_battery(spec)`
run against `Stack([])` with the canary genuinely leaking
(`scrubbed_name_is_absent`'s own `ProbeOutcome.verdict` is `Verdict.FAIL`,
confirmed by direct execution) computes `report.contradictions == ()` --
`Axis.ENV` grades `UNENFORCED` on `Stack([])` (confirmed directly: no
mechanism in the empty stack claims it), and SPEC.md's own rule (this
file's own EC1 quote above) makes a `FAIL` verdict against an `UNENFORCED`
grade "not a contradiction". Under operator ruling round 15 (decision-104),
that is exactly what `BatteryVerdict.CONSISTENT` means: the battery agrees
with a report that claims nothing. `attempt 1`'s blocker was that the OLD
vocabulary had no word for this outcome other than the unreachable
`Verdict.FAIL` -- the rename supplies one, with `runner.py`'s algorithm
**unchanged** (task-053 AC #15 proves the algorithm itself by mutation).
See task-053's own notes for the full empirical trace.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import itertools
import os
import signal
import time
from collections.abc import Sequence
from typing import cast

import pytest

from brig.core import (
    Axis,
    Channel,
    ChannelKind,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    Limits,
    ProbeReport,
    ProbeShape,
    Spec,
    Verdict,
)
from brig.core.probes import Battery as CoreBattery
from brig.core.probes import BatteryVerdict
from brig.probe.batteries.env import CANARY_ENV_NAME, env_battery
from brig.probe.batteries.fs import fs_read_battery, fs_write_battery
from brig.probe.batteries.limits import limits_battery
from brig.probe.batteries.network import network_battery
from brig.run._execs import live as live_execs
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack, degraded
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()

#: `run_battery`'s own internal per-probe timeout (`brig/probe/runner.py`'s
#: `_PROBE_WAIT_TIMEOUT_S`) is 15.0s -- this file never depends on that
#: number directly (it is private to that module), but sizes its own
#: `future.result` join generously past it wherever a test lets a probe
#: run to completion normally.
_WAIT_TIMEOUT_S = 15.0


def _new_root(run_id: str, tag: str) -> str:
    """A short scratch root, `/tmp/bg<pid><tag><run_id[:8]><n>` -- never
    `tmp_path` (`sun_path` is 104 bytes on darwin). The `e1` infix (this
    file's own tag below) avoids colliding with a sibling integration
    file's own counter -- same reasoning as `test_env_scrub.py`'s and
    `test_probe_runner.py`'s own `_new_jail_dir`/`_new_root` docstrings."""
    return f"/tmp/bg{os.getpid()}{tag}{run_id[:8]}{next(_jail_counter)}"


def _launch(stack: Stack, spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str) -> Handle:
    jail_dir = _new_root(run_id, "e1")
    jail = stack.compile(spec)
    launcher = SubprocessLauncher()
    return launcher.launch(
        jail,
        argv=list(argv),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _teardown_group(handle: Handle) -> None:
    """Group-kill the long-lived workload -- the kill is hand-rolled, not
    `Handle.kill()`, same reasoning as `test_probe_runner.py`'s own
    `_teardown_group`: a test's cleanup path must not be the code under
    test. `handle.wait()` blocks until the launcher's exit-waiter has reaped
    it (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _sleep_workload(run_id: str) -> list[str]:
    return workload_argv(run_id, "sleep 100")


def _probe(handle: Handle, battery: object) -> ProbeReport:
    """Same `cast` idiom as `test_probe_runner.py`'s own `_probe` --
    `Handle.probe`'s parameter is `core.probes.Battery`, a `@runtime_
    checkable` `Protocol` every concrete `Battery` this file builds
    satisfies at runtime; the `cast` only silences the STATIC mismatch a
    frozen dataclass's read-only-modeled fields produce against a
    `Protocol`'s default read-write attribute check (see that file's own
    `_probe` docstring for the full explanation)."""
    return handle.probe(cast(CoreBattery, battery))


#: How long a registered exec sibling has to still be registered before
#: this file believes it is the spin loop rather than the CONTROL probe's
#: own near-instant exec. Generous relative to a `/usr/bin/true`-shaped
#: control (microseconds) and short relative to `run_battery`'s own 15s
#: internal wait.
_SETTLE_S = 0.5


def _wait_for_spin_loop_pgid(jail_dir: str, deadline: float = 10.0) -> int:
    """Poll this jail's exec-sibling registrations (`brig/run/_execs.py`)
    for the PERSISTENT one -- the spin loop -- and return its `pgid`.

    `run_battery` runs every CONTROL probe before any other,
    unconditionally, and waits for it; the control's registration is
    therefore created and removed again long before the spin loop's
    appears. "Persistent" is what distinguishes them without needing to
    know either pid in advance: a registration still present `_SETTLE_S`
    after it was first seen belongs to a process that is still running.

    This polled the per-jail event stream for the SECOND `EXEC` record
    until decision-152 (2026-09-08) deleted it. The registration is
    written before `exec_in_jail` ever returns, exactly as the `EXEC`
    record was, so the pid/pgid still survive while the call that spawned
    the sibling is blocked in `.wait()` -- which is the property this
    watchdog depends on."""
    deadline_at = time.monotonic() + deadline
    while time.monotonic() < deadline_at:
        registered = live_execs(jail_dir)
        if registered:
            pid, pgid, _stamp = registered[0]
            time.sleep(_SETTLE_S)
            if any(other == pid for other, _pgid, _s in live_execs(jail_dir)):
                return pgid
            continue
        time.sleep(0.02)
    raise TimeoutError(
        f"no persistent exec sibling registered under {jail_dir!r} within {deadline}s"
    )


# ---------------------------------------------------------------------------
# AC #1 / #2 -- EC1 half one, env.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_env_battery_is_consistent_against_degraded(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #1: `env_battery(spec)` against a real `degraded()` jail is
    `BatteryVerdict.CONSISTENT`, and -- stated as a PER-PROBE expectation,
    not inferred from the summary -- the `scrubbed_name_is_absent` outcome's
    OWN verdict is `Verdict.PASS`, its shape is `ProbeShape.ABSENCE`, and
    its `matched_signature` is `None`: the PASS is attributable to OBSERVED
    ABSENCE, never a signature (SPEC.md §12, decision-067, decision-104).
    Asserting the probe's own verdict, not only the battery's aggregate, is
    what makes AC #8's mutation check (env_scrub removed, leaving the axis
    UNENFORCED) actually discriminate -- see this file's module docstring.

    AC #14's real path: `report.observed_by_axis` -- built by `run_battery`,
    not hand-built -- is NON-EMPTY, its keys are exactly the axes this
    battery's probes name (`{Axis.ENV}`, both probes are `Axis.ENV`), and its
    `Axis.ENV` value is the two probes' observed `Verdict`s in order."""
    monkeypatch.setenv(CANARY_ENV_NAME, "topsecret-should-not-leak")
    spec = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",)))
    handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="ec1-env-pass", run_id=run_id
    )
    try:
        battery = env_battery(spec)
        report = _probe(handle, battery)
        assert report.battery_verdict is BatteryVerdict.CONSISTENT
        absence = next(o for o in report.outcomes if o.probe_name == "scrubbed_name_is_absent")
        assert absence.verdict is Verdict.PASS
        assert absence.shape is ProbeShape.ABSENCE
        assert absence.matched_signature is None

        view = report.observed_by_axis
        assert set(view.keys()) == {p.axis for p in battery.probes} == {Axis.ENV}
        assert view != {}
        assert view[Axis.ENV] == tuple(o.verdict for o in report.outcomes)
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_control_env_battery_against_the_empty_stack_is_consistent_with_a_failing_probe(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #2, the operator's own words (decision-104 consequences): "the
    strict xfail in 053 becomes a real green assertion under the new name."
    The identical battery, against `Stack([])` (every axis honestly
    `UNENFORCED` -- confirmed directly, see this file's module docstring)
    with a genuinely leaking canary, asserts THREE things, none inferred
    from another:

    (a) `scrubbed_name_is_absent`'s OWN verdict is `Verdict.FAIL` -- the
        probe read the environment and found the canary. This is the
        discriminating half that rules out "the probe never looked" (the
        same discriminator `test_env_battery_is_consistent_against_degraded`
        proves the honest side of).
    (b) `report.contradictions` is EMPTY, because a probe `FAIL` against an
        `UNENFORCED` grade is consistent, not a contradiction (SPEC.md §12).
    (c) `report.battery_verdict` is `BatteryVerdict.CONSISTENT` -- the
        battery agreeing with a report that claims nothing, which is
        exactly what the retired word `PASS` made unreadable."""
    monkeypatch.setenv(CANARY_ENV_NAME, "topsecret-should-leak-here")
    spec = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",)))
    handle = _launch(
        Stack([]), spec, _sleep_workload(run_id), jail_id="ec1-env-control", run_id=run_id
    )
    try:
        report = _probe(handle, env_battery(spec))
        absence = next(o for o in report.outcomes if o.probe_name == "scrubbed_name_is_absent")
        assert absence.verdict is Verdict.FAIL, (
            "the probe must have actually observed the leaking canary -- a probe "
            "that never looked would not discriminate anything"
        )
        assert report.contradictions == (), (
            "a FAIL against an UNENFORCED grade is consistent, not a "
            f"contradiction (SPEC.md sec 12); got {report.contradictions!r}"
        )
        assert report.battery_verdict is BatteryVerdict.CONSISTENT, (
            f"battery_verdict={report.battery_verdict!r} -- the battery must agree "
            "with a report that claims nothing on this axis"
        )
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #3 / #4 -- EC1 half two, cpu.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_limits_battery_is_consistent_against_degraded(run_id: str) -> None:
    """AC #3: `limits_battery(spec)` against a real `degraded()` jail with
    `Limits(cpu_seconds=1)` is `BatteryVerdict.CONSISTENT`, and -- per-probe,
    stated explicitly -- the `cpu_spin_is_killed` outcome's OWN verdict is
    `Verdict.PASS`, its `matched_signature` is not `None`, and its `subject`
    contains the exact token `'signal:SIGXCPU'` -- so the PASS is
    attributable to `rlimits`' own declared signature actually matching the
    spin loop's real, observed termination, not to the mere fact that the
    attempt failed, and not to the battery's summary word."""
    spec = Spec(limits=Limits(cpu_seconds=1))
    handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="ec1-limits-pass", run_id=run_id
    )
    try:
        report = _probe(handle, limits_battery(spec))
        assert report.battery_verdict is BatteryVerdict.CONSISTENT
        spin = next(o for o in report.outcomes if o.probe_name == "cpu_spin_is_killed")
        assert spin.verdict is Verdict.PASS
        assert spin.matched_signature is not None
        assert "signal:SIGXCPU" in spin.subject
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_control_limits_battery_against_the_empty_stack_is_not_consistent(run_id: str) -> None:
    """AC #4: the IDENTICAL battery against `Stack([])` -- no `rlimits`, so
    the spin loop never trips `SIGXCPU` on its own; it spins forever.

    **This test owns a bounded deadline `run_battery`'s internal one does
    not give it for free.** Without an external kill, the spin loop would
    run for the full 15s of `run_battery`'s own internal `exec.wait()`
    timeout and then LEAK: `Popen.wait(timeout=...)` raising
    `TimeoutExpired` does not kill its subprocess, and the exception
    propagates out of `handle.probe(...)` with no return value -- losing
    the only in-process reference `_run_one` ever had to the spin loop's
    pid. This test instead runs `handle.probe` on a worker thread and, on
    the MAIN thread, polls the jail's exec-sibling registrations for the
    spin loop's own (durably on disk -- `exec_.exec_in_jail` writes it
    BEFORE ever calling `.wait()`, so the pid/pgid survive even though the
    call that spawned it is still blocked) and sends it a real `SIGKILL`
    well inside that internal 15s window. The `finally` block re-issues
    the kill in case the watchdog's own timing ever slips, so a leak here
    fails LOUD (the conftest leak sweep) rather than silent.

    The kill this test issues is a real `SIGKILL`, not a `SIGXCPU` --
    `cpu_spin_is_killed`'s own outcome is therefore `Verdict.VACUOUS` (no
    denial-signature claim exists on the empty stack's `SignatureBook` for
    `Axis.LIMITS`), which is what actually makes `battery_verdict` land on
    `BatteryVerdict.VACUOUS` here, via `run_battery`'s "any non-control probe
    VACUOUS -> VACUOUS" branch -- not a CONTRADICTED path (see this file's
    module docstring for why that path would not fire for a plain FAIL
    against an UNENFORCED grade anyway). The AC also asks the criterion to
    NAME which verdict it IS, not only assert it is not CONSISTENT -- so
    that clause is asserted separately, with the reason in the message, so
    the criterion cannot be satisfied by an outcome nobody looked at."""
    spec = Spec(limits=Limits(cpu_seconds=1))
    handle = _launch(
        Stack([]), spec, _sleep_workload(run_id), jail_id="ec1-limits-control", run_id=run_id
    )
    battery = limits_battery(spec)
    killed_pgid: int | None = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_probe, handle, battery)
            killed_pgid = _wait_for_spin_loop_pgid(handle.jail_dir)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(killed_pgid, signal.SIGKILL)
            report = future.result(timeout=_WAIT_TIMEOUT_S + 5.0)
        assert report.battery_verdict is not BatteryVerdict.CONSISTENT
        assert report.battery_verdict is BatteryVerdict.VACUOUS, (
            f"battery_verdict={report.battery_verdict!r} -- expected VACUOUS: the "
            "spin loop was killed by an external SIGKILL, not rlimits' own "
            "SIGXCPU, so cpu_spin_is_killed's own verdict is VACUOUS (no "
            "signature claim on the empty stack) and no CONTROL probe failed"
        )
    finally:
        if killed_pgid is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(killed_pgid, signal.SIGKILL)
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #11 / #12 -- EC1 half three, honest fs/network.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_fs_and_network_batteries_report_honestly_without_contradicting(run_id: str) -> None:
    """AC #11: `fs_write_battery`, `fs_read_battery`, and `network_battery`
    -- all three, against the SAME `degraded()` handle -- report honestly
    on axes `degraded()` does not claim (`fs_read`, `fs_write`, `network`
    all fall to `Grade.UNENFORCED` via the coverage step's fill, since
    neither `rlimits` nor `env_scrub` claims any of them).

    **Updated by task-062 (doc-016 §7 deviation 4's fix):** the fs
    batteries' DENIAL probes now target HOST-resolved, genuinely-reachable
    paths (a scratch root the caller owns, a seeded credential file/dir --
    never the old `"$HOME"`-dependent or machine-conditioned targets). So
    the write-outside and both read attempts here are REAL attempts
    against a REAL, unconfined jail that GENUINELY SUCCEED (nothing in
    `degraded()` stops them), landing each probe's own `Verdict.FAIL`
    ("the attempt succeeded; the claim is false") rather than the OLD
    `Verdict.VACUOUS` this docstring used to describe -- still consistent
    with, not a contradiction of, an honestly `UNENFORCED` report (SPEC.md
    §12's asymmetry: a `FAIL` against `UNENFORCED` is consistent), so
    `fs_write`/`fs_read` each land `BatteryVerdict.CONSISTENT` on this
    host now, not `VACUOUS`.

    **Updated by task-063 (decision-117):** `network_battery` no longer
    takes a caller-supplied `control_endpoint` -- its CONTROL is derived
    from the Spec itself, so `spec` here now declares a LISTEN channel
    (`ctl.sock` under this test's own scratch root) purely so the network
    battery has a spec-permitted action to control for; the CONTROL BINDS
    that declared endpoint (never dials it -- nothing need be listening,
    binding is the one network action decision-116 records a deny-all
    Seatbelt profile as compiled to allow). The DENIAL probe now targets a
    caller-required LITERAL address (`192.0.2.1:80`, RFC 5737 TEST-NET-1)
    instead of the old hostname -- no name resolution happens at all, so
    whatever this host's real routing does with an unroutable literal
    address (refused, unreachable, or timed out) is the only thing that
    can produce its outcome. Every one of these is expected to fail for a
    REAL, non-brig reason (permission, seeded existence, or plain
    unroutability), with no declared signature to match:
    `report.contradictions` stays empty, each battery's CONTROL outcome
    PASSes (so a broken control cannot be mistaken for an honest report),
    and `battery_verdict` lands in `{BatteryVerdict.CONSISTENT,
    BatteryVerdict.VACUOUS}` -- CONSISTENT when every probe outcome
    (including the non-control denial probes) genuinely agrees with the
    UNENFORCED grade, VACUOUS when a non-control probe asserted nothing
    (its own `Verdict.VACUOUS`, per `run_battery`'s third branch). Which
    of the two each battery actually reaches on THIS host is recorded in
    the implementer's notes, not assumed."""
    workspace = _new_root(run_id, "fw")
    os.makedirs(workspace, exist_ok=True)
    # task-062: fs_write_battery/fs_read_battery now take their targets as
    # required, HOST-resolved keyword arguments (doc-016 §7 deviation 4) --
    # these three scratch paths replace the old, jail-env-dependent
    # "$HOME"-based targets. `outside_writable` is a scratch root a genuinely
    # unjailed process can write into; `credential_canary` /
    # `ssh_directory_canary` are seeded so absence can never masquerade as
    # denial (defect 3).
    outside_writable = _new_root(run_id, "fwo")
    os.makedirs(outside_writable, exist_ok=True)
    ssh_directory_canary = _new_root(run_id, "fws")
    os.makedirs(ssh_directory_canary, exist_ok=True)
    with open(os.path.join(ssh_directory_canary, "known_hosts"), "w", encoding="utf-8") as f:
        f.write("canary\n")
    credential_canary_dir = _new_root(run_id, "fwc")
    os.makedirs(credential_canary_dir, exist_ok=True)
    credential_canary = os.path.join(credential_canary_dir, "credentials")
    with open(credential_canary, "w", encoding="utf-8") as f:
        f.write("canary\n")
    # task-063 (decision-117): the CONTROL is derived from the Spec, so a
    # LISTEN channel must be declared for network_battery to have a
    # spec-permitted action to control for -- the endpoint is a plain path
    # under this test's own scratch root, nothing pre-bound.
    channel_root = _new_root(run_id, "fnc")
    os.makedirs(channel_root, exist_ok=True)
    channel_endpoint = os.path.join(channel_root, "ctl.sock")
    spec = Spec(
        fs=FsPolicy(write_allows=(workspace,)),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=channel_endpoint),),
    )
    handle = _launch(degraded(), spec, _sleep_workload(run_id), jail_id="ec1-fs-net", run_id=run_id)
    try:
        batteries = (
            fs_write_battery(spec, outside_writable=outside_writable),
            fs_read_battery(
                spec,
                credential_canary=credential_canary,
                ssh_directory_canary=ssh_directory_canary,
            ),
            network_battery(spec, denied_address="192.0.2.1:80"),
        )
        for battery in batteries:
            report = _probe(handle, battery)
            assert report.contradictions == (), (
                f"{battery.name!r}: unexpected contradiction(s) {report.contradictions!r}"
            )
            control = next(o for o in report.outcomes if o.shape is ProbeShape.CONTROL)
            assert control.verdict is Verdict.PASS, (
                f"{battery.name!r}: CONTROL probe did not PASS -- a broken "
                "control cannot be mistaken for an honest report"
            )
            assert report.battery_verdict in (BatteryVerdict.CONSISTENT, BatteryVerdict.VACUOUS), (
                f"{battery.name!r}: battery_verdict={report.battery_verdict!r} -- "
                "degraded() enforces neither fs nor network, so an outcome outside "
                "{CONSISTENT, VACUOUS} would mean either a false claim of "
                "enforcement or an actual contradiction, neither of which this "
                "host's real filesystem/network behavior should produce"
            )
    finally:
        _teardown_group(handle)


@pytest.mark.integration
def test_the_network_control_fails_when_the_declared_endpoint_cannot_be_bound(
    run_id: str,
) -> None:
    """AC #12, the control on the control (task-053's own name for this
    test was `test_the_network_control_fails_without_a_listener`; task-053
    is Done and its own AC #12 text keeps that name as the historical
    record of what was true then, per decision-079 -- not retro-edited.
    **Updated by task-063 (decision-117):** the LISTEN-shape CONTROL now
    BINDS the Spec's own declared endpoint rather than dialing a
    caller-supplied `control_endpoint` -- there is no longer an
    out-of-band endpoint to point at nothing, so "without a listener" no
    longer names a failure this CONTROL can have. The renamed test targets
    the equivalent failure mode for a bind: the declared endpoint already
    being occupied. This test seeds the endpoint with a plain file before
    launch, so the CONTROL's own `socket.bind()` genuinely raises
    (`EADDRINUSE` -- the path exists). Its `CONTROL` probe outcome is
    `Verdict.FAIL`, and the battery verdict is `BatteryVerdict.VACUOUS`
    (`run_battery`'s "any control not PASS -> VACUOUS" branch). This is
    what proves AC #11's own `control.verdict is Verdict.PASS` assertion
    is capable of failing: without this test, a probe mechanism that
    reported CONTROL-PASS unconditionally, endpoint bindable or not, would
    sail through AC #11 undetected. MUTATION-CHECKED (see task-063's own
    notes): removing the occupying seed below makes `control.verdict is
    Verdict.FAIL` go red, because the bind then genuinely succeeds."""
    channel_root = _new_root(run_id, "ncf")
    os.makedirs(channel_root, exist_ok=True)
    channel_endpoint = os.path.join(channel_root, "ctl.sock")
    with open(channel_endpoint, "w", encoding="utf-8") as f:
        f.write("occupied\n")
    spec = Spec(channels=(Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=channel_endpoint),))
    handle = _launch(
        degraded(), spec, _sleep_workload(run_id), jail_id="ec1-net-control-fail", run_id=run_id
    )
    try:
        battery = network_battery(spec, denied_address="192.0.2.1:80")
        report = _probe(handle, battery)
        control = next(o for o in report.outcomes if o.shape is ProbeShape.CONTROL)
        assert control.verdict is Verdict.FAIL
        assert report.battery_verdict is BatteryVerdict.VACUOUS
    finally:
        _teardown_group(handle)
