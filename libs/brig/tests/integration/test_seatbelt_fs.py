"""task-060's EC1 file: `seatbelt`'s `fs_write`/`fs_read` enforcement,
observed from INSIDE a real seatbelt jail on darwin -- never asserted about
the argv handed to `sandbox-exec` -- MILESTONES.md M5-lite exit criterion 1
and `.claude/rules/integration-tests.md`'s observation and control rules,
verbatim in this task's own Spec anchor.

Four paired observations, each pair a denial and its own control, every one
made by a JAILED process reporting its own outcome through the launcher's
captured stdio (`handle.stdout_path` / `handle.stderr_path` -- never the
compiled `Step` or the argv passed to `Popen`):

1. write outside every `write_allows` fails / write inside the workspace
   succeeds -- `test_write_outside_write_allows_denied_and_inside_succeeds`.
2. write to `WORKSPACE/.git/hooks/<canary>` fails / write to a sibling path
   INSIDE THE SAME WORKSPACE, in the SAME jail run, succeeds --
   `test_write_denies_carveout_denied_and_sibling_succeeds`.
3. read of a `read_denies` path fails / read of a sibling path NOT in
   `read_denies`, in the SAME run, succeeds --
   `test_read_denies_path_denied_and_sibling_succeeds`.
4. the denial text of pairs 1 and 2 matches `seatbelt`'s own declared
   denial signature, and the same signature does NOT match either pair's
   own successful control output -- asserted INSIDE each of those two test
   functions (both directions), not as a separate probe.

Each pair's two halves run in ONE real `/bin/sh -c` invocation through ONE
real `Stack([seatbelt])` jail (a single `;`-joined script: the denied
command first, then the control command) -- so pairs 2 and 3's "same jail
run" requirement is met by construction, not by convention, and pair 1's
"same test" requirement is trivially a strict subset of that. The denied
command's own shell error (`sh`'s own "cannot create ... Operation not
permitted"/"Operation not permitted" text for a failed redirect-open or a
failed `cat`) lands on the process's real stderr; a later `2>&1` on the SAME
simple command is never reached once the earlier redirect has already
failed to open (POSIX left-to-right redirect application), so it is not
needed and is not used here -- stdout and stderr stay the two cleanly
separated captured streams `IoPolicy`'s default filenames already give us.

MUTATION CHECK 2 (AC #8) is the file's PERMANENT control, same posture as
`tests/integration/test_env_scrub.py`'s own
`test_control_without_env_scrub_the_same_probe_sees_the_secret`: the
IDENTICAL spec and paths pairs 1-3 used above, launched through
`Stack([])` -- seatbelt REMOVED -- chained with `&&` so the whole probe
only reports success if every one of the three previously-denied
operations now succeeds. This is the ongoing, always-green proof that the
denials above are the JAIL's doing and not an accident of this host's own
file permissions (doc-016 deviation 4's own failure shape: a probe that
would pass identically against an unconfined environment proves nothing).

MUTATION CHECK 1 (AC #7 -- removing the offending path from
`spec.fs.write_denies` in THIS FILE's own fixture, in
`test_write_denies_carveout_denied_and_sibling_succeeds`, and re-running)
is the ONE-TIME manual plant/revert against this file itself, done with a
scratch copy and a pasted sha256 per WORKFLOW.md's restoration discipline
-- recorded in this task's Implementation Notes, not as code here (there is
nothing in `Stack([])`, unlike a `write_denies` removal, that this test
file could "restore"; MUTATION CHECK 2 mutates nothing at all, which is why
it is the permanent one).

`sun_path` is not implicated (no channel, no socket) but the jail_dir
convention is followed anyway for consistency with every sibling
integration file: a short `/tmp/bg<pid>sf<n>` scratch root, never
`tmp_path` (CLAUDE.md's trap list). The `sf` infix ("seatbelt fs") is
distinct from `test_seatbelt_smoke.py`'s own `sb` infix so this file's jail
dirs never collide with that sibling's counter in the same pytest session.

Darwin-gated at module level with a visible skip reason: `sandbox-exec` and
SBPL do not exist on any other platform.
"""

from __future__ import annotations

import itertools
import os
import re
import sys

import pytest

from brig.core import FsPolicy, Spec
from brig.mech import Mechanism
from brig.mech.seatbelt import seatbelt
from brig.run.compile_ctx import build_compile_ctx
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="seatbelt/sandbox-exec is darwin-only (SPEC.md §6's seatbelt roster row)",
)

_jail_counter = itertools.count()
_WAIT_TIMEOUT_S = 10.0


def _denial_signature() -> re.Pattern[str]:
    """`seatbelt`'s own declared denial signature (SPEC.md §6: "Seatbelt
    'Operation not permitted'"), fetched from a real compiled `Step` --
    never hand-copied as a literal string -- so this file tests THIS
    mechanism's actual declared signature, not a guess at its wording.
    Computed inside each test function (never at module import time) so
    nothing here runs during collection on a non-darwin host ahead of the
    module-level `skipif`."""
    return seatbelt.compile(
        Spec(), build_compile_ctx(Spec(), jail_dir=_new_jail_dir(), platform="darwin")
    ).denial_signatures[0]


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>sf<n>` -- never `tmp_path`
    (`sun_path` is 104 bytes on darwin). The `sf` infix keeps this file's
    jail dirs from colliding with `test_seatbelt_smoke.py`'s own `sb`
    infix's counter when both run in the same pytest session."""
    return f"/tmp/bg{os.getpid()}sf{next(_jail_counter)}"


def _run_and_capture(
    *,
    jail_dir: str,
    spec: Spec,
    argv: list[str],
    label: str,
    mechanisms: tuple[Mechanism, ...] = (seatbelt,),
) -> tuple[int, str, str]:
    """Compile `spec` through a real `Stack(mechanisms)` (default: just
    `seatbelt`), launch `argv` through the real `SubprocessLauncher`, wait
    for it to exit, and return `(exit_status, stdout_text, stderr_text)`
    read from the jail's own log files -- SPEC.md's "observe from inside
    the jail, not from the outside." `mechanisms=()` is what
    `test_control_stack_with_no_mechanisms_the_same_probes_all_succeed`
    (MUTATION CHECK 2) passes to run the identical probe unconfined."""
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="darwin")
    jail = Stack(mechanisms).compile(spec, ctx=ctx)
    launcher = SubprocessLauncher()
    handle = launcher.launch(
        jail,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"seatbelt-fs-{label}",
        jail_dir=jail_dir,
    )
    status = handle.wait()
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout_text = f.read()
    with open(handle.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr_text = f.read()
    return status, stdout_text, stderr_text


# --------------------------------------------------------------------------
# Pair 1 (AC #3) + half of pair 4 (AC #6): write outside every
# `write_allows` fails, write inside the workspace succeeds -- both halves
# in this one test, run through one real jailed `/bin/sh`.
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_write_outside_write_allows_denied_and_inside_succeeds() -> None:
    """A write to a path that is a SIBLING of the granted workspace (not
    under it, so outside every `write_allows` entry) fails; a write inside
    the workspace, read back via `cat` in the same command, succeeds. Both
    outcomes observed from ONE real jailed process's own captured stdio."""
    signature = _denial_signature()
    jail_dir = _new_jail_dir()
    workspace = f"{jail_dir}/workspace"
    os.makedirs(workspace, exist_ok=True)
    outside_path = f"{jail_dir}/outside.txt"
    inside_path = f"{workspace}/inside.txt"

    spec = Spec(fs=FsPolicy(write_allows=(workspace,)))
    script = f"echo pwned > {outside_path}; echo ok > {inside_path} && cat {inside_path}"
    status, stdout, stderr = _run_and_capture(
        jail_dir=jail_dir,
        spec=spec,
        argv=["/bin/sh", "-c", script],
        label="outside-vs-inside",
    )

    # The control: the inside write (and its immediate read-back) is the
    # LAST command in the `;`-joined script, so a zero overall status plus
    # the exact echoed content is direct, observed proof it ran and
    # succeeded -- not an assumption from a non-error exit code alone.
    assert status == 0, f"inside-workspace write+read unexpectedly failed: {stderr!r}"
    assert stdout == "ok\n"

    # The denial: the outside write's own shell error, captured from the
    # real process's real stderr -- never asserted about argv.
    assert signature.search(stderr) is not None, (
        f"outside-write denial did not match seatbelt's own signature: {stderr!r}"
    )
    # Pair 4, direction 2: the signature must NOT match the control's own
    # successful output.
    assert signature.search(stdout) is None


# --------------------------------------------------------------------------
# Pair 2 (AC #4) + the other half of pair 4 (AC #6): the `.git/hooks`
# carve-out write fails, a sibling write INSIDE THE SAME WORKSPACE, in the
# SAME jail run, succeeds. This is the pair MILESTONES.md singles out.
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_write_denies_carveout_denied_and_sibling_succeeds() -> None:
    """A write under a `write_denies` carve-out (`.git/hooks`, inside a
    granted `write_allows` workspace) fails; a write to a SIBLING path
    inside that SAME workspace, in the SAME jail run, succeeds. The
    sibling is the control that separates "carve-out enforced" from
    "workspace not writable at all" -- MILESTONES.md's own framing of this
    exact pair.

    MUTATION CHECK 1 (AC #7): removing `hooks_dir` from this test's own
    `spec.fs.write_denies` below and re-running turns the carve-out write
    from denied to allowed, so the FIRST signature assertion below goes
    red while the sibling control's assertions stay green -- proving this
    test is discriminating on the carve-out, not on workspace writability
    in general. Done as a one-time scratch-copy plant/revert (WORKFLOW.md),
    recorded with its pasted sha256 in this task's Implementation Notes,
    not left in this file.
    """
    signature = _denial_signature()
    jail_dir = _new_jail_dir()
    workspace = f"{jail_dir}/workspace"
    hooks_dir = f"{workspace}/.git/hooks"
    os.makedirs(hooks_dir, exist_ok=True)
    hooks_path = f"{hooks_dir}/pre-commit"
    sibling_path = f"{workspace}/sibling.txt"

    spec = Spec(fs=FsPolicy(write_allows=(workspace,), write_denies=(hooks_dir,)))
    script = f"echo pwned > {hooks_path}; echo ok > {sibling_path} && cat {sibling_path}"
    status, stdout, stderr = _run_and_capture(
        jail_dir=jail_dir,
        spec=spec,
        argv=["/bin/sh", "-c", script],
        label="carveout-vs-sibling",
    )

    assert status == 0, f"sibling write+read (same workspace) unexpectedly failed: {stderr!r}"
    assert stdout == "ok\n"

    assert signature.search(stderr) is not None, (
        f".git/hooks carve-out denial did not match seatbelt's own signature: {stderr!r}"
    )
    assert signature.search(stdout) is None


# --------------------------------------------------------------------------
# Pair 3 (AC #5): a `read_denies` path read fails, a sibling path NOT in
# `read_denies` reads successfully, both in the same jail run.
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_read_denies_path_denied_and_sibling_succeeds() -> None:
    """Reads default-allow under seatbelt's denylist model (SPEC.md §6):
    a `read_denies` path fails to read, a sibling path NOT named in
    `read_denies` reads successfully -- the control that separates "this
    one path is denied" from "reads are denied everywhere," in one real
    jailed `cat ...; cat ...` run."""
    signature = _denial_signature()
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)
    denied_path = f"{jail_dir}/denied.txt"
    allowed_path = f"{jail_dir}/allowed.txt"
    with open(denied_path, "w", encoding="utf-8") as f:
        f.write("denied-file-content\n")
    with open(allowed_path, "w", encoding="utf-8") as f:
        f.write("allowed-file-content\n")

    spec = Spec(fs=FsPolicy(read_denies=(denied_path,)))
    script = f"cat {denied_path}; cat {allowed_path}"
    status, stdout, stderr = _run_and_capture(
        jail_dir=jail_dir,
        spec=spec,
        argv=["/bin/sh", "-c", script],
        label="read-denied-vs-sibling",
    )

    # The control: the sibling read is the LAST command, so its exact
    # printed content on a zero overall status is direct, observed proof
    # it succeeded -- the denied `cat` above it produced nothing on
    # stdout (its error went to the real stderr instead).
    assert status == 0, f"sibling (not-denied) read unexpectedly failed: {stderr!r}"
    assert stdout == "allowed-file-content\n"
    assert "denied-file-content" not in stdout

    assert signature.search(stderr) is not None, (
        f"read_denies path denial did not match seatbelt's own signature: {stderr!r}"
    )
    assert signature.search(stdout) is None


# --------------------------------------------------------------------------
# MUTATION CHECK 2 (AC #8): the file's PERMANENT control, run every time
# this suite runs. Same three probes as the three tests above, IDENTICAL
# spec shape and path layout, launched through `Stack([])` -- seatbelt
# entirely removed -- chained with `&&` so a zero exit proves every one of
# the three previously-denied operations now succeeds. This is the control
# that proves the tests above observe the JAIL, not an accident of this
# host's own file permissions (the exact defect doc-016 deviation 4 found
# in the probe fixtures: a probe that would pass identically against an
# unconfined environment proves nothing).
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_control_stack_with_no_mechanisms_the_same_probes_all_succeed() -> None:
    """The identical probe shapes from all three pairs above -- a write
    outside a nominal `write_allows`, a write under a nominal `.git/hooks`
    `write_denies` carve-out, and a read of a nominal `read_denies` path --
    run through `Stack([])` instead of `Stack([seatbelt])`. Every one now
    succeeds, proving the denials observed above come from seatbelt's own
    enforcement, not from this host's ordinary file permissions."""
    jail_dir = _new_jail_dir()
    workspace = f"{jail_dir}/workspace"
    hooks_dir = f"{workspace}/.git/hooks"
    os.makedirs(hooks_dir, exist_ok=True)
    outside_path = f"{jail_dir}/outside.txt"
    hooks_path = f"{hooks_dir}/pre-commit"
    denied_read_path = f"{jail_dir}/denied.txt"
    with open(denied_read_path, "w", encoding="utf-8") as f:
        f.write("denied-file-content\n")

    # The SAME spec shape the three enforced tests above used, combined:
    # with no mechanism to enforce it, none of these fields restrict
    # anything -- that is exactly the point of this control.
    spec = Spec(
        fs=FsPolicy(
            write_allows=(workspace,),
            write_denies=(hooks_dir,),
            read_denies=(denied_read_path,),
        )
    )
    script = f"echo pwned > {outside_path} && echo pwned > {hooks_path} && cat {denied_read_path}"
    status, stdout, stderr = _run_and_capture(
        jail_dir=jail_dir,
        spec=spec,
        argv=["/bin/sh", "-c", script],
        label="control-no-mechanisms",
        mechanisms=(),
    )

    assert status == 0, (
        "expected every probe (outside write, .git/hooks write, denied "
        "read) to succeed with NO seatbelt mechanism in the stack, same "
        f"spec that was denied by seatbelt above -- got status={status!r} "
        f"stderr={stderr!r}"
    )
    assert stdout == "denied-file-content\n"
