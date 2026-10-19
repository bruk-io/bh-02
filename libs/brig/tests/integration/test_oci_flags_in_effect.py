"""The flags `Oci` compiles, observed from inside a real container (decision-202).

`tests/unit/test_oci_compile.py` pins the flags and `test_oci_runtime.py` reads them back from
`docker inspect`; this file shows they confine anything. Each probe is `docker exec` into the
container by the test's own door (`tests/oci_jail.py`), never through the runtime under test, and
each denial has its control in the same test: the allowed case, run in the same container, that
shows the probe could have succeeded.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from brig.core import Axis, Limits, Spec
from brig.mech import Oci
from brig.run import Jail, build_compile_ctx
from brig.stack import Stack
from tests.conftest import NewJailDir
from tests.oci_jail import IMAGE, allow_list, container_of, docker, exec_in

pytestmark = pytest.mark.integration

Make = Callable[..., Jail]

_EROFS = "Read-only file system"


@dataclasses.dataclass(frozen=True, slots=True)
class _Tree:
    """The host side of the spec under test: a read-only reference, a workspace with its
    carve-outs, and the Spec over them."""

    reference: str
    workspace: str
    spec: Spec

    @property
    def hooks(self) -> str:
        return f"{self.workspace}/.git/hooks"

    @property
    def protected(self) -> str:
        return f"{self.workspace}/protected.txt"

    @property
    def absent(self) -> str:
        return f"{self.workspace}/.envrc"

    @property
    def secret(self) -> str:
        return f"{self.workspace}/local.env"

    @property
    def private(self) -> str:
        return f"{self.workspace}/private"


@pytest.fixture
def tree(new_jail_dir: NewJailDir) -> _Tree:
    reference = new_jail_dir()
    workspace = new_jail_dir()
    Path(reference, "f.txt").write_text("reference\n")
    os.makedirs(f"{workspace}/.git/hooks")
    os.makedirs(f"{workspace}/private")
    Path(workspace, "ok.txt").write_text("readable\n")
    Path(workspace, "protected.txt").write_text("protected\n")
    Path(workspace, "local.env").write_text("TOP-SECRET\n")
    Path(workspace, "private", "a.txt").write_text("private\n")
    spec = Spec(
        fs=allow_list(
            read_allows=(reference,),
            write_allows=(workspace,),
            write_denies=(
                f"{workspace}/.git/hooks",
                f"{workspace}/protected.txt",
                f"{workspace}/.envrc",
            ),
            read_denies=(f"{workspace}/local.env", f"{workspace}/private"),
        ),
        limits=Limits(cpu_seconds=1),
    )
    return _Tree(reference, workspace, spec)


def _out(container: str, script: str) -> tuple[int, str]:
    done = exec_in(container, script)
    return done.returncode, (done.stdout + done.stderr).strip()


def test_a_write_root_is_writable_as_the_embedder_and_nothing_else_is(
    make_oci_jail: Make, tree: _Tree
) -> None:
    container = container_of(make_oci_jail(tree.spec))
    # The control: the write root takes a write, owned on the host by the embedder's uid.
    assert _out(container, f"echo from-inside > {tree.workspace}/new.txt")[0] == 0
    assert os.stat(f"{tree.workspace}/new.txt").st_uid == os.geteuid()
    assert _out(container, "id -u") == (0, str(os.geteuid()))
    # The denials: the read-only reference, the container's root, an unmounted path.
    for target in (f"{tree.reference}/y", "/x", "/etc/brig", "/usr/brig"):
        code, text = _out(container, f"touch {target}")
        assert code != 0 and _EROFS in text, (target, text)
    # A path in /tmp, which a bwrap-like jail would not have: the root is read-only and /tmp is not
    # granted (SPEC.md §5: no shared /tmp).
    code, text = _out(container, "touch /tmp/brig")
    assert code != 0 and _EROFS in text
    # What stays writable and never reaches the host is named in the grade (below): /dev/shm.
    assert _out(container, "touch /dev/shm/brig")[0] == 0


def test_the_grade_names_what_stays_writable(make_oci_jail: Make, tree: _Tree) -> None:
    jail = make_oci_jail(tree.spec)
    detail = jail.report.axes[Axis.FS_WRITE].detail
    assert "/dev/shm" in detail and "/dev (a tmpfs" in detail and "ON THE HOST" in detail


def test_the_write_carve_outs_hold_and_leave_what_the_grade_says_they_leave(
    make_oci_jail: Make, tree: _Tree
) -> None:
    container = container_of(make_oci_jail(tree.spec))
    # Existing file: still readable (a write deny asks no more), not writable.
    assert _out(container, f"cat {tree.protected}") == (0, "protected")
    code, text = _out(container, f"echo x >> {tree.protected}")
    assert code != 0 and _EROFS in text
    # Existing directory: the hooks cannot be added to ...
    code, text = _out(container, f"touch {tree.hooks}/pre-commit")
    assert code != 0 and _EROFS in text
    # ... and the control, a sibling in the same write root, can.
    assert _out(container, f"touch {tree.workspace}/.git/config")[0] == 0
    # Absent path: an empty read-only directory appears, nothing can be created at or in it.
    assert _out(container, f"test -d {tree.absent} && echo dir") == (0, "dir")
    code, text = _out(container, f"touch {tree.absent}/x")
    assert code != 0 and _EROFS in text
    # ... and its mount point was made ON THE HOST, as the grade's detail says, and outlives the jail.
    assert os.path.isdir(tree.absent) and os.listdir(tree.absent) == []
    assert not os.path.exists(f"{tree.hooks}/pre-commit")


def test_the_read_carve_outs_mask_what_exists_inside_a_root(
    make_oci_jail: Make, tree: _Tree
) -> None:
    container = container_of(make_oci_jail(tree.spec))
    # The control: a file beside the masked one reads; the secret is really on the host.
    assert _out(container, f"cat {tree.workspace}/ok.txt") == (0, "readable")
    assert Path(tree.secret).read_text() == "TOP-SECRET\n"
    # The masked file reads as nothing. A write to it is accepted and goes to the null device it
    # is bound to (Docker's binds are not `nodev`, so unlike bwrap's mask it is not EACCES): the
    # host's file is as it was, below.
    assert _out(container, f"cat {tree.secret}") == (0, "")
    assert _out(container, f"echo overwritten > {tree.secret}")[0] == 0
    # The masked directory cannot be listed or read into, even by root (it holds no capability).
    code, text = _out(container, f"ls {tree.private}")
    assert code != 0 and "Permission denied" in text
    code, _ = _out(container, f"cat {tree.private}/a.txt")
    assert code != 0
    assert Path(tree.secret).read_text() == "TOP-SECRET\n"  # the host's file is as it was


def test_the_pins_keep_a_directory_with_a_carve_out_in_it_from_being_renamed_away(
    make_oci_jail: Make, tree: _Tree, new_jail_dir: NewJailDir
) -> None:
    """decision-168 on Docker: `mv .git .git-moved` would let the workload build a new `.git` with
    a hooks directory of its own where a host `git` reads it. With the pin it is busy; without, in
    a container made from the same flags minus the pin, it is not (the control)."""
    container = container_of(make_oci_jail(tree.spec))
    code, text = _out(container, f"mv {tree.workspace}/.git {tree.workspace}/.git-moved")
    assert code != 0 and "busy" in text.lower(), text
    assert os.path.isdir(f"{tree.workspace}/.git/hooks")

    ctx = build_compile_ctx(tree.spec, jail_dir=new_jail_dir(), platform=sys.platform)
    plan = Stack([Oci(IMAGE, interpreter=None)]).compile(tree.spec, ctx=ctx).container
    assert plan is not None
    pin = f"type=bind,src={tree.workspace}/.git,dst={tree.workspace}/.git"
    assert pin in plan.flags
    without = list(plan.flags)
    at = without.index(pin)
    del without[at - 1 : at + 1]  # the --mount and its value
    env_file = f"{ctx.jail_dir}/control.env"
    Path(env_file).write_text("")
    os.makedirs(
        plan.channel_dir
    )  # the bind source the flags name: `create` makes it, the control must
    without[without.index("--env-file") + 1] = env_file
    control = docker(
        "create", "--pull", "never", "--label", f"brig.jail=oci-pincontrol-{uuid.uuid4().hex[:8]}",
        *without, IMAGE, *plan.command,
    )  # fmt: skip
    control_id = control.stdout.strip()
    try:
        assert control.returncode == 0, control.stderr
        assert docker("start", control_id).returncode == 0
        moved = _out(control_id, f"mv {tree.workspace}/.git {tree.workspace}/.git-moved")
        assert moved[0] == 0, moved  # the control: unpinned, it moves
    finally:
        docker("rm", "-f", control_id)
        shutil.rmtree(ctx.jail_dir, ignore_errors=True)


def test_root_in_the_container_holds_no_capability_and_cannot_remount(
    make_oci_jail: Make, tree: _Tree
) -> None:
    container = container_of(make_oci_jail(tree.spec))
    code, text = _out(container, "grep -E '^Cap(Eff|Bnd|Prm)' /proc/self/status")
    assert code == 0 and {line.split()[-1] for line in text.splitlines()} == {"0" * 16}
    code, text = _out(container, f"mount -o remount,rw {tree.reference}")
    assert code != 0 and "permission denied" in text.lower()
    # no_new_privs: an exec gains nothing back
    assert _out(container, "grep NoNewPrivs /proc/self/status") == (0, "NoNewPrivs:\t1")


def test_the_network_is_the_loopback_alone_and_a_container_that_is_given_one_has_more(
    make_oci_jail: Make, tree: _Tree
) -> None:
    container = container_of(make_oci_jail(tree.spec))
    assert _out(container, "ls /sys/class/net") == (0, "lo")
    bash = exec_in(container, "bash -c 'exec 3<>/dev/tcp/192.0.2.1/80'")
    assert bash.returncode != 0 and "unreachable" in (bash.stdout + bash.stderr).lower()
    # The control: the same image with the default bridge has an interface besides lo.
    control = docker("run", "--rm", "--pull", "never", IMAGE, "ls", "/sys/class/net")
    assert control.returncode == 0 and set(control.stdout.split()) - {"lo"}


def test_the_container_has_a_reaping_init_as_pid_1(make_oci_jail: Make, tree: _Tree) -> None:
    container = container_of(make_oci_jail(tree.spec))
    code, text = _out(container, "tr '\\0' ' ' < /proc/1/cmdline")
    assert code == 0 and "docker-init" in text and "sleep infinity" in text


def test_a_cpu_limit_is_delivered_as_sigxcpu_and_not_as_sigkill(
    make_oci_jail: Make, tree: _Tree
) -> None:
    """decision-161's second of headroom, in a container: soft 1 and hard 2, so a busy loop is
    ended by `SIGXCPU` (shell status 128 + 24) before the hard limit's `SIGKILL` (128 + 9)."""
    container = container_of(make_oci_jail(tree.spec))
    assert _out(container, "ulimit -St") == (0, "1") and _out(container, "ulimit -Ht") == (0, "2")
    code, text = _out(container, "sh -c 'while :; do :; done'; echo $?")
    assert code == 0 and str(128 + 24) in text.splitlines(), text
    assert "CPU time limit exceeded" in text  # the shell's name for SIGXCPU


def test_a_uid_other_than_the_embedders_is_what_user_says(make_oci_jail: Make, tree: _Tree) -> None:
    """`--user` is the compile context's uid and nothing else: a different one is the user in the
    container, and it cannot write the embedder's workspace (the control for the test above)."""
    container = container_of(make_oci_jail(tree.spec, euid=12345))
    assert _out(container, "id -u") == (0, "12345")
    code, text = _out(container, f"touch {tree.workspace}/by-12345")
    assert code != 0 and "Permission denied" in text
    assert not os.path.exists(f"{tree.workspace}/by-12345")
