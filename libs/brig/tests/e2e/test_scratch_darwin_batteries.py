"""task-065: MILESTONES.md M5-lite exit criterion 3, verbatim -- this file
owns EC3:

    `fs_write`, `fs_read` and `network` probe batteries report `CONSISTENT`
    against `scratch_darwin()` with their DENIAL probes at `PASS` -- the
    first passing fs battery in the project -- and the M4 forgery check
    still catches a weakened stack (`tests/e2e/test_probe_forgery.py`,
    with its two controls, rewritten onto the stack this milestone
    weakens).

and EC5's second half, verbatim:

    under `scratch_darwin()` lands `PASS` on a matched seatbelt signature.

The forgery half of EC3 lives in `test_probe_forgery.py` (this file's
sibling, extended rather than replaced -- see that module's own docstring
for the M4 journey it still carries). This file owns Part 1 (the headline
three batteries), Part 2 (EC5's matched-signature identity requirement),
and AC #11 (the network journey's Spec declaring a LISTEN channel,
decision-117).

SPEC.md sec 12's `CONSISTENT` / `CONTRADICTED` / `VACUOUS` vocabulary
(decision-104) is the word set every assertion here uses -- `BatteryVerdict`
at battery altitude, `Verdict` per probe.

`doc-016` sec 9 ask 2, verbatim:

    Under real enforcement an `UNENFORCED` grade stops being the common
    case, which is when the `CONSISTENT`-versus-enforcement-proven
    distinction gets concrete rather than definitional.

**Read model matters here in a way it did not for `degraded()`.** seatbelt's
`fs_read` axis is a DENYLIST (default-ALLOW, `spec.fs.read_denies` compiled
as explicit per-path denies -- `brig/mech/seatbelt/__init__.py`'s own
`_FS_READ_DETAIL`). `credential_canary` and `ssh_directory_canary` are
ordinary scratch paths, not `$HOME`-relative ones `brig.core.threats`
already threat-lists, so this file folds them into `spec.fs.read_denies`
itself (`brig.core.threats`'s own module docstring: "Threat lists ship as
documented tuples that the embedder folds in explicitly") -- the SAME
posture `tests/integration/test_seatbelt_fs.py`'s own `read_denies` fixture
takes. Likewise `write_into_git_hooks_carveout`'s target
(`workspace/.git/hooks/...`) sits INSIDE the granted `write_allows`
workspace, so without a matching `spec.fs.write_denies` carve-out
(`test_seatbelt_fs.py`'s own `hooks_dir` fixture, reproduced here) seatbelt
would honestly ALLOW it -- not a defect in seatbelt, a Spec this file must
build correctly to exercise the carve-out threat SPEC.md sec 5 names.

**Why a LISTEN channel, never `spec.network.allowed_domains`.**
`Seatbelt.compile` raises `NetworkUnsupported` outright when
`spec.network.allowed_domains` is non-empty -- seatbelt has no DNS
awareness (that mechanism's own module docstring, refusal 3). The only
network action a deny-all seatbelt profile is compiled to permit is binding
a declared LISTEN channel's own endpoint (`decision-116`), which is exactly
what `network_battery`'s own CONTROL-selection logic reaches for when a
Spec declares one (`decision-117`). AC #11 pins this as fact about THIS
file's own journey Spec, with its own construction-time control (a Spec
that drops the channel makes `network_battery` refuse) -- distinct from,
and not a re-derivation of, `tests/e2e/test_degraded_journey.py`'s own
identical-shaped pair pinned against `degraded()`'s journey (task-070,
decision-125): that file's pair is about `network_battery` in general; this
one is about the Spec THIS file's own journey drives.

Public-API-only, per `.claude/rules/system-tests.md`: `Spec` ->
`scratch_darwin()` -> `Launcher` -> `Handle` -> `handle.probe`.
`BatteryVerdict` (`brig.core.probes`) is the one name not re-exported by
`brig.core`'s barrel -- imported directly, the same justified exception
`test_probe_forgery.py`'s own module docstring already carries (grep
evidence there, not reproduced here).

Darwin-gated at module level: `scratch_darwin()` composes `seatbelt`
(`sandbox-exec`/SBPL), which exists only on darwin (SPEC.md sec 6's roster
row).
"""

from __future__ import annotations

import dataclasses
import itertools
import os
import sys
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
    Grade,
    ProbeReport,
    ProbeShape,
    Spec,
    Verdict,
)
from brig.core import Battery as CoreBattery
from brig.core.probes import (
    BatteryVerdict,  # not barrel-exported; justified in this module's docstring
)
from brig.probe.batteries.fs import fs_read_battery, fs_write_battery
from brig.probe.batteries.network import network_battery
from brig.run import Handle, IoPolicy, SubprocessLauncher, build_compile_ctx
from brig.stack import CompiledJail, Stack, scratch_darwin
from tests.conftest import teardown_group, workload_argv

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="scratch_darwin() composes seatbelt (sandbox-exec/SBPL), darwin-only (SPEC.md sec 6)",
)

_jail_counter = itertools.count()

#: RFC 5737 TEST-NET-1 -- a literal address, never a hostname (network_battery's
#: own "Defect A" docstring), so the DENIAL probe's only obstacle is policy.
_DENIED_NETWORK_ADDRESS = "192.0.2.1:80"


def _new_root(run_id: str, tag: str) -> str:
    """A short scratch root, `/tmp/bg<pid><tag><run_id[:8]><n>` -- never
    pytest `tmp_path` (`sun_path` is 104 bytes on darwin, CLAUDE.md's trap
    list). The `sd` family of tags below is this file's own, distinct from
    `test_probe_forgery.py`'s `pf` and `test_degraded_journey.py`'s `dj`."""
    return f"/tmp/bg{os.getpid()}{tag}{run_id[:8]}{next(_jail_counter)}"


def _launch_at(
    stack: Stack, spec: Spec, jail_dir: str, argv: Sequence[str], *, jail_id: str
) -> tuple[Handle, CompiledJail]:
    """`Spec -> Stack.compile(ctx=build_compile_ctx(...)) -> SubprocessLauncher
    -> Handle`, through public methods on public types only -- the exact
    chain `.claude/rules/system-tests.md` names. `jail_dir` is a caller-
    supplied argument, not generated here, because a LISTEN channel's own
    endpoint must be built from it BEFORE the Spec exists (same ordering
    `tests/integration/test_seatbelt_channel.py` uses)."""
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    jail = stack.compile(spec, ctx=ctx)
    launcher = SubprocessLauncher()
    handle = launcher.launch(
        jail, argv=list(argv), cwd=jail_dir, io=IoPolicy(), jail_id=jail_id, jail_dir=jail_dir
    )
    return handle, jail


def _teardown_group(handle: Handle) -> None:
    """Hand-rolled group-kill, not `Handle.kill()` -- a test's cleanup path
    must not be the code under test (same posture as this file's e2e
    siblings' own `_teardown_group`)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _probe(handle: Handle, battery: object) -> ProbeReport:
    """Same cast idiom as `test_probe_forgery.py`'s own `_probe` -- see that
    module's docstring for why the cast, not the Protocol mismatch itself,
    is what mypy --strict needs silenced here."""
    return handle.probe(cast(CoreBattery, battery))


def _seed_fs_targets(run_id: str) -> tuple[str, str, str, str, str]:
    """Build and seed every HOST-resolved scratch path the fs batteries need
    (doc-016 sec 7 deviation 4, task-062): `workspace` (spec.fs.write_allows[0]),
    `hooks_dir` (the `.git/hooks` carve-out INSIDE workspace -- must also land
    in `spec.fs.write_denies` or seatbelt honestly ALLOWS it, this module's own
    docstring), `outside_writable` (genuinely writable by an unjailed process),
    `credential_canary` (a FILE, seeded), and `ssh_directory_canary` (a
    DIRECTORY, seeded with one entry). Returns them in that order."""
    workspace = _new_root(run_id, "sdw")
    hooks_dir = os.path.join(workspace, ".git", "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    outside_writable = _new_root(run_id, "sdo")
    os.makedirs(outside_writable, exist_ok=True)

    credential_root = _new_root(run_id, "sdc")
    os.makedirs(credential_root, exist_ok=True)
    credential_canary = os.path.join(credential_root, "credentials")
    with open(credential_canary, "w", encoding="utf-8") as f:
        f.write("canary-secret\n")

    ssh_directory_canary = _new_root(run_id, "sds")
    os.makedirs(ssh_directory_canary, exist_ok=True)
    with open(os.path.join(ssh_directory_canary, "known_hosts"), "w", encoding="utf-8") as f:
        f.write("canary-host-key\n")

    return workspace, hooks_dir, outside_writable, credential_canary, ssh_directory_canary


def _journey_spec(
    *,
    workspace: str,
    hooks_dir: str,
    credential_canary: str,
    ssh_directory_canary: str,
    listen_endpoint: str,
) -> Spec:
    """The one Spec this file's headline journey drives, and the one AC #11
    is about. `write_denies` carries the `.git/hooks` carve-out (SELF_MODIFY
    threat, SPEC.md sec 5) and `read_denies` carries both read canaries
    (seatbelt's fs_read is a denylist -- default-ALLOW, module docstring
    above) -- both explicitly folded in, per `brig.core.threats`'s own
    "the embedder folds in explicitly" posture. `channels` carries exactly
    one declared LISTEN channel -- the only network action scratch_darwin()
    (seatbelt) can honestly stand a positive control up for
    (decision-116/117; AC #11)."""
    return Spec(
        fs=FsPolicy(
            write_allows=(workspace,),
            write_denies=(hooks_dir,),
            read_denies=(credential_canary, ssh_directory_canary),
        ),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",)),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=listen_endpoint),),
    )


_BATTERY_AXES: dict[str, Axis] = {
    "fs_write": Axis.FS_WRITE,
    "fs_read": Axis.FS_READ,
    "network": Axis.NETWORK,
}


# ---------------------------------------------------------------------------
# Part 1 (AC #2 / #3) + Part 2 (AC #4): the headline journey.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_scratch_darwin_fs_and_network_batteries_reach_consistent_with_denial_pass(
    run_id: str,
) -> None:
    """AC #2/#3/#4 -- EC3's headline and EC5's second half, in one real
    `scratch_darwin()` jail.

    **AC #2**: each of `fs_write`, `fs_read`, `network` reaches
    `BatteryVerdict.CONSISTENT` with every `DENIAL` probe's own `Verdict`
    `PASS` (and every `CONTROL` probe's own `Verdict` `PASS`) -- a per-probe
    table (probe name, shape, verdict, report grade, matched signature) is
    printed below, the shape `doc-016` sec 2 pastes EC1's own table in.

    **AC #3**: every assertion below reads `report.observed_by_axis` and
    each outcome's own `.verdict`, per probe -- never `battery_verdict`
    alone standing in for "every probe passed" (M4's own discrimination
    defect, this task's own Description names it).

    **AC #4**: each fs `DENIAL` probe's `matched_signature` is asserted by
    IDENTITY (`is`, never a substring match) against
    `jail.signatures.for_axis(...)` -- the SAME `SignatureBook` this run's
    own `Stack.compile` produced, i.e. seatbelt's own declaration for THIS
    run, not a separately re-derived one. `network`'s own `DENIAL` probe is
    held to the identical identity bar for the same reason Part 1's own
    headline names it ("network -- same shape").
    """
    workspace, hooks_dir, outside_writable, credential_canary, ssh_directory_canary = (
        _seed_fs_targets(run_id)
    )
    jail_dir = _new_root(run_id, "sdj")
    listen_endpoint = f"{jail_dir}/ctl.sock"
    spec = _journey_spec(
        workspace=workspace,
        hooks_dir=hooks_dir,
        credential_canary=credential_canary,
        ssh_directory_canary=ssh_directory_canary,
        listen_endpoint=listen_endpoint,
    )

    handle, jail = _launch_at(
        scratch_darwin(),
        spec,
        jail_dir,
        workload_argv(run_id, "sleep 100"),
        jail_id="sd-journey",
    )
    try:
        # Sanity: scratch_darwin() actually claims what this test is about
        # to probe -- otherwise nothing below would be evidence of anything.
        for axis in (Axis.FS_WRITE, Axis.FS_READ, Axis.NETWORK):
            assert handle.report.axes[axis].grade is Grade.ENFORCED, (
                axis,
                handle.report.axes[axis],
            )

        reports: dict[str, ProbeReport] = {
            "fs_write": _probe(handle, fs_write_battery(spec, outside_writable=outside_writable)),
            "fs_read": _probe(
                handle,
                fs_read_battery(
                    spec,
                    credential_canary=credential_canary,
                    ssh_directory_canary=ssh_directory_canary,
                ),
            ),
            "network": _probe(
                handle, network_battery(spec, denied_address=_DENIED_NETWORK_ADDRESS)
            ),
        }

        # --- the per-probe table (AC #2's own pasted evidence) -- grade
        # read per OUTCOME's own axis, literally per-probe, not looked up
        # once per battery (every outcome in a battery shares one axis
        # today, but this is what "per-probe" in the AC's own wording
        # means). -----------------------------------------------------
        print("\nbattery.probe | shape | verdict | report_grade | matched_signature")
        for name, report in reports.items():
            for outcome in report.outcomes:
                grade = handle.report.axes[outcome.axis].grade
                print(
                    f"{name}.{outcome.probe_name} | {outcome.shape.value} | "
                    f"{outcome.verdict.value} | {grade.value} | {outcome.matched_signature!r}"
                )

        # --- AC #2: battery verdict, every battery. -----------------------
        for name, report in reports.items():
            assert report.battery_verdict is BatteryVerdict.CONSISTENT, (
                name,
                report.battery_verdict,
                report.contradictions,
            )

        # --- AC #3: per-probe, per-axis, via observed_by_axis ITSELF --
        # never the battery word alone (M4's own discrimination defect).
        # The first assertion reads observed_by_axis directly (every
        # observed Verdict on the axis is PASS, and NOTHING observed on
        # any other axis -- no probe strayed); the per-outcome loop below
        # is kept too, for a failing probe's own name in the assertion. --
        for name, report in reports.items():
            axis = _BATTERY_AXES[name]
            observed_by_axis = report.observed_by_axis
            assert set(observed_by_axis) == {axis}, (name, observed_by_axis)
            assert set(observed_by_axis[axis]) == {Verdict.PASS}, (name, observed_by_axis[axis])
            for outcome in report.outcomes:
                if outcome.shape is ProbeShape.DENIAL:
                    assert outcome.verdict is Verdict.PASS, (
                        name,
                        outcome.probe_name,
                        outcome.verdict,
                        outcome.subject,
                        outcome.detail,
                    )
                elif outcome.shape is ProbeShape.CONTROL:
                    assert outcome.verdict is Verdict.PASS, (
                        name,
                        outcome.probe_name,
                        outcome.verdict,
                        outcome.subject,
                    )

        # network's own control is the LISTEN-bind shape, task-063's own
        # "spec-shaped control" (Part 1's headline names it explicitly) --
        # never the granted-domain shape, which this Spec never permits.
        network_control_names = {
            o.probe_name for o in reports["network"].outcomes if o.shape is ProbeShape.CONTROL
        }
        assert network_control_names == {"bind_the_declared_listen_endpoint"}, network_control_names

        # --- AC #4: fs DENIAL probes' matched_signature, by IDENTITY. The
        # signature compared against comes from `jail.signatures` -- the
        # SAME SignatureBook `_launch_at`'s own `stack.compile(...)` call
        # produced and this run was actually LAUNCHED with -- never a
        # second, separately-derived compile, and never seatbelt's private
        # `_DENIAL_SIGNATURE` module constant, because e2e tests
        # drive the public API only (`.claude/rules/system-tests.md`):
        # `jail.signatures.for_axis(...)` is `CompiledJail`'s own public
        # field, reached the same way an embedder holding `jail` would. -----
        fs_write_claim = jail.signatures.for_axis(Axis.FS_WRITE)
        fs_read_claim = jail.signatures.for_axis(Axis.FS_READ)
        network_claim = jail.signatures.for_axis(Axis.NETWORK)
        assert fs_write_claim is not None
        assert fs_read_claim is not None
        assert network_claim is not None
        # seatbelt declares exactly one denial-signature pattern (this
        # module's own docstring: "Operation not permitted") -- asserted
        # before indexing [0], so a mechanism that someday declares more
        # than one pattern fails LOUD here rather than silently comparing
        # against only the first.
        assert len(fs_write_claim.signatures) == 1, fs_write_claim.signatures
        assert len(fs_read_claim.signatures) == 1, fs_read_claim.signatures
        assert len(network_claim.signatures) == 1, network_claim.signatures
        fs_write_signature = fs_write_claim.signatures[0].pattern
        fs_read_signature = fs_read_claim.signatures[0].pattern
        network_signature = network_claim.signatures[0].pattern

        for outcome in reports["fs_write"].outcomes:
            if outcome.shape is ProbeShape.DENIAL:
                assert outcome.matched_signature is not None, outcome.probe_name
                assert outcome.matched_signature is fs_write_signature, (
                    outcome.probe_name,
                    outcome.matched_signature,
                    fs_write_signature,
                )
        for outcome in reports["fs_read"].outcomes:
            if outcome.shape is ProbeShape.DENIAL:
                assert outcome.matched_signature is not None, outcome.probe_name
                assert outcome.matched_signature is fs_read_signature, (
                    outcome.probe_name,
                    outcome.matched_signature,
                    fs_read_signature,
                )
        # network's own DENIAL probe, held to the same identity bar (Part
        # 1's headline: "network -- same shape").
        for outcome in reports["network"].outcomes:
            if outcome.shape is ProbeShape.DENIAL:
                assert outcome.matched_signature is not None, outcome.probe_name
                assert outcome.matched_signature is network_signature, (
                    outcome.probe_name,
                    outcome.matched_signature,
                    network_signature,
                )
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #8: the control against the ENVIRONMENT, not the kernel. Same Spec,
# Stack([]) -- zero mechanisms -- and every DENIAL probe must NOT reach PASS.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_control_against_the_environment_stack_of_no_mechanisms_denies_nothing(
    run_id: str,
) -> None:
    """AC #8. The IDENTICAL Spec the headline journey above drives, launched
    through `Stack([])` (zero mechanisms -- `CompiledJail.wrap` is the
    identity) instead of `scratch_darwin()`. No `DENIAL` probe in any of the
    three batteries may reach `Verdict.PASS` here: this is what makes the
    headline test's own `PASS`es above attributable to seatbelt, not to some
    accident of this host's ordinary file permissions or an unreachable
    literal address (the exact control `.claude/rules/integration-tests.md`
    requires for every denial assertion, carried up to the e2e tier).

    **Stated plainly, not left for a reader to notice in the printed table:**
    the two fs rows land `Verdict.FAIL` here (the write/read genuinely
    succeeds against no mechanism -- direct proof egress was POSSIBLE, so
    the headline test's own fs `PASS`es are discriminated against a real
    alternative). The network row instead lands `Verdict.VACUOUS`: the
    literal TEST-NET-1 address `_DENIED_NETWORK_ADDRESS` fails to connect
    even completely unjailed (no route to a reserved, non-routable address),
    so this control cannot show egress was POSSIBLE the way the fs rows do
    -- its own discriminating power is narrower, resting on the SIGNATURE
    match alone (headline `PASS` + `'Operation not permitted'` vs. here
    `VACUOUS` + no signature), not on "the same action succeeds
    unconfined". Both are still "not PASS", which is everything this AC
    asks for -- but the network row's own evidence is weaker than the fs
    rows', and this docstring says so rather than letting a `vacuous`
    line in the printed table go unexplained (doc-016 sec 2's own posture:
    an honesty note where a battery word alone would read stronger than
    what was actually shown)."""
    workspace, hooks_dir, outside_writable, credential_canary, ssh_directory_canary = (
        _seed_fs_targets(run_id)
    )
    jail_dir = _new_root(run_id, "sde")
    listen_endpoint = f"{jail_dir}/ctl.sock"
    spec = _journey_spec(
        workspace=workspace,
        hooks_dir=hooks_dir,
        credential_canary=credential_canary,
        ssh_directory_canary=ssh_directory_canary,
        listen_endpoint=listen_endpoint,
    )

    handle, _jail = _launch_at(
        Stack([]), spec, jail_dir, workload_argv(run_id, "sleep 100"), jail_id="sd-env-control"
    )
    try:
        reports: dict[str, ProbeReport] = {
            "fs_write": _probe(handle, fs_write_battery(spec, outside_writable=outside_writable)),
            "fs_read": _probe(
                handle,
                fs_read_battery(
                    spec,
                    credential_canary=credential_canary,
                    ssh_directory_canary=ssh_directory_canary,
                ),
            ),
            "network": _probe(
                handle, network_battery(spec, denied_address=_DENIED_NETWORK_ADDRESS)
            ),
        }
        print("\n[AC #8 environment control] battery.probe | verdict")
        for name, report in reports.items():
            for outcome in report.outcomes:
                if outcome.shape is ProbeShape.DENIAL:
                    print(f"{name}.{outcome.probe_name} | {outcome.verdict.value}")
                    assert outcome.verdict is not Verdict.PASS, (
                        f"[{name}] {outcome.probe_name} reached PASS with NO mechanism "
                        f"in the stack -- verdict={outcome.verdict!r}, this environment "
                        "control must never pass a denial probe"
                    )
    finally:
        _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #11: the network journey's Spec DECLARES A LISTEN CHANNEL, and its own
# removal control.
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_journey_spec_declares_a_listen_channel_and_its_removal_makes_the_battery_refuse(
    run_id: str,
) -> None:
    """AC #11. Two assertions about THIS file's own `_journey_spec` (the
    exact Spec-building function the headline test above drives) -- distinct
    from, and not a re-derivation of, `test_degraded_journey.py`'s own
    identical-shaped pair against `degraded()`'s journey (task-070,
    decision-125's own boundary: that pair is about `network_battery` in
    general, this one is about the Spec THIS file's own journey drives).

    1. The journey Spec DOES declare a `ChannelKind.LISTEN` channel, and
       `network_battery` constructs against it without raising -- without
       this, EC3's own network row is unreachable (task-063 AC #10).
    2. The CONTROL: the same Spec with `channels` emptied makes
       `network_battery` refuse at construction (`decision-117`, `ValueError`
       naming both missing declarations), pasted below.
    """
    jail_dir = _new_root(run_id, "sdn")
    listen_endpoint = f"{jail_dir}/ctl.sock"
    # network_battery reads only spec.channels and spec.network.allowed_domains
    # (this file's own imported source, `brig/probe/batteries/network.py`) --
    # the fs-shaped placeholders below need not exist on disk for this
    # construct-only test, which never launches a jail or runs a probe.
    placeholder = _new_root(run_id, "sdnph")
    spec = _journey_spec(
        workspace=placeholder,
        hooks_dir=os.path.join(placeholder, ".git", "hooks"),
        credential_canary=os.path.join(placeholder, "credentials"),
        ssh_directory_canary=placeholder,
        listen_endpoint=listen_endpoint,
    )

    # Every declared channel is a LISTEN channel (decision-153: `LISTEN` is
    # the only `ChannelKind` there is), so declaring one is the assertion.
    assert spec.channels, "this file's journey Spec must declare a LISTEN channel (AC #11)"

    battery = network_battery(spec, denied_address=_DENIED_NETWORK_ADDRESS)
    assert battery.name == "network"
    assert len(battery.probes) == 2

    channel_less = dataclasses.replace(spec, channels=())
    with pytest.raises(ValueError) as exc_info:
        network_battery(channel_less, denied_address=_DENIED_NETWORK_ADDRESS)
    message = str(exc_info.value)
    print("\n[AC #11 control] network_battery on a channel-less Spec raised:", message)
    assert "no LISTEN channel" in message, message
    assert "spec.network.allowed_domains" in message, message
