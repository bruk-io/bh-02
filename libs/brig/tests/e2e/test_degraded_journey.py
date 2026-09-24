"""One small e2e journey (task-054 AC #5), through the public API
only, per `.claude/rules/system-tests.md`:

    Full stacks through the public API only: `Spec` -> preset `Stack` ->
    `Launcher` -> `Handle` -> probe battery, exactly as an embedder would
    drive them. No internal imports below the public surface

and:

    Volume: this tier stays small -- a handful of journeys per preset.

This file drives exactly one journey against `degraded()`: `Spec ->
degraded() -> SubprocessLauncher -> Handle -> handle.probe(...)` for each of
the FOUR batteries `degraded()`'s spec here can honestly stand up a battery
for -> `handle.kill()`. `test_probe_forgery.py`, this file's sibling, owns
EC3 and its controls; this file owns the end-to-end shape and `kill()`'s own
honesty, neither of which EC3's forgery needs to also carry.

**task-070 (decision-125): why there is a second test function here, and why
that is not a second journey.** The old fifth row, `network`, probed
`network_battery` against this journey's own `spec`, which declares no
`ChannelKind.LISTEN` channel and grants no `spec.network.allowed_domains` --
exactly the shape `decision-117` converted from a tolerated `VACUOUS` verdict
into a construction-time refusal (SPEC.md §6's no-work-to-do rule: a battery
that would be permanently `VACUOUS` against the preset it was built for
refuses rather than shipping). `degraded()`'s own docstring already states it
claims neither axis for network, so there was never a real network mechanism
here for a journey to exercise -- the row was only ever recording "nothing to
claim, nothing to probe" in verdict vocabulary. Dropping it (chosen over
asserting the refusal inline -- see the journey's own docstring for why) does
not drop `decision-117`'s coverage: `test_network_battery_refuses_a_spec_with_no_network_action`
and `test_network_battery_permits_a_spec_declaring_a_listen_channel` below
are `network_battery`'s own control pair, construct-only (no jail, no probe,
no second launch), so they add no volume to what
`.claude/rules/system-tests.md` calls "a handful of journeys per preset" --
they are not a journey at all, just two direct assertions about one already-
imported factory function.

**Public-API-only, the same two names.** `BatteryVerdict` and `KillOutcome`
are each real, documented public types that are simply not re-exported by
their package's barrel `__init__.py` -- see `test_probe_forgery.py`'s own
module docstring for the full accounting (grep evidence, and why neither
gap needs a hook to work around). This file imports both the identical way.
"""

from __future__ import annotations

import itertools
import os
from collections.abc import Sequence
from dataclasses import replace
from typing import cast

import pytest

from brig.core import Battery as CoreBattery
from brig.core import (
    Channel,
    ChannelKind,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    Limits,
    ProbeReport,
    Spec,
)
from brig.core.probes import BatteryVerdict  # not barrel-exported; justified in AC #6
from brig.probe.batteries.env import CANARY_ENV_NAME, env_battery  # batteries: no barrel, by design
from brig.probe.batteries.fs import fs_read_battery, fs_write_battery
from brig.probe.batteries.limits import limits_battery
from brig.probe.batteries.network import network_battery
from brig.run import Handle, IoPolicy, SubprocessLauncher
from brig.run.teardown import KillOutcome  # not barrel-exported; same shape, justified in AC #6
from brig.stack import degraded
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()


def _new_root(run_id: str, tag: str) -> str:
    """A short scratch root -- never `tmp_path` (`sun_path` is 104 bytes on
    darwin). The `dj` infix keeps this file's counter separate from its
    `test_probe_forgery.py` sibling's own `pf`-tagged one."""
    return f"/tmp/bg{os.getpid()}{tag}{run_id[:8]}{next(_jail_counter)}"


def _launch(spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str) -> Handle:
    """`Spec -> degraded() -> SubprocessLauncher -> Handle`, through public
    methods on public types only -- the exact chain this file's own AC
    names."""
    jail_dir = _new_root(run_id, "dj")
    jail = degraded().compile(spec)
    launcher = SubprocessLauncher()
    return launcher.launch(
        jail,
        argv=list(argv),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _probe(handle: Handle, battery: object) -> ProbeReport:
    """Same cast idiom as `test_probe_forgery.py`'s own `_probe` -- see
    that module's docstring for why the cast, not the Protocol mismatch
    itself, is what mypy --strict needs silenced here."""
    return handle.probe(cast(CoreBattery, battery))


def _teardown_group(handle: Handle) -> None:
    """A defensive, idempotent fallback -- `os.killpg` on an already-gone
    group raises `ProcessLookupError`, suppressed. `handle.kill()` is what
    this test actually asserts about; this exists only so a failed
    assertion AFTER `kill()` still leaves the machine clean for the
    conftest leak-check (AC #10), not as the teardown path under test."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


@pytest.mark.e2e
def test_degraded_journey_through_the_public_api_only(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #5. One `degraded()` jail, probed by the FOUR batteries this
    journey's `spec` can honestly stand one up for, then torn down through
    `handle.kill()` -- the whole public surface `.claude/rules/system-tests.md`
    names, in one journey.

    **task-070 (decision-125): the fifth row, `network`, is GONE, not merely
    tolerated `VACUOUS`.** `network_battery(spec, ...)` against THIS journey's
    `spec` -- no `ChannelKind.LISTEN` channel, no `spec.network.allowed_domains`
    -- now raises `ValueError` at construction (`decision-117`, landed
    task-063): a battery that would be permanently `VACUOUS` against the
    preset it was built for refuses rather than shipping (SPEC.md §6's
    no-work-to-do rule). `degraded()` itself claims neither axis for network
    (`brig/stack/__init__.py`'s own `degraded()` docstring), so this journey
    never had a real network mechanism to exercise -- the old row was always
    "nothing claimed, nothing to probe" spelled as a verdict. Chosen over
    asserting the refusal inline here: `decision-117`'s behaviour is a fact
    about `network_battery` itself, independent of any one preset's journey,
    so it is pinned once, directly, by
    `test_network_battery_refuses_a_spec_with_no_network_action` and its
    control-pair sibling below -- not re-derived per journey that happens to
    carry a network-less `Spec`. Dropping the row here keeps this journey
    about what `degraded()` actually composes (`env_scrub`, `rlimits`) and
    what its own `Spec` grants (`fs.write_allows`), rather than about a
    battery that, for this preset, would never construct at all.

    **Battery verdicts, against a literal expected mapping** (`degraded()`
    claims exactly `env` and `limits`; `fs_write`/`fs_read` are honestly
    `unenforced` until M5/M6 -- see `brig/stack/__init__.py`'s own
    `degraded()` docstring):

    - `env` -> `BatteryVerdict.CONSISTENT` (env_scrub's own claim, proven by
      the ABSENCE probe's observed absence plus the CONTROL).
    - `limits` -> `BatteryVerdict.CONSISTENT` (rlimits' own SIGXCPU
      signature, matched against the real spin-loop termination).
    - `fs_write` / `fs_read` -> each reaches
      `{BatteryVerdict.CONSISTENT, BatteryVerdict.VACUOUS}`: `degraded()`
      claims neither axis, so every denial probe's own `claim` is `None`.
      **Updated by task-062 (doc-016 §7 deviation 4's fix):** `fs_write`
      and `fs_read`'s DENIAL probes now target HOST-resolved, genuinely
      reachable paths (a scratch root the caller owns, a seeded credential
      file/directory), so their real attempts here GENUINELY SUCCEED --
      each probe's own `Verdict.FAIL` ("the attempt succeeded; the claim
      is false"), which is still consistent (not a contradiction) against
      an honestly `UNENFORCED` grade (SPEC.md §12's asymmetry), so both
      batteries land `BatteryVerdict.CONSISTENT` on this host, not
      `VACUOUS`. Both members of the permitted set remain asserted below
      because this is host-conditioned per axis, not a fixed fact of the
      preset.

    **Teardown.** `handle.kill()` tears down the workload group and every
    exec sibling `handle.probe(...)` registered while running the four
    batteries' own DENIAL/CONTROL/ABSENCE probes above -- every item's
    outcome must be `ENDED` or `ALREADY_GONE`, never `FAILED` (SPEC.md
    sec 9's fixed ladder: verification is the last, non-optional rung).
    """
    monkeypatch.setenv(CANARY_ENV_NAME, "topsecret-should-not-leak")
    workspace = _new_root(run_id, "djw")
    os.makedirs(workspace, exist_ok=True)
    # task-062: fs_write_battery/fs_read_battery now take their targets as
    # required, HOST-resolved keyword arguments (doc-016 §7 deviation 4) --
    # see tests/integration/test_battery_targets.py for the dedicated
    # coverage of the fix itself; this journey only needs valid targets to
    # keep constructing.
    outside_writable = _new_root(run_id, "djo")
    os.makedirs(outside_writable, exist_ok=True)
    ssh_directory_canary = _new_root(run_id, "djs")
    os.makedirs(ssh_directory_canary, exist_ok=True)
    with open(os.path.join(ssh_directory_canary, "known_hosts"), "w", encoding="utf-8") as f:
        f.write("canary\n")
    credential_canary_dir = _new_root(run_id, "djc")
    os.makedirs(credential_canary_dir, exist_ok=True)
    credential_canary = os.path.join(credential_canary_dir, "credentials")
    with open(credential_canary, "w", encoding="utf-8") as f:
        f.write("canary\n")
    spec = Spec(
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",)),
        limits=Limits(cpu_seconds=1),
        fs=FsPolicy(write_allows=(workspace,)),
    )
    handle = _launch(spec, workload_argv(run_id, "sleep 100"), jail_id="dj-journey", run_id=run_id)
    try:
        verdicts: dict[str, BatteryVerdict] = {
            "env": _probe(handle, env_battery(spec)).battery_verdict,
            "limits": _probe(handle, limits_battery(spec)).battery_verdict,
            "fs_write": _probe(
                handle, fs_write_battery(spec, outside_writable=outside_writable)
            ).battery_verdict,
            "fs_read": _probe(
                handle,
                fs_read_battery(
                    spec,
                    credential_canary=credential_canary,
                    ssh_directory_canary=ssh_directory_canary,
                ),
            ).battery_verdict,
            # task-070 (decision-125): no "network" row. `spec` above declares
            # no ChannelKind.LISTEN channel and grants no
            # spec.network.allowed_domains, so network_battery(spec, ...)
            # would raise ValueError at construction rather than return a
            # Battery -- decision-117's own refusal, which stays (SPEC.md §6's
            # no-work-to-do rule). That refusal is pinned directly, in both
            # directions, by test_network_battery_refuses_a_spec_with_no_network_action
            # and test_network_battery_permits_a_spec_declaring_a_listen_channel
            # below, not re-derived here against a Spec that was never going
            # to grant it a network action.
        }

        assert verdicts["env"] is BatteryVerdict.CONSISTENT, verdicts
        assert verdicts["limits"] is BatteryVerdict.CONSISTENT, verdicts
        honest_unclaimed = (BatteryVerdict.CONSISTENT, BatteryVerdict.VACUOUS)
        assert verdicts["fs_write"] in honest_unclaimed, verdicts
        assert verdicts["fs_read"] in honest_unclaimed, verdicts

        kill_report = handle.kill()
        assert kill_report.items, "kill() must report at least the workload group item"
        for item in kill_report.items:
            assert item.outcome is not KillOutcome.FAILED, (
                f"kill item {item.kind}/{item.identity} FAILED: {item.detail}"
            )
            assert item.outcome in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE), item.outcome
    finally:
        _teardown_group(handle)


@pytest.mark.e2e
def test_network_battery_refuses_a_spec_with_no_network_action() -> None:
    """AC #4, direction 1 (task-070, decision-117 not weakened). A `Spec`
    declaring no `ChannelKind.LISTEN` channel and granting no
    `spec.network.allowed_domains` -- the same network-relevant shape (no
    LISTEN channel, no granted domains, which is all this guard reads) that
    `degraded()`'s journey `spec` above carries, though not identical in its
    other fields -- gives `network_battery` no action the Spec
    provably permits for a positive control (SPEC.md §6's no-work-to-do
    rule), so construction REFUSES rather than shipping a battery that would
    be permanently `VACUOUS` against the preset it was built for. No jail, no
    probe, no launch: this is `network_battery` itself, called directly, the
    same way `test_network_battery_permits_a_spec_declaring_a_listen_channel`
    below calls it for the permitted direction -- together they are the
    control pair this task's AC #4 requires. `denied_address` is a valid
    literal in both directions so the raise under test here is unambiguously
    the network-shape guard, never the separate `denied_address` validation
    that follows it in `brig/probe/batteries/network.py`.
    """
    no_network_spec = Spec()
    with pytest.raises(ValueError) as exc_info:
        network_battery(no_network_spec, denied_address="192.0.2.1:80")
    message = str(exc_info.value)
    # Both missing declarations named, paren-free substrings (the real
    # message is full of parentheses, which are regex-special -- plain `in`
    # on the caught text, not pytest.raises(match=...), per this file's own
    # notes) -- either alone is satisfiable by a weaker guard that dropped
    # one half of decision-117's check.
    assert "no LISTEN channel" in message, message
    assert "spec.network.allowed_domains" in message, message


@pytest.mark.e2e
def test_network_battery_permits_a_spec_declaring_a_listen_channel() -> None:
    """AC #4, direction 2: an otherwise identical `Spec` that DOES declare a
    LISTEN channel does NOT raise. `dataclasses.replace` (stdlib) changes
    only `channels`, so "otherwise identical" to the refusing Spec in
    `test_network_battery_refuses_a_spec_with_no_network_action` above is
    mechanical, not a claim this docstring has to argue. `network_battery` is
    pure (its own module docstring: "no I/O, no clock, no randomness, no
    child processes") -- the endpoint below is never bound or dialed at
    construction, so it need not resolve to anything real on this host.
    """
    no_network_spec = Spec()
    listen_spec = replace(
        no_network_spec,
        channels=(Channel(name="control", kind=ChannelKind.LISTEN, endpoint="/tmp/unused.sock"),),
    )
    battery = network_battery(listen_spec, denied_address="192.0.2.1:80")
    assert battery.name == "network"
    assert len(battery.probes) == 2
