"""`bwrap`'s `network` enforcement -- an unshared network namespace --
observed from inside a real jail, with the control that keeps it from being
a statement about this host's own connectivity.

Two observations, and the second is what makes the first mean anything:

1. Inside the jail, a connect to a routable address fails with
   `Network is unreachable`, which is one of the mechanism's own declared
   denial signatures. This needs no working internet ANYWHERE: a network
   namespace holding nothing but loopback has no default route, so the
   kernel answers ENETUNREACH before a packet is ever sent. That is the
   whole claim -- deny-all by unshare, not by filtering.
2. Inside the same jail, a loopback socket the jailed process binds and
   connects to ITSELF succeeds. Without this control, a broken interpreter
   or a missing library would produce the same "it failed" as enforcement
   does. And it makes the deny-all claim precise rather than absolute: the
   jail keeps its OWN loopback, which is what lets a LISTEN channel and any
   in-jail socket work at all.

The host-side control that pair 1 does NOT use, named so its absence is a
choice: connecting to the same address from an UNJAILED process would
depend on the runner having egress, which turns a network-isolation test
into a network-availability test. The netns argument above is what replaces
it, and it is strictly more deterministic.

**Skips visibly by name**, twice: bubblewrap (linux-only, not installed by
default) and the `python3` this file needs INSIDE the jail, because
`/bin/sh` on a Debian-family host is `dash` and has no network primitive at
all.

**Executed on linux 2026-09-08.** The development machine is darwin, where
this file skips; it was run on a real linux kernel in a container by
`tools/linux-check.sh` (the keel workspace's reproduction of the
`verify-linux` CI job) and passes there. What that is NOT is a GitHub
Actions run: the job itself has still never been observed, and a container
is not the runner image.
"""

from __future__ import annotations

import itertools
import os
import sys

import pytest

from brig.core import FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run.compile_ctx import build_compile_ctx
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack

_PYTHON = "/usr/bin/python3"

#: The skip is an AUTOUSE FIXTURE rather than a module-level
#: `pytest.mark.skipif`, and the reason is mechanical: `skipif`'s condition
#: is evaluated at IMPORT time, so probing for the binary there is an
#: import-time `os.path.exists` -- which pypeeker's
#: `import-time-side-effects` rule refuses, workspace-wide, for good
#: reasons that do not stop applying inside a test file. A fixture asks the
#: same question at setup time and reports the same visible, named skip.


@pytest.fixture(autouse=True)
def _needs_bubblewrap_and_python() -> None:
    if (
        sys.platform != "linux"
        or not os.path.exists(DEFAULT_BWRAP_PATH)
        or not os.path.exists(_PYTHON)
    ):
        pytest.skip(
            f"needs bubblewrap at {DEFAULT_BWRAP_PATH} and an interpreter at {_PYTHON} "
            f"on linux (sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )


_jail_counter = itertools.count()
_WAIT_TIMEOUT_S = 30.0
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")

#: Deliberately a documentation-range address that is also globally
#: routable-looking: what matters is only that it is NOT loopback, so a
#: namespace with no default route answers ENETUNREACH immediately. No
#: packet leaves the machine even when the jail is removed.
_OFF_LOOPBACK = "203.0.113.1"

_PROBE = f"""
import socket, sys
try:
    s = socket.socket()
    s.settimeout(2)
    s.connect(({_OFF_LOOPBACK!r}, 80))
except OSError as exc:
    print("OFFBOX_FAILED:", exc, file=sys.stderr)
else:
    print("OFFBOX_CONNECTED")

server = socket.socket(socket.AF_INET)
server.bind(("127.0.0.1", 0))
server.listen(1)
client = socket.socket(socket.AF_INET)
client.settimeout(2)
client.connect(server.getsockname())
print("LOOPBACK_OK")
"""


def _new_jail_dir() -> str:
    return f"/tmp/bg{os.getpid()}bn{next(_jail_counter)}"


def _spec(workspace: str) -> Spec:
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(p for p in _SYSTEM_ROOTS if os.path.exists(p)),
            write_allows=(workspace,),
        )
    )


def _run(*, jailed: bool) -> tuple[str, str]:
    jail_dir = _new_jail_dir()
    workspace = f"{jail_dir}/ws"
    os.makedirs(workspace, exist_ok=True)
    spec = _spec(workspace)
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    stack = Stack([bwrap]) if jailed else Stack([])
    handle = SubprocessLauncher().launch(
        stack.compile(spec, ctx=ctx),
        argv=[_PYTHON, "-c", _PROBE],
        cwd=workspace,
        io=IoPolicy(),
        jail_id=f"bwrap-net-{'jailed' if jailed else 'control'}",
        jail_dir=jail_dir,
    )
    handle.wait(timeout=_WAIT_TIMEOUT_S)
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout = f.read()
    with open(handle.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr = f.read()
    return stdout, stderr


@pytest.mark.integration
def test_an_off_loopback_connect_is_unreachable_and_matches_the_signature() -> None:
    """Observation 1. The signature is fetched from the mechanism's own
    compiled `Step` rather than written as a literal, so this tests what
    `bwrap` declares."""
    spec = _spec("/tmp")
    ctx = build_compile_ctx(spec, jail_dir=_new_jail_dir(), platform="linux")
    signatures = bwrap.compile(spec, ctx).denial_signatures

    stdout, stderr = _run(jailed=True)

    assert "OFFBOX_CONNECTED" not in stdout
    assert "OFFBOX_FAILED" in stderr
    assert any(pattern.search(stderr) for pattern in signatures), stderr


@pytest.mark.integration
def test_the_jail_keeps_its_own_loopback_which_is_the_control() -> None:
    """Observation 2. A jailed process can still bind and connect to its
    OWN loopback -- so the failure above is the missing route, not a
    missing interpreter, and the deny-all claim is precise: the namespace
    is empty of everything except the jail's own loopback, which a LISTEN
    channel needs."""
    stdout, _stderr = _run(jailed=True)

    assert "LOOPBACK_OK" in stdout


@pytest.mark.integration
def test_without_the_jail_the_same_probe_does_not_report_unreachable() -> None:
    """The mutation-shaped control: the identical probe through `Stack([])`
    -- bwrap REMOVED -- does not produce the unreachable answer, because
    the host has a default route. It may still fail (a runner with no
    egress will time out or be refused), which is why this asserts on the
    SIGNATURE rather than on success: what must not happen is the denial
    text appearing without the mechanism that causes it."""
    spec = _spec("/tmp")
    ctx = build_compile_ctx(spec, jail_dir=_new_jail_dir(), platform="linux")
    signatures = bwrap.compile(spec, ctx).denial_signatures

    _stdout, stderr = _run(jailed=False)

    assert not any(pattern.search(stderr) for pattern in signatures), stderr
