"""Helpers for tests that run a real supervised bwrap jail (decision-190 to decision-192).

A jail here is `strict_linux()` compiled for an allowlist `Spec` that mounts the system and one
scratch workspace, created through `HostRuntime`, so its PID 1 is brig's supervisor under the
system's `python3`. Everything a test learns about it, it learns the way the leak sweep does:
from the host with `/bin/ps` and `/proc`, or from inside, by a process the test started.

`needs_a_supervised_jail` is the skip, an autouse-style fixture body rather than a module-level
`skipif`, for the reason `tests/e2e/test_strict_linux_journey.py` gives.
"""

from __future__ import annotations

import dataclasses
import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Sequence

import pytest

from brig.core import (
    Channel,
    ChannelKind,
    FsPolicy,
    ReadModel,
    Spec,
)
from brig.mech.bwrap import DEFAULT_BWRAP_PATH
from brig.run import HostRuntime, Jail, Process
from brig.run.compile_ctx import build_compile_ctx
from brig.stack import CompiledJail, strict_linux

INTERPRETER = "/usr/bin/python3"
SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")


def needs_a_supervised_jail() -> None:
    """Skip, visibly and by name, where brig cannot run a supervised jail."""
    if sys.platform != "linux" or not os.path.exists(DEFAULT_BWRAP_PATH):
        pytest.skip(
            f"a supervised bwrap jail needs bubblewrap at {DEFAULT_BWRAP_PATH} on linux "
            f"(sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )
    if not os.path.exists(INTERPRETER):
        pytest.skip(f"the jail's supervisor runs under {INTERPRETER}, which is not there")


def new_jail_dir() -> str:
    return tempfile.mkdtemp(prefix="bg-sv-", dir="/tmp")


def spec_for(
    workspace: str | None = None, *, channel: bool = False, scratch: str | None = None
) -> Spec:
    """An allowlist `Spec`: the system, read-only, `workspace` writable when given, and `scratch`
    (the jail's `<jail_dir>/tmp`, decision-173) writable when given."""
    writable = tuple(path for path in (workspace, scratch) if path is not None)
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in SYSTEM_ROOTS if os.path.exists(path)),
            write_allows=writable,
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),) if channel else (),
    )


def blocked(compiled: CompiledJail) -> CompiledJail:
    """`compiled` with bwrap told to refuse a nested user namespace (`--unshare-user
    --disable-userns`), as a hardened host does: the planted block of decision-195. A process of
    the jail finds `unshare(CLONE_NEWUSER)` refused (`ENOSPC`), so the supervisor's probe fails and
    its processes get no namespaces of their own; nothing else about the jail changes."""
    sentinel = ("__brig_test_argv__",)
    whole = compiled.wrap(sentinel)
    assert whole[-1:] == sentinel, "the compiled wrap is not a pure prefix"
    prefix = whole[:-1]
    at = prefix.index("--unshare-all") + 1
    planted = (*prefix[:at], "--unshare-user", "--disable-userns", *prefix[at:])
    return dataclasses.replace(compiled, wrap=lambda argv: (*planted, *argv))


def create_jail(
    jail_dir: str,
    *,
    workspace: str | None = None,
    channel: bool = False,
    scratch: bool = False,
    namespaces: bool = True,
    tether: int | None = None,
    python: str = INTERPRETER,
    jail_id: str = "supervised",
) -> Jail:
    """A supervised jail through `HostRuntime`, its supervisor ready. The caller destroys it.

    `namespaces=False` plants the block of decision-195 (`blocked`): the jail whose processes
    share the jail's pid, mount, network and IPC namespaces, which is also what a jail run as
    uid 0 is. `True` is whatever the host gives: namespaces of their own for an unprivileged
    user where nested user namespaces work, the shared ones where they don't. `scratch` grants
    the jail's own `<jail_dir>/tmp`, which a process in namespaces gets a directory of its own
    over."""
    scratch_dir = os.path.join(os.path.realpath(jail_dir), "tmp") if scratch else None
    if scratch_dir is not None:
        os.makedirs(scratch_dir, exist_ok=True)
        os.chmod(scratch_dir, 0o777)
    spec = spec_for(workspace, channel=channel, scratch=scratch_dir)
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    compiled = strict_linux(python).compile(spec, ctx=ctx)
    return Jail.create(
        compiled if namespaces else blocked(compiled),
        runtime=HostRuntime(),
        cwd="/",
        jail_id=jail_id,
        jail_dir=jail_dir,
        tether=tether,
    )


@functools.cache
def namespaces_here() -> tuple[bool, str]:
    """Whether a jail made here gives its processes namespaces of their own, and when not the
    supervisor's reason, asked of a real jail once: what a test that needs them skips on."""
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir, jail_id="asked")
    try:
        process = jail.start(["/bin/true"])
        return process.namespaces, process.control.detail
    finally:
        jail.destroy()
        cleanup(jail_dir)


@functools.cache
def the_kernel_gives_namespaces_in_a_jail(*, blocked_jail: bool = False) -> bool:
    """Whether an unprivileged process can make a user, pid, mount, network and IPC namespace
    with a `/proc` for its pid namespace inside a jail made like these, asked of `unshare(1)` and
    not of brig's supervisor: an observation made without the code under test, so that a
    supervisor that wrongly finds none is told from a host that gives none. `blocked_jail` asks
    it of the jail with the block of decision-195 planted (`blocked`)."""
    jail_dir = new_jail_dir()
    try:
        spec = spec_for()
        ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
        compiled = strict_linux(INTERPRETER).compile(spec, ctx=ctx)
        argv = (
            "/usr/bin/unshare",
            "--user",
            "--map-current-user",
            "--pid",
            "--mount",
            "--net",
            "--ipc",
            "--fork",
            "--mount-proc",
            "/bin/true",
        )
        wrap = (blocked(compiled) if blocked_jail else compiled).wrap
        # bwrap reads its stdin to the end for the `--ro-bind-data` the supervisor's program is
        done = subprocess.run(wrap(argv), input=b"x", capture_output=True, check=False)
        return done.returncode == 0
    finally:
        cleanup(jail_dir)


def needs_namespaces() -> None:
    """Skip, visibly and by name, where a jail made here gives its processes none because the host
    gives none (uid 0, or a host that blocks nested user namespaces). Fail where the kernel gives
    an unprivileged process namespaces in such a jail, `unshare(1)` made them, and brig's
    supervisor found none: that is a defect, and a skip would read as a pass."""
    held, why = namespaces_here()
    if held:
        return
    if os.geteuid() != 0 and the_kernel_gives_namespaces_in_a_jail():
        pytest.fail(
            "the kernel gives an unprivileged process namespaces in a jail like this one "
            f"(unshare(1) made them) and brig's supervisor found none: {why}"
        )
    pytest.skip(f"this jail gives its processes no namespaces of their own here: {why}")


def cleanup(jail_dir: str, *workspaces: str) -> None:
    for path in (jail_dir, *workspaces):
        shutil.rmtree(path, ignore_errors=True)


def run_to_end(process: Process, timeout: float = 20.0) -> tuple[int, str]:
    """Wait for `process` and return its status and what it wrote to stdout."""
    status = process.wait(timeout)
    with open(process.stdout_path, encoding="utf-8", errors="replace") as out:
        return status, out.read()


def stderr_of(process: Process) -> str:
    with open(process.stderr_path, encoding="utf-8", errors="replace") as err:
        return err.read()


def sh(script: str) -> list[str]:
    return ["/bin/sh", "-c", script]


def python(code: str, *args: str) -> list[str]:
    return [INTERPRETER, "-I", "-c", code, *args]


def unique_sleep() -> tuple[str, list[str]]:
    """A marker no other process has, and an argv for `/bin/sleep` that carries it: the sleep's
    duration, unique, shows in `ps`'s `args`."""
    marker = f"{uuid.uuid4().int % 10**9 + 10**9}.{uuid.uuid4().int % 10**6:06d}"
    return marker, ["/bin/sleep", marker]


def _table() -> list[tuple[int, int, int, str, str]]:
    out = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,ppid=,pgid=,stat=,args="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows: list[tuple[int, int, int, str, str]] = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and all(parts[i].isdigit() for i in range(3)):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3], parts[4]))
    return rows


def running_with(marker: str) -> list[int]:
    """Host pids of the live (not zombie) processes whose command line holds `marker`, as the
    host sees them: a process of a jail's own pid namespace is visible here."""
    return sorted(
        pid
        for pid, _, _, state, args in _table()
        if marker in args and not state.startswith("Z") and "/bin/ps" not in args
    )


def until(check: object, timeout: float = 10.0, step: float = 0.05) -> bool:
    """Poll `check()` until it is truthy or `timeout` passes; the last answer."""
    assert callable(check)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(step)
    return bool(check())


_NSPID = re.compile(r"^NSpid:\s+(.*)$", re.MULTILINE)


def supervisor_host_pid(instance_group: int) -> int:
    """The host pid of the jail's PID 1, the supervisor: the process of the instance's group
    (`jail.to_dict()["supervisor"]["pid"]`, the group the exit wrapper leads) whose pid in its
    own namespace is 1 (`NSpid` ends in 1). Read from `/proc` by the host.

    Raises:
        LookupError: no such process: the jail has no PID 1 running.
    """
    for pid, _, pgid, state, _ in _table():
        if pgid != instance_group or state.startswith("Z"):
            continue
        try:
            with open(f"/proc/{pid}/status", encoding="utf-8") as status:
                found = _NSPID.search(status.read())
        except OSError:
            continue
        if (
            found is not None
            and found.group(1).split()[-1] == "1"
            and len(found.group(1).split()) > 1
        ):
            return pid
    raise LookupError(f"no process of group {instance_group} is PID 1 of its own pid namespace")


def process_state(pid: int) -> str:
    """The one-letter state in `/proc/<pid>/status`, or `gone`."""
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as status:
            found = re.search(r"^State:\s+(\S)", status.read(), re.MULTILINE)
    except OSError:
        return "gone"
    return "gone" if found is None else found.group(1)


def instance_group(jail: Jail) -> int:
    instance = jail.to_dict()["supervisor"]
    assert instance is not None, "not a supervised jail"
    return int(instance["pid"])


def argv_words(argv: Sequence[str]) -> str:
    return " ".join(argv)
