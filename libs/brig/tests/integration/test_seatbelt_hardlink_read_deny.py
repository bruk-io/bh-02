"""TASK-0048's spike, against the real darwin sandbox kernel: does
`os.link` let a jailed process read a `read_denies` source by giving it a
second, undenied name?

Seatbelt's `fs_read` is a denylist (SPEC.md Sec.4/Sec.6): `(allow file-read*
(subpath "/"))` then a per-`read_denies` `(deny file-read* (subpath
"RESOLVED"))`. That deny is PATH-based, so a hard link at a *different*
path is, in principle, a different `(deny ...)` match entirely -- the
question this file answers empirically rather than assuming either way
(SPEC.md Sec.4: "field evidence ... says cooperative filesystem guarding
fails reliably").

**The matrix that matters is the source's `write_allows` membership, not
just its `read_denies` membership** -- a scratch spike run against a
hand-written profile (not shipped, not this file) found `os.link` denied
even when its source sat OUTSIDE `write_allows` and was NOT itself
`read_denies`, which only shows hard-linking needs some permission on the
source, not which one. The cell that actually answers TASK-0048's question
is a `read_denies` source **inside** `write_allows` -- the exact shape
SPEC.md Sec.6 already describes for `.envrc` and `.git/hooks` carve-outs --
linked to an undenied name in the same tree, with the required control
(`.claude/rules/integration-tests.md`'s "every denial assertion ships with
its control", `test_seatbelt_smoke.py`'s same pattern): the identical
shape with an undenied source, which must both link and read back, so a
jail that denies everything would not pass this file vacuously.

Darwin-gated at module level, visible skip reason, same as every other
seatbelt integration file here: `sandbox-exec`/SBPL do not exist elsewhere.
"""

from __future__ import annotations

import os
import sys

import pytest

from brig.core import FsPolicy, Spec
from brig.mech.seatbelt import seatbelt
from brig.run import IoPolicy
from brig.run.compile_ctx import build_compile_ctx
from brig.stack import Stack
from tests.conftest import NewJailDir, launch

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="seatbelt/sandbox-exec is darwin-only (SPEC.md Sec.6's seatbelt roster row)",
)

_WAIT_TIMEOUT_S = 10.0

_LINK_PROGRAM = (
    "import os\n"
    "os.link({source!r}, {dest!r})\n"
    "print('LINK_OK')\n"
    "with open({dest!r}, encoding='utf-8') as f:\n"
    "    print(f'READ_VIA_LINK:{{f.read()}}')\n"
)


def _run_hardlink_attempt(
    *, jail_dir: str, spec: Spec, source: str, dest: str, label: str
) -> tuple[int, str, str]:
    """Compile `spec` through a real `Stack([seatbelt])`, launch the real
    Python interpreter running `_LINK_PROGRAM` through the real
    `Jail.create`/`jail.start`, wait for it to exit, and return
    `(exit_status, stdout_text, stderr_text)` read from the jail's own log
    files -- the same observe-from-inside pattern `test_seatbelt_smoke.py`
    uses. `label` disambiguates the `jail_id` across this file's several
    launches."""
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="darwin")
    jail = Stack([seatbelt]).compile(spec, ctx=ctx)
    jail, process = launch(
        jail,
        argv=[sys.executable, "-c", _LINK_PROGRAM.format(source=source, dest=dest)],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=f"seatbelt-hardlink-{label}",
        jail_dir=jail_dir,
    )
    status = process.wait()
    with open(process.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout_text = f.read()
    with open(process.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr_text = f.read()
    return status, stdout_text, stderr_text


@pytest.mark.integration
def test_hardlink_of_read_denied_source_is_denied_with_control(
    new_jail_dir: NewJailDir,
) -> None:
    """A `read_denies` entry **inside `write_allows`** (SPEC.md Sec.6's own
    `.envrc`/`.git/hooks` carve-out shape) is the source of a hard link to
    an undenied name in the same writable tree. If the link succeeded, the
    new name would carry no `read_denies` entry of its own and the content
    would read straight through -- the bypass TASK-0048 asks about. The
    control is the identical shape with the source NOT in `read_denies`:
    required to both link and read back, so the jailed process and the
    launch itself are shown working before the denial is trusted."""
    pattern = seatbelt.compile(
        Spec(), build_compile_ctx(Spec(), jail_dir=new_jail_dir(), platform="darwin")
    ).denial_signatures[0]

    # --- The claim: source is read_denies, inside write_allows ----------
    jail_dir_denied = new_jail_dir()
    workspace_denied = f"{jail_dir_denied}/workspace"
    os.makedirs(workspace_denied, exist_ok=True)
    secret = f"{workspace_denied}/secret.env"
    with open(secret, "w", encoding="utf-8") as f:
        f.write("TOP_SECRET=1\n")
    linked = f"{workspace_denied}/not_denied.txt"

    spec_denied = Spec(
        fs=FsPolicy(write_allows=(workspace_denied,), read_denies=(secret,)),
    )
    status_denied, stdout_denied, stderr_denied = _run_hardlink_attempt(
        jail_dir=jail_dir_denied,
        spec=spec_denied,
        source=secret,
        dest=linked,
        label="denied",
    )
    assert status_denied != 0, (
        f"os.link of a read_denies source succeeded inside brig's seatbelt jail: "
        f"stdout={stdout_denied!r} stderr={stderr_denied!r}"
    )
    assert pattern.search(stderr_denied) is not None, (
        f"hard-link denial did not match seatbelt's own denial signature: {stderr_denied!r}"
    )
    assert not os.path.exists(linked), (
        "the destination name exists on the host even though the jailed os.link call failed"
    )

    # --- The control: identical shape, source NOT in read_denies ---------
    jail_dir_control = new_jail_dir()
    workspace_control = f"{jail_dir_control}/workspace"
    os.makedirs(workspace_control, exist_ok=True)
    plain = f"{workspace_control}/plain.env"
    with open(plain, "w", encoding="utf-8") as f:
        f.write("not secret\n")
    linked_control = f"{workspace_control}/also_not_denied.txt"

    spec_control = Spec(fs=FsPolicy(write_allows=(workspace_control,)))
    status_control, stdout_control, stderr_control = _run_hardlink_attempt(
        jail_dir=jail_dir_control,
        spec=spec_control,
        source=plain,
        dest=linked_control,
        label="control",
    )
    assert status_control == 0, (
        f"control hard link (source not in read_denies) unexpectedly failed: "
        f"status={status_control!r} stderr={stderr_control!r}"
    )
    assert "LINK_OK" in stdout_control
    assert "READ_VIA_LINK:not secret\n" in stdout_control
    assert pattern.search(stderr_control) is None
