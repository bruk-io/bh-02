"""`seatbelt` against the real darwin sandbox kernel: task-059's ONE
observed integration test file, covering two distinct claims.

**AC #5 -- the `jail_dir` resolution, observed rather than assumed.**
`brig.run.compile_ctx.build_compile_ctx` (task-059's run-layer helper)
realpaths `jail_dir` itself before constructing a `CompileCtx` -- this is
real OS symlink-resolution behavior (darwin's `/tmp` -> `/private/tmp`),
not something the unit tier can observe without faking the filesystem
away, which would test nothing (`.claude/rules/integration-tests.md`).

**AC #8/#9's SMOKE, observed from inside the jail rather than asserted
about argv.** A real `/bin/sh`, launched through a real `Stack([seatbelt])`
via the real `SubprocessLauncher`, attempts three writes: one OUTSIDE
`write_allows` entirely (AC #8's own literal wording), one under a
`write_denies` CARVE-OUT inside `write_allows` (so AC #10's own mutation --
"delete the write_denies emission ... and the SMOKE test goes red" -- has
something to bite: a write outside `write_allows` entirely is denied by
the untouched default-deny line regardless of `write_denies`, so it alone
cannot falsify that specific mutation), and one INSIDE `write_allows` and
NOT carved out, which must SUCCEED -- the control
`.claude/rules/integration-tests.md` requires for every denial assertion
("the same probe against an allowed path... succeeds"), and the exact
observable AC #11's own mutation needs: an unresolved `jail_dir` turns a
correctly-targeted ALLOW rule into one that can no longer match the real
(symlink-resolved) path the kernel checks against, so the CONTROL write is
what would flip from success to denial.

No LISTEN channel anywhere in this file: socket-bind behavior is
task-061's own observed instrument, out of this task's scope.

`sun_path` is not implicated here (no channel, no socket) but the jail_dir
convention is followed anyway for consistency with every other integration
file: a short `/tmp/bg<pid>sb<n>` scratch root, never `tmp_path`
(CLAUDE.md's trap list; the `sb` infix -- "seatbelt" -- avoids colliding
with a sibling integration file's own counter, matching
`tests/integration/test_env_scrub.py::_new_jail_dir`'s own convention).

Darwin-gated at module level with a visible skip reason (the e2e tier's
"skips are visible" rule, applied here even though this file is
integration-tier rather than e2e, because the same honesty requirement
applies): `sandbox-exec` and SBPL do not exist on
any other platform.
"""

from __future__ import annotations

import itertools
import os
import sys

import pytest

from brig.core import FsPolicy, Spec
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


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>sk<n>` -- never `tmp_path`. The
    `sk` infix keeps this file's jail dirs from colliding with another
    integration file's own counter (same convention as
    `test_env_scrub.py::_new_jail_dir`'s `es` infix)."""
    return f"/tmp/bg{os.getpid()}sk{next(_jail_counter)}"


def _run_seatbelt_and_capture(
    *, jail_dir: str, spec: Spec, argv: list[str], label: str
) -> tuple[int, str, str]:
    """Compile `spec` through a real `Stack([seatbelt])`, launch `argv`
    through the real `SubprocessLauncher`, wait for it to exit, and return
    `(exit_status, stdout_text, stderr_text)`, read from the jail's own log
    files -- SPEC.md's "observe from inside the jail, not from the
    outside." `label` disambiguates the `jail_id` across the several
    launches this file's one test performs against distinct jail dirs."""
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="darwin")
    jail = Stack([seatbelt]).compile(spec, ctx=ctx)
    launcher = SubprocessLauncher()
    handle = launcher.launch(
        jail,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"seatbelt-smoke-{label}",
        jail_dir=jail_dir,
    )
    status = handle.wait()
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout_text = f.read()
    with open(handle.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr_text = f.read()
    return status, stdout_text, stderr_text


# --------------------------------------------------------------------------
# AC #5: the jail_dir resolution, observed rather than assumed.
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_build_compile_ctx_resolves_jail_dir_to_its_own_realpath() -> None:
    """`build_compile_ctx` (the run-layer helper task-059's Deliverable
    names) realpaths `jail_dir` itself before constructing the
    `CompileCtx`: the resulting `ctx.jail_dir` is the `/private/tmp` form
    on darwin, equal to `os.path.realpath` of the raw `/tmp` root handed
    in. The control -- raw root and resolved root are different STRINGS --
    is what keeps this assertion non-vacuous on a host where `/tmp` and
    its realpath happen to coincide (this repo's own darwin host never
    does, but the control makes that an observed fact, not an assumption)."""
    jail_dir = _new_jail_dir()
    ctx = build_compile_ctx(Spec(), jail_dir=jail_dir, platform="darwin")

    assert ctx.jail_dir == os.path.realpath(jail_dir)
    # Control: not vacuous -- the raw and resolved forms actually differ.
    assert ctx.jail_dir != jail_dir
    assert ctx.jail_dir.startswith("/private/tmp/")


# --------------------------------------------------------------------------
# AC #8/#9: the SMOKE, plus its required control (integration-tests.md:
# "every denial assertion ships with its control").
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_smoke_denied_writes_match_signature_and_the_allowed_write_succeeds() -> None:
    """Three real, separately-jailed `/bin/sh` launches:

    1. A write OUTSIDE `write_allows` entirely -- denied, and the captured
       stderr matches `seatbelt`'s own declared denial signature (AC #8's
       literal wording).
    2. A write under a `write_denies` CARVE-OUT inside `write_allows` --
       also denied, matching the same signature. This is the write AC
       #10's mutation (dropping the write_denies emission) targets: case 1
       above is denied by the untouched default-deny line regardless of
       that mutation, so case 1 alone could not falsify it.
    3. The CONTROL: a write INSIDE `write_allows` and NOT carved out --
       succeeds. Required by `.claude/rules/integration-tests.md`
       ("every denial assertion ships with its control"), and also the
       exact observable AC #11's jail_dir-resolution mutation would flip
       (an unresolved jail_dir makes even a correctly-targeted ALLOW rule
       fail to match the kernel's own symlink-resolved path check).
    """
    pattern = seatbelt.compile(
        Spec(), build_compile_ctx(Spec(), jail_dir=_new_jail_dir(), platform="darwin")
    ).denial_signatures[0]

    # --- Case 1: outside write_allows entirely -------------------------
    jail_dir_outside = _new_jail_dir()
    os.makedirs(jail_dir_outside, exist_ok=True)
    spec_outside = Spec(fs=FsPolicy(write_allows=(f"{jail_dir_outside}/workspace",)))
    status_outside, _stdout_outside, stderr_outside = _run_seatbelt_and_capture(
        jail_dir=jail_dir_outside,
        spec=spec_outside,
        argv=["/bin/sh", "-c", f"echo pwned > {jail_dir_outside}/outside.txt"],
        label="outside",
    )
    assert status_outside != 0
    assert pattern.search(stderr_outside) is not None, (
        f"case 1 (outside write_allows) stderr did not match denial signature: {stderr_outside!r}"
    )

    # --- Case 2: a write_denies carve-out inside write_allows -----------
    jail_dir_carveout = _new_jail_dir()
    workspace = f"{jail_dir_carveout}/workspace"
    hooks_dir = f"{workspace}/.git/hooks"
    os.makedirs(hooks_dir, exist_ok=True)
    spec_carveout = Spec(fs=FsPolicy(write_allows=(workspace,), write_denies=(hooks_dir,)))
    status_carveout, _stdout_carveout, stderr_carveout = _run_seatbelt_and_capture(
        jail_dir=jail_dir_carveout,
        spec=spec_carveout,
        argv=["/bin/sh", "-c", f"echo pwned > {hooks_dir}/pre-commit"],
        label="carveout",
    )
    assert status_carveout != 0
    assert pattern.search(stderr_carveout) is not None, (
        f"case 2 (write_denies carve-out) stderr did not match denial signature: "
        f"{stderr_carveout!r}"
    )

    # --- Case 3: the control -- inside write_allows, not carved out -----
    jail_dir_control = _new_jail_dir()
    workspace_control = f"{jail_dir_control}/workspace"
    os.makedirs(workspace_control, exist_ok=True)
    spec_control = Spec(fs=FsPolicy(write_allows=(workspace_control,)))
    status_control, stdout_control, stderr_control = _run_seatbelt_and_capture(
        jail_dir=jail_dir_control,
        spec=spec_control,
        argv=[
            "/bin/sh",
            "-c",
            f"echo ok > {workspace_control}/file.txt && cat {workspace_control}/file.txt",
        ],
        label="control",
    )
    assert status_control == 0, (
        f"control write (inside write_allows, not carved out) unexpectedly failed: "
        f"status={status_control!r} stderr={stderr_control!r}"
    )
    assert stdout_control == "ok\n"
    assert pattern.search(stderr_control) is None
