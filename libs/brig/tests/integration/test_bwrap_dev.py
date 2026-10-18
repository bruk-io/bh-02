"""A bwrap jail's `/dev` is read-only, but for `/dev/shm` (TASK-0079.22, decision-198).

`bwrap --dev /dev` builds `/dev` as a tmpfs of the jail's own, and until a
`--remount-ro` says otherwise it is writable: `touch /dev/x` inside a jail
succeeded, while `fs_write` graded a write outside every write root denied.
It never reached the host, so it was not an escape, but the claim was false,
the same false denial decision-166 fixed for the jail's root tmpfs.

The planted claim is a write to a NEW path directly in `/dev`, which must be refused
with the mechanism's own read-only signature. The test is seen failing before
the fix (the `touch` succeeds) and passing after it.

Its controls are in the same run, one for each thing a workload uses under
`/dev`:

- `/dev/null` is written, and `/dev/zero` and `/dev/urandom` are read, as before;
- `/dev/ptmx` opens (a pty master: `/dev/pts` is devpts, its own mount, which a
  read-only `/dev` does not reach), and `/dev/pts` is there;
- `/dev/tty` is a node. There is no controlling terminal in a test, so it is
  checked as a character device rather than opened;
- `/dev/shm` stays WRITABLE, on purpose. Python's `multiprocessing` creates its
  semaphores there, and a read-only `/dev/shm` makes `multiprocessing.Lock()`
  fail with EROFS (measured). The fix gives `/dev/shm` a tmpfs of its own, so
  the write to it lands here, and that is the one writable directory under `/dev`.
  Like the jail's root tmpfs and `/tmp`, it never reaches the host.

A write in the workspace lands too, so a jail that never ran fails here.
"""

import os
import re
import sys
from pathlib import Path

import pytest

from brig.core import FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run import IoPolicy
from brig.run.compile_ctx import build_compile_ctx
from brig.stack import Stack
from tests.conftest import launch


@pytest.fixture(autouse=True)
def _needs_bubblewrap() -> None:
    if sys.platform != "linux" or not os.path.exists(DEFAULT_BWRAP_PATH):
        pytest.skip(
            f"bwrap needs bubblewrap at {DEFAULT_BWRAP_PATH} on linux "
            f"(sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )


_WAIT_TIMEOUT_S = 30.0
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")


def _denial_signature(jail_dir: str) -> re.Pattern[str]:
    """The mechanism's own declared read-only signature, fetched from a compiled `Step`
    (as `test_bwrap_fs.py` does), never copied as a literal."""
    spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/usr",)))
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    return bwrap.compile(spec, ctx).denial_signatures[0]


@pytest.mark.integration
def test_a_new_path_under_dev_is_refused_and_what_a_workload_uses_there_still_works(
    jail_dir: str,
) -> None:
    workspace = f"{jail_dir}/ws"
    os.makedirs(workspace)
    # A name no host file under /dev carries, so a write that leaked would be seen.
    probe = f"brig-dev-probe-{os.getpid()}"
    host_path = f"/dev/{probe}"
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(p for p in _SYSTEM_ROOTS if os.path.exists(p)),
            write_allows=(workspace,),
        ),
    )
    script = (
        f"touch /dev/{probe} && echo DEV_WROTE; "
        "echo x > /dev/null && echo NULL_OK; "
        '[ "$(head -c 4 /dev/zero | wc -c)" = 4 ] && echo ZERO_OK; '
        '[ "$(head -c 4 /dev/urandom | wc -c)" = 4 ] && echo URANDOM_OK; '
        "[ -c /dev/tty ] && echo TTY_NODE_OK; "
        "[ -d /dev/pts ] && : </dev/ptmx && echo PTMX_OK; "
        f"echo x > /dev/shm/{probe} && echo SHM_OK; "
        f"echo ok > {workspace}/control.txt && echo CONTROL"
    )
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    jail, process = launch(
        Stack([bwrap]).compile(spec, ctx=ctx),
        argv=["/bin/sh", "-c", script],
        cwd=workspace,
        io=IoPolicy(),
        jail_id="bwrap-dev",
        jail_dir=jail_dir,
    )
    try:
        status = process.wait(timeout=_WAIT_TIMEOUT_S)
        stdout = Path(process.stdout_path).read_text(errors="replace")
        stderr = Path(process.stderr_path).read_text(errors="replace")
        leaked = os.path.exists(host_path)
    finally:
        # Ends what is left and waits for it, so the leak sweep never meets the
        # leader still exiting.
        jail.destroy()

    assert not leaked, host_path
    assert status == 0, (stdout, stderr)
    # The claim: a new path directly in /dev is refused with the read-only signature
    # (`/dev/shm`, the one writable directory, is a control below).
    assert "DEV_WROTE" not in stdout, (stdout, stderr)
    assert _denial_signature(jail_dir).search(stderr) is not None, (stdout, stderr)
    # The controls: each thing a workload uses under /dev still works, and so does the
    # workspace, in the same run.
    for token in (
        "NULL_OK",
        "ZERO_OK",
        "URANDOM_OK",
        "TTY_NODE_OK",
        "PTMX_OK",
        "SHM_OK",
        "CONTROL",
    ):
        assert token in stdout, (token, stdout, stderr)
