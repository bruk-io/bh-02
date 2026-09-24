"""A CEDING seatbelt against the real darwin sandbox kernel: decision-136 (3)+(4).

`Seatbelt(cedes_network=True)` hands `Axis.NETWORK` to `connect_proxy` and,
because the workload now reaches its allowed hosts THROUGH the proxy on
loopback, must stop denying the loopback hop. That change is only worth
anything if the kernel agrees, so it is observed here rather than asserted
against the rendered text.

**Both controls, in the same jailed process's same run**, because either
alone is vacuous:

- loopback alone would pass just as well if the allowance had opened ALL
  egress -- the exact silent failure this pairing exists to prevent;
- external alone would pass for a profile that denied everything, including
  the proxy hop, which breaks every ALLOWED request instead of only the
  denied ones.

The non-ceding profile is the third observation: it must still deny
loopback, or `cedes_network` is not actually the thing making the
difference and this file is measuring the weather.
"""

from __future__ import annotations

import itertools
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from brig.core import Spec
from brig.mech.seatbelt.profile import render_sbpl

pytestmark = pytest.mark.integration

_counter = itertools.count()

#: Any routable non-loopback address. Never actually connected to when the
#: sandbox is working: the refusal happens in the kernel, before a packet.
_EXTERNAL = ("1.1.1.1", 80)


@pytest.fixture
def loopback_listener():  # type: ignore[no-untyped-def]
    """A real listener on 127.0.0.1, so 'connected' means connected."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)

    def serve() -> None:
        while True:
            try:
                conn, _ = sock.accept()
                conn.close()
            except OSError:
                return

    threading.Thread(target=serve, daemon=True).start()
    yield sock.getsockname()[1]
    sock.close()


def _profile(jail_dir: str, *, cedes: bool) -> str:
    path = os.path.join(jail_dir, "seatbelt.sb")
    with open(path, "w") as handle:
        handle.write(render_sbpl(Spec(), resolved={}, jail_dir=jail_dir, cedes_network=cedes))
    return path


def _probe_from_inside_the_jail(profile: str, port: int) -> dict[str, str]:
    """Run the connect attempts INSIDE the sandbox and report what happened.

    Observed from inside, never inferred from outside
    (`.claude/rules/integration-tests.md`).
    """
    script = f"""
import socket
for label, addr in (("loopback", ("127.0.0.1", {port})), ("external", {_EXTERNAL!r})):
    try:
        socket.create_connection(addr, timeout=3).close()
        print(f"{{label}}=connected")
    except PermissionError:
        print(f"{{label}}=denied")
    except Exception as exc:
        print(f"{{label}}=other:{{type(exc).__name__}}")
"""
    done = subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", profile, sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return dict(line.split("=", 1) for line in done.stdout.strip().splitlines() if "=" in line)


@pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt is sandbox-exec, darwin only")
def test_ceding_permits_the_loopback_hop_and_still_denies_everything_else(
    tmp_path: Path, loopback_listener: int
) -> None:
    """decision-136 (4): the allowance is loopback-WIDE (the proxy binds port
    0, so no port is knowable when this pure render runs) but it is not
    egress-wide. Both halves, one run."""
    jail_dir = os.path.realpath(str(tmp_path))
    result = _probe_from_inside_the_jail(_profile(jail_dir, cedes=True), loopback_listener)

    assert result.get("loopback") == "connected", (
        "a ceding seatbelt must permit the loopback hop, or every request the "
        f"proxy was going to ALLOW fails too. got {result!r}"
    )
    assert result.get("external") == "denied", (
        "the loopback allowance must not open general egress -- if it does, "
        "the workload bypasses the proxy entirely and the whole pairing is "
        f"decorative. got {result!r}"
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt is sandbox-exec, darwin only")
def test_control_a_non_ceding_seatbelt_still_denies_loopback(
    tmp_path: Path, loopback_listener: int
) -> None:
    """THE CONTROL. Without `cedes_network`, loopback is denied like anything
    else -- so the test above is observing `cedes_network`, not a host that
    happens to allow loopback to everyone.

    This is also the mutation check for the render, standing rather than
    performed once: delete the `if cedes_network:` line in `profile.py` and
    the test above reddens on `loopback`, while this one keeps passing.
    """
    jail_dir = os.path.realpath(str(tmp_path))
    result = _probe_from_inside_the_jail(_profile(jail_dir, cedes=False), loopback_listener)

    assert result.get("loopback") == "denied", (
        f"the default profile must deny loopback; got {result!r}"
    )
