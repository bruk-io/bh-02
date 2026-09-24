"""task-062: the fs batteries' targets resolve against the HOST at battery
construction, never through the jail's own environment (`doc-016` §7
deviation 4, `doc-016` §9 ask 1, MILESTONES.md M5-lite's "battery
target-resolution fix").

Four things this file proves, each with its own AC:

- **AC #3 / defect 2** -- the write-outside probe's target
  (`outside_writable`) is genuinely writable by an UNJAILED process, so a
  later denial under a real mechanism is attributable to the jail, not to
  a read-only volume (the old target, `/`, is read-only on darwin
  regardless of any jail).
- **AC #4 / defect 3** -- the read-side credential probes' targets
  (`credential_canary`, `ssh_directory_canary`) are seeded by this file
  BEFORE the battery runs and are shown readable unjailed, so absence can
  never masquerade as denial.
- **AC #6** -- the run that proves the above leaves the machine as it
  found it: the scratch root is removed, and nothing landed under the
  real home.
- **AC #9 / AC #10 -- the named regression.** Against `degraded()` (no fs
  mechanism), every fs DENIAL probe now lands `Verdict.FAIL` under a SCRUB
  spec AND a PASS spec, agreeing where the OLD, jail-env-dependent targets
  disagreed. The discriminating control reproduces `doc-016`'s own
  measured pairing by hand, with the retired `"$HOME"/.ssh` target, to
  show the regression this fix retires.

`doc-016` §7 deviation 4's own measured control, reproduced literally by
this file's `test_the_discriminating_control_...` below:

    SCRUB spec (EC1's own):  read_home_ssh_directory -> VACUOUS
        subject='ls: /.ssh: No such file or directory'
    CONTROL, PASS spec:      read_home_ssh_directory -> FAIL
        subject='\\nexit:0'

**Task-065's own half, deliberately NOT pinned here** (decision-079: a task
pins only what it alone owns): the same probes reaching `PASS` under
`scratch_darwin()`.

Every REAL jail this file launches is built through the REAL `degraded()`
preset and the REAL `SubprocessLauncher` -- same "observe from inside the
jail" posture `tests/integration/test_ec1_degraded_batteries.py` already
established, whose helper shapes (`_new_root`, `_launch`, `_teardown_group`)
this file mirrors rather than imports (that file's own helpers are private
module functions, not a shared fixture module).

Short `/tmp/bg<pid>t6<run_id[:8]><n>` scratch roots throughout -- never
`tmp_path` (`sun_path` is 104 bytes on darwin).
"""

from __future__ import annotations

import itertools
import os
import shutil
import subprocess
from collections.abc import Sequence

import pytest

from brig.core import (
    Axis,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    ProbeShape,
    Spec,
    Verdict,
)
from brig.probe.batteries.fs import fs_read_battery, fs_write_battery
from brig.probe.battery import Battery, Expectation, Probe
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack, degraded
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()

#: Bounded deadline for one unjailed `subprocess.run` in this file -- these
#: are `/bin/sh -c` one-liners against local scratch paths, never network.
_UNJAILED_TIMEOUT_S = 10.0


def _new_root(run_id: str, tag: str) -> str:
    """A short scratch root, `/tmp/bg<pid><tag><run_id[:8]><n>` -- never
    `tmp_path` (`sun_path` is 104 bytes on darwin). The `t6` infix (this
    file's own tag below) avoids colliding with a sibling integration
    file's own counter."""
    return f"/tmp/bg{os.getpid()}{tag}{run_id[:8]}{next(_jail_counter)}"


def _launch(stack: Stack, spec: Spec, argv: Sequence[str], *, jail_id: str, run_id: str) -> Handle:
    jail_dir = _new_root(run_id, "t6")
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
    """Hand-rolled group-kill, not `Handle.kill()` -- same reasoning as
    `test_ec1_degraded_batteries.py`'s own `_teardown_group`: a test's
    cleanup path must not be the code under test."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


def _sleep_workload(run_id: str) -> list[str]:
    return workload_argv(run_id, "sleep 100")


def _seed_fs_targets(run_id: str) -> tuple[str, str, str, str]:
    """Build and seed the four scratch paths every fs battery in this file
    needs: `workspace` (spec.fs.write_allows[0]), `outside_writable` (a
    scratch root a genuinely unjailed process can write into),
    `credential_canary` (a FILE, seeded, `read_aws_credentials`' target),
    and `ssh_directory_canary` (a DIRECTORY, seeded with one entry,
    `read_home_ssh_directory`'s target). Returns them in that order."""
    workspace = _new_root(run_id, "btw")
    # `.git/hooks` must exist under the workspace for `write_into_git_hooks_
    # carveout`'s own write to reach a real ENOENT-free attempt against a
    # stack with no fs mechanism -- that probe's target is unchanged by this
    # task's fix (spec-derived, already sound), but AC #9 still needs it to
    # genuinely SUCCEED-when-unenforced like every other DENIAL probe here,
    # not VACUOUS on a missing parent directory this file's own setup owns.
    os.makedirs(os.path.join(workspace, ".git", "hooks"), exist_ok=True)

    outside_writable = _new_root(run_id, "ow")
    os.makedirs(outside_writable, exist_ok=True)

    credential_root = _new_root(run_id, "cc")
    os.makedirs(credential_root, exist_ok=True)
    credential_canary = os.path.join(credential_root, "credentials")
    with open(credential_canary, "w", encoding="utf-8") as f:
        f.write("canary-secret\n")

    ssh_directory_canary = _new_root(run_id, "sd")
    os.makedirs(ssh_directory_canary, exist_ok=True)
    with open(os.path.join(ssh_directory_canary, "known_hosts"), "w", encoding="utf-8") as f:
        f.write("canary-host-key\n")

    return workspace, outside_writable, credential_canary, ssh_directory_canary


# ---------------------------------------------------------------------------
# AC #3 / AC #4 / AC #6 -- targets are real, unjailed process can reach
# them, and the machine is left as it was found.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_write_and_read_targets_are_genuinely_reachable_by_an_unjailed_process_and_cleanup_leaves_no_trace(
    run_id: str,
) -> None:
    """AC #3: the write-outside probe's target is `outside_writable`, and a
    genuinely UNJAILED process (no Stack, no Handle -- `subprocess.run`
    directly against the probe's own argv) can actually write there: exit
    0, and the file it wrote is on disk with the content it wrote. This is
    what makes a LATER denial under a real mechanism attributable to the
    jail, not to a read-only volume -- the old target, `/`, is read-only
    on darwin regardless of any jail, so a DENIAL there would have proven
    nothing.

    AC #4: the read-side credential probes' targets are seeded and shown
    to exist and be readable BEFORE the battery runs -- `credential_canary`
    (a file) and `ssh_directory_canary` (a directory), each asserted
    present with `os.path` right after seeding, then genuinely read by an
    unjailed process (`cat` / `ls`), exit 0, with the seeded content
    actually present in stdout. Absence can never masquerade as denial when
    the target is proven to exist first.

    AC #6: after the run, the scratch root is removed (asserted gone, not
    merely "cleanup attempted"), and none of the probe-written filenames
    exist anywhere under the REAL home -- proving this run never touched
    it, which is the whole point of moving the write targets under
    `outside_writable` in the first place."""
    workspace, outside_writable, credential_canary, ssh_directory_canary = _seed_fs_targets(run_id)

    # AC #4's own wording: assert existence and readability BEFORE running
    # anything, so the seeding itself is the evidence, not an assumption.
    assert os.path.isfile(credential_canary) and os.access(credential_canary, os.R_OK)
    assert os.path.isdir(ssh_directory_canary) and os.access(ssh_directory_canary, os.R_OK)

    spec = Spec(fs=FsPolicy(write_allows=(workspace,)))
    write_battery = fs_write_battery(spec, outside_writable=outside_writable)
    read_battery = fs_read_battery(
        spec, credential_canary=credential_canary, ssh_directory_canary=ssh_directory_canary
    )

    # --- AC #3: the write-outside probe, run UNJAILED. ---
    write_outside = next(p for p in write_battery.probes if p.name == "write_outside_workspace")
    result = subprocess.run(
        list(write_outside.argv), capture_output=True, text=True, timeout=_UNJAILED_TIMEOUT_S
    )
    assert result.returncode == 0, (
        f"an UNJAILED process could not write under outside_writable: "
        f"rc={result.returncode} stderr={result.stderr!r}"
    )
    written = os.path.join(outside_writable, "brig-probe-outside-canary")
    assert os.path.isfile(written)
    with open(written, encoding="utf-8") as f:
        assert f.read() == "x"

    # --- AC #4: both read-side credential probes, run UNJAILED. ---
    read_aws = next(p for p in read_battery.probes if p.name == "read_aws_credentials")
    aws_result = subprocess.run(
        list(read_aws.argv), capture_output=True, text=True, timeout=_UNJAILED_TIMEOUT_S
    )
    assert aws_result.returncode == 0, (
        f"an UNJAILED process could not read the seeded credential_canary: "
        f"rc={aws_result.returncode} stderr={aws_result.stderr!r}"
    )
    assert "canary-secret" in aws_result.stdout

    read_ssh = next(p for p in read_battery.probes if p.name == "read_home_ssh_directory")
    ssh_result = subprocess.run(
        list(read_ssh.argv), capture_output=True, text=True, timeout=_UNJAILED_TIMEOUT_S
    )
    assert ssh_result.returncode == 0, (
        f"an UNJAILED process could not list the seeded ssh_directory_canary: "
        f"rc={ssh_result.returncode} stderr={ssh_result.stderr!r}"
    )
    assert "known_hosts" in ssh_result.stdout

    # --- AC #6: leave the machine as it was found. ---
    shutil.rmtree(outside_writable)
    shutil.rmtree(os.path.dirname(credential_canary))
    shutil.rmtree(ssh_directory_canary)
    shutil.rmtree(workspace)
    assert not os.path.exists(outside_writable)
    assert not os.path.exists(credential_canary)
    assert not os.path.exists(ssh_directory_canary)

    real_home = os.path.expanduser("~")
    # What was checked: none of the filenames this run's probes ever wrote
    # or could have written exist anywhere under the real home -- the whole
    # point of defect 2's fix.
    for relative in (
        "brig-probe-outside-canary",
        "brig-probe-home-ssh-canary",
        os.path.join(".ssh", "brig-probe-canary"),
        os.path.join(".ssh", "brig-probe-outside-canary"),
    ):
        assert not os.path.exists(os.path.join(real_home, relative)), (
            f"a probe wrote under the real home at {relative!r} -- defect 2 is not fixed"
        )


# ---------------------------------------------------------------------------
# AC #9 -- the named regression, first half: FAIL under SCRUB AND under
# PASS, against a stack with no fs mechanism, and the two runs agree.
# ---------------------------------------------------------------------------


def _denial_verdicts(handle: Handle, battery: Battery) -> dict[str, Verdict]:
    from typing import cast

    from brig.core.probes import Battery as CoreBattery

    report = handle.probe(cast(CoreBattery, battery))
    return {
        outcome.probe_name: outcome.verdict
        for outcome in report.outcomes
        if outcome.shape is ProbeShape.DENIAL
    }


@pytest.mark.integration
def test_the_named_regression_first_half_every_fs_denial_probe_fails_under_scrub_and_pass(
    run_id: str,
) -> None:
    """AC #9. MILESTONES.md M5-lite: "the battery target-resolution fix
    ... with the PASS-mode control that exposed the defect as the named
    regression." `doc-016` §7 deviation 4 measured the OLD behaviour as
    `VACUOUS` under a SCRUB spec and `FAIL` under a PASS spec -- two
    different verdicts for what is supposed to be the same probe, because
    the OLD target depended on the jail's own environment.

    This test runs the FIXED `fs_write_battery` / `fs_read_battery`
    against `degraded()` -- `env_scrub` + `rlimits`, NO fs mechanism, so
    every fs DENIAL probe's own attempt genuinely succeeds once nothing
    stops it -- under BOTH a SCRUB spec (the shape `doc-016`'s own EC1
    spec used) and a PASS spec, and asserts every DENIAL probe's OWN
    `Verdict` is `Verdict.FAIL` (SPEC.md §12: "the attempt succeeded; the
    claim is false") under BOTH, PER PROBE. The two runs AGREEING is the
    regression's retirement -- the target no longer depends on which spec
    is in force at all, unlike the discriminating control below, which
    reproduces the OLD disagreement by hand."""
    workspace, outside_writable, credential_canary, ssh_directory_canary = _seed_fs_targets(run_id)
    fs_policy = FsPolicy(write_allows=(workspace,))

    scrub_spec = Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",)), fs=fs_policy)
    pass_spec = Spec(env=EnvPolicy(mode=EnvMode.PASS), fs=fs_policy)

    results: dict[str, dict[str, Verdict]] = {}
    for label, spec in (("scrub", scrub_spec), ("pass", pass_spec)):
        handle = _launch(
            degraded(), spec, _sleep_workload(run_id), jail_id=f"t6-fs-{label}", run_id=run_id
        )
        try:
            write_battery = fs_write_battery(spec, outside_writable=outside_writable)
            read_battery = fs_read_battery(
                spec,
                credential_canary=credential_canary,
                ssh_directory_canary=ssh_directory_canary,
            )
            verdicts: dict[str, Verdict] = {}
            verdicts.update(_denial_verdicts(handle, write_battery))
            verdicts.update(_denial_verdicts(handle, read_battery))
            results[label] = verdicts
        finally:
            _teardown_group(handle)

    # Every DENIAL probe, both batteries, both spec modes: FAIL.
    for label, verdicts in results.items():
        for probe_name, verdict in verdicts.items():
            assert verdict is Verdict.FAIL, (
                f"[{label}] {probe_name}: expected Verdict.FAIL (a stack with no fs "
                f"mechanism cannot stop the attempt), got {verdict!r}"
            )

    # The two runs AGREE, per probe -- the regression's own retirement.
    assert set(results["scrub"]) == set(results["pass"])
    for probe_name in results["scrub"]:
        assert results["scrub"][probe_name] is results["pass"][probe_name], (
            f"{probe_name}: scrub={results['scrub'][probe_name]!r} "
            f"pass={results['pass'][probe_name]!r} -- the two must agree post-fix"
        )

    # Per-probe verdicts, both runs, side by side -- pasted into task-062's
    # own implementation notes verbatim from a real run.
    print("\nscrub:", results["scrub"])
    print("pass: ", results["pass"])


# ---------------------------------------------------------------------------
# AC #10 -- the discriminating control: doc-016's OWN pre-fix pairing,
# reproduced by hand, READ-shaped only.
# ---------------------------------------------------------------------------


def _pre_fix_control_battery(workspace: str) -> Battery:
    """Hand-built, reproducing `doc-016` §7 deviation 4's own pre-fix shape
    VERBATIM -- the literal shell text `"$HOME"/.ssh`, built here by hand,
    never through `fs_read_battery` (which no longer emits it -- this is
    exactly what makes this a discriminating control on the FIX, not a
    duplicate of the fixed battery). READ-shaped only, per task-062 AC
    #10: reproducing the old defect must never write into the real home."""
    return Battery(
        name="fs_read_pre_fix_control",
        axis=Axis.FS_READ,
        probes=(
            Probe(
                name="read_a_workspace_file",
                shape=ProbeShape.CONTROL,
                axis=Axis.FS_READ,
                argv=(
                    "/bin/sh",
                    "-c",
                    'printf brig-ok > "$0"/brig-probe-readable && cat "$0"/brig-probe-readable',
                    workspace,
                ),
                expect=Expectation(token="brig-ok"),
            ),
            Probe(
                name="read_home_ssh_directory_pre_fix",
                shape=ProbeShape.DENIAL,
                axis=Axis.FS_READ,
                argv=("/bin/sh", "-c", 'ls "$HOME"/.ssh'),
                expect=Expectation(),
            ),
        ),
    )


@pytest.mark.integration
def test_the_discriminating_control_reproduces_doc_016_deviation_4_exactly(
    run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC #10. The pre-fix control, `_pre_fix_control_battery` above,
    targets the literal retired string `"$HOME"/.ssh` -- READ-shaped, so
    reproducing the old defect can never write into the real home. This is
    what the fixed batteries retire (the test above): under a SCRUB spec
    HOME is scrubbed and the probe targets `/.ssh`, `ENOENT`, no signature
    claim on `degraded()`'s fs axis -> `Verdict.VACUOUS`; under a PASS
    spec HOME survives and the probe reaches the real `~/.ssh`, succeeds
    -> `Verdict.FAIL`, reproducing `doc-016` §7 deviation 4's own measured
    pairing exactly:

        SCRUB: read_home_ssh_directory -> VACUOUS
        PASS:  read_home_ssh_directory -> FAIL

    **HOME is pointed at a `.ssh` this test creates, and is not the
    operator's own** (2026-09-08). This assertion used to read the REAL
    `~/.ssh` and fail loudly on a host without one -- which is what it did
    the first time this suite ran on linux, in a container whose user has
    no `~/.ssh`, and would do on any CI runner that does not ship one. The
    pairing under test is about HOME SURVIVING `PASS` and being SCRUBBED
    otherwise, not about whose home it is: the launcher hands the workload
    this process's own environment, so pointing HOME at a directory this
    test made -- with a listable `.ssh` inside it -- reproduces doc-016's
    measurement exactly and depends on no fact about the host. The
    assertion below is kept, and is now about a directory whose existence
    this test is responsible for."""
    fake_home = _new_root(run_id, "hm")
    real_ssh = os.path.join(fake_home, ".ssh")
    os.makedirs(real_ssh, exist_ok=True)
    monkeypatch.setenv("HOME", fake_home)
    assert os.path.isdir(real_ssh) and os.access(real_ssh, os.R_OK), (
        f"this control depends on a listable ~/.ssh ({real_ssh!r}) -- "
        f"doc-016's own measured pairing assumed the same"
    )

    workspace = _new_root(run_id, "btp")
    os.makedirs(workspace, exist_ok=True)

    scrub_spec = Spec(
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",)),
        fs=FsPolicy(write_allows=(workspace,)),
    )
    pass_spec = Spec(env=EnvPolicy(mode=EnvMode.PASS), fs=FsPolicy(write_allows=(workspace,)))

    outcomes: dict[str, Verdict] = {}
    for label, spec in (("scrub", scrub_spec), ("pass", pass_spec)):
        handle = _launch(
            degraded(), spec, _sleep_workload(run_id), jail_id=f"t6-pf-{label}", run_id=run_id
        )
        try:
            verdicts = _denial_verdicts(handle, _pre_fix_control_battery(workspace))
            outcomes[label] = verdicts["read_home_ssh_directory_pre_fix"]
        finally:
            _teardown_group(handle)

    print("\npre-fix control -- scrub:", outcomes["scrub"], "pass:", outcomes["pass"])
    assert outcomes["scrub"] is Verdict.VACUOUS, (
        f"expected VACUOUS (HOME scrubbed -> ENOENT, no signature claim), got {outcomes['scrub']!r}"
    )
    assert outcomes["pass"] is Verdict.FAIL, (
        f"expected FAIL (HOME survives -> real ~/.ssh reached, attempt succeeds), got "
        f"{outcomes['pass']!r}"
    )
