"""A bwrap jail started as ROOT holds no capabilities (decision-177).

Run as root, bwrap 0.9 maps the jail's uid 0 to the host's uid 0 and, unless
told otherwise, leaves the workload every capability over its own user and
mount namespaces. That made each read-only bind a suggestion: the workload
remounted one read-write and wrote through it to the host (found by
TASK-0079.01's review on the host's `/etc`), read root-owned files whatever
their mode (CAP_DAC_OVERRIDE), and, being the host's uid 0, wrote sysctls,
whose permission check is the mode bits alone. The fix is two flags in
stage 1 and 2 of the render: `--cap-drop ALL` and `/proc/sys` bound
read-only.

**Only the test's own scratch directory is ever planted.** The read-only
tree the jail tries to unlock is a directory under this test's `tmp_path`,
so if the hole is open the host write lands there; the sysctl probe writes
`kernel.hostname`, which belongs to the jail's own UTS namespace
(`--unshare-all`), so even an open hole changes nothing outside the jail.

Each denial has its control in the same run: a write in the workspace lands
and a readable file in the read-only tree reads, so a jail that never ran
and one that denied everything both fail here.

**Root only, and skipped visibly otherwise.** An unprivileged user's bwrap
leaves no capabilities and maps the jail to a uid that is not the host's
root, so there is no hole to plant: the test would pass on an unconfined
jail too.
"""

import itertools
import os
import shutil
import sys
from pathlib import Path

import pytest

from brig.core import FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run.compile_ctx import build_compile_ctx
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack

_jail_counter = itertools.count()
_WAIT_TIMEOUT_S = 30.0
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")
_NO_CAPS = "0000000000000000"


@pytest.fixture(autouse=True)
def _needs_bubblewrap_as_root() -> None:
    if sys.platform != "linux" or not os.path.exists(DEFAULT_BWRAP_PATH):
        pytest.skip(
            f"bwrap needs bubblewrap at {DEFAULT_BWRAP_PATH} on linux "
            f"(sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )
    if os.geteuid() != 0:
        pytest.skip(
            "the root-capability hole only exists when bwrap runs as root "
            f"(euid is {os.geteuid()}): an unprivileged bwrap leaves no "
            "capabilities, so this test would pass against an unconfined jail; "
            "run the suite as root to exercise it"
        )


def _status_field(stdout: str, name: str) -> str:
    """The value of `name:` in the `/proc/self/status` lines the jail printed."""
    for line in stdout.splitlines():
        key, _, value = line.partition(":")
        if key == name:
            return value.strip()
    raise AssertionError(f"no {name!r} line in the jail's stdout: {stdout!r}")


@pytest.mark.integration
def test_a_jail_started_as_root_holds_no_capabilities_and_cannot_unlock_a_read_only_bind(
    tmp_path: Path,
) -> None:
    ro = tmp_path / "ro"
    ro.mkdir()
    (ro / "readable").write_text("READABLE\n")
    locked = ro / "locked"
    locked.write_text("LOCKEDVALUE\n")
    locked.chmod(0o000)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    planted = ro / "planted"

    jail_dir = f"/tmp/bg{os.getpid()}rc{next(_jail_counter)}"
    os.makedirs(jail_dir)
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=(*(p for p in _SYSTEM_ROOTS if os.path.exists(p)), str(ro)),
            write_allows=(str(workspace),),
        )
    )
    script = (
        "grep -E '^Cap(Eff|Bnd):' /proc/self/status; "
        f"/bin/mount -o remount,bind,rw {ro}; echo REMOUNT=$?; "
        f"/usr/bin/touch {planted}; echo PLANT=$?; "
        f"/bin/cat {locked}; echo LOCKED=$?; "
        "echo jailhost > /proc/sys/kernel/hostname; echo SYSCTL=$?; "
        f"/bin/cat {ro}/readable; "
        f"echo ok > {workspace}/control && echo CONTROL"
    )
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    handle = SubprocessLauncher().launch(
        Stack([bwrap]).compile(spec, ctx=ctx),
        argv=["/bin/sh", "-c", script],
        cwd=str(workspace),
        io=IoPolicy(),
        jail_id="bwrap-root-confined",
        jail_dir=jail_dir,
    )
    try:
        status = handle.wait(timeout=_WAIT_TIMEOUT_S)
        stdout = Path(handle.stdout_path).read_text(errors="replace")
        stderr = Path(handle.stderr_path).read_text(errors="replace")
        host_write_landed = planted.exists()
    finally:
        # Ends what is left and waits for it, so the leak sweep never meets the
        # leader still exiting (a race seen 2 times in 12 without it).
        handle.kill()
        planted.unlink(missing_ok=True)
        shutil.rmtree(jail_dir, ignore_errors=True)

    # The controls: the jail ran, wrote its workspace and read its tree.
    assert status == 0, (stdout, stderr)
    assert "CONTROL" in stdout and (workspace / "control").is_file(), (stdout, stderr)
    assert "READABLE" in stdout, (stdout, stderr)

    # The claims.
    assert _status_field(stdout, "CapEff") == _NO_CAPS, stdout
    assert _status_field(stdout, "CapBnd") == _NO_CAPS, stdout
    assert "REMOUNT=0" not in stdout, (stdout, stderr)
    assert "PLANT=0" not in stdout and not host_write_landed, (stdout, stderr)
    assert "LOCKEDVALUE" not in stdout and "LOCKED=0" not in stdout, (stdout, stderr)
    assert "SYSCTL=0" not in stdout, (stdout, stderr)
