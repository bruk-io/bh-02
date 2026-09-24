"""task-081: the network battery against a stack that ACTUALLY enforces
something on the network axis.

NOT a duplicate of task-052/063/070. Those prove the battery reports HONESTLY
against a stack with NO network mechanism, where its interesting verdict is an
honest non-claim. This is the case that could not be built until
`connect_proxy` and the confined pairing existed: a `confined_egress_darwin`
stack, where the DENIAL probe must pass on the proxy's own confinement and a
weakened stack carrying an unchanged report must be CAUGHT.

**What building this found (decision-141).** The battery's granted-domain
CONTROL used to be a raw `exec 3<>/dev/tcp/$0/443`. Under a confined egress
stack that is guaranteed to fail -- the seatbelt denies all non-loopback
outbound precisely so a workload ignoring `HTTP_PROXY` cannot dial out, and
`/dev/tcp` ignores `HTTP_PROXY` by construction -- so the battery would have
reported a CORRECTLY confined jail as broken. The control now honours the
proxy variables; the DENIAL probe deliberately still does not, because what it
tests is that a workload BYPASSING the proxy cannot reach the network.

**No internet.** The "allowed domain" is a loopback origin server this file
starts, so the control proves routing rather than connectivity, and the suite
does not fail when a network is absent.
"""

from __future__ import annotations

import contextlib
import dataclasses
import itertools
import os
import socket
import sys
import threading
import uuid
from collections.abc import Sequence
from typing import cast

import pytest

from brig.core import Axis, Grade, NetworkPolicy, ProbeReport, ProbeShape, Spec, Verdict
from brig.core import Battery as CoreBattery
from brig.core.probes import BatteryVerdict  # not barrel-exported; see test_probe_forgery.py
from brig.mech import env_scrub, rlimits
from brig.probe.batteries.network import network_battery
from brig.run import Handle, IoPolicy, SubprocessLauncher, build_compile_ctx
from brig.run.teardown import kill_jail
from brig.stack import Stack, confined_egress_darwin
from tests.conftest import teardown_group

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt is sandbox-exec, darwin only"),
]

_jail_counter = itertools.count()

#: RFC 5737 TEST-NET-1: a literal address that is routable-looking and never
#: actually reachable, so only policy can decide the DENIAL probe's outcome.
_DENIED_ADDRESS = "192.0.2.1:80"


def _new_root(run_id: str, tag: str) -> str:
    """Short scratch root -- `sun_path` is 104 bytes on darwin (CLAUDE.md's
    own trap list), so never `tmp_path`. The `nb` infix keeps this file's
    counter from colliding with a sibling e2e file's."""
    path = f"/tmp/bg{os.getpid()}{tag}{run_id[:8]}{next(_jail_counter)}"
    os.makedirs(path, exist_ok=True)
    return os.path.realpath(path)


@pytest.fixture
def origin():  # type: ignore[no-untyped-def]
    """A loopback HTTP origin standing in for the allowed domain."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)

    def serve() -> None:
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            with contextlib.suppress(OSError):
                conn.recv(4096)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield sock.getsockname()[1]
    sock.close()


def _launch(stack: Stack, spec: Spec, argv: Sequence[str], *, run_id: str) -> Handle:
    """`Spec -> Stack -> Launcher -> Handle`, the public chain
    `.claude/rules/system-tests.md` names. No internal seam."""
    jail_dir = _new_root(run_id, "nb")
    # seatbelt needs a real platform and resolved paths, so the ctx is built
    # through the public `build_compile_ctx` rather than left to
    # `Stack.compile`'s ctx=None placeholder.
    jail = stack.compile(
        spec, ctx=build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    )
    return SubprocessLauncher().launch(
        jail,
        argv=list(argv),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=run_id,
        jail_dir=jail_dir,
    )


def _teardown_group(handle: Handle) -> None:
    """Tear the whole jail down, HELPERS INCLUDED.

    A bare `os.killpg(handle.pgid, ...)` -- which the sibling e2e
    files use -- is not enough here and the leak checker said so: it reaps
    the workload's group and leaves `connect_proxy`'s JAIL_LIFETIME proxy
    running, a listening socket outliving the jail it filtered for. This is
    the first e2e file whose stack declares a helper at all.

    `kill_jail` is not the code under test (`handle.probe` is), so using the
    real teardown here does not make a test mark its own homework."""
    # `kill_jail` first, because THIS stack declares a JAIL_LIFETIME helper
    # (connect_proxy's proxy) and the group kill below does not reach it --
    # a proxy outliving the jail it filtered for is a listening socket with
    # no owner. Then the shared verified teardown (task-086) confirms the
    # workload's own group actually emptied.
    kill_jail(handle)
    teardown_group(handle)


def _probe(handle: Handle, battery: object) -> ProbeReport:
    return handle.probe(cast(CoreBattery, battery))


def _spec() -> Spec:
    """`localhost` is the granted domain; the loopback origin's PORT rides in
    `control_url`, because `allowed_domains` entries are hosts and
    `connect_proxy` matches them exact-or-wildcard."""
    return Spec(network=NetworkPolicy(allowed_domains=("localhost",)))


def _battery(port: int):  # type: ignore[no-untyped-def]
    return network_battery(
        _spec(),
        denied_address=_DENIED_ADDRESS,
        control_url=f"http://HOST:{port}/x",
    )


def test_the_battery_is_consistent_against_a_stack_that_really_enforces(origin: int) -> None:
    """AC #1, #2, #4 together, because separately each is vacuous.

    The DENIAL probe must fail to reach a literal address (the confinement
    working), the CONTROL must reach the ALLOWED origin through the proxy
    (so a battery passing because ALL egress is broken is impossible), and
    the battery's verdict for a correctly-reporting stack must be
    CONSISTENT -- not merely non-contradicting.
    """
    run_id = uuid.uuid4().hex
    handle = _launch(
        confined_egress_darwin(sys.executable),
        _spec(),
        ("/bin/sh", "-c", "while :; do sleep 0.2; done"),
        run_id=run_id,
    )
    try:
        report = _probe(handle, _battery(origin))

        denial = next(o for o in report.outcomes if o.shape is ProbeShape.DENIAL)
        control = next(o for o in report.outcomes if o.shape is ProbeShape.CONTROL)

        assert control.verdict is Verdict.PASS, (
            "the CONTROL must reach the allowed origin THROUGH the proxy; a "
            "battery whose control fails cannot tell 'policy denied this' "
            f"from 'nothing works here'. {control!r}"
        )
        assert denial.verdict is Verdict.PASS, (
            f"the confinement must deny a direct literal address. {denial!r}"
        )
        assert report.battery_verdict is BatteryVerdict.CONSISTENT, report
    finally:
        _teardown_group(handle)


def test_forgery_a_stack_with_no_confinement_carrying_the_confined_report_fails_its_battery(
    origin: int,
) -> None:
    """AC #3, and the honest strength of it.

    The weakened stack is `[rlimits, env_scrub]` -- no seatbelt, no
    connect_proxy, nothing that could refuse egress -- while its CLAIMED
    report is the real `confined_egress_darwin` one, copied from an honest
    compile and never hand-built. It claims `best_effort` on an axis it does
    nothing about.

    **It fails its battery as VACUOUS, not CONTRADICTED, and that is the
    correct verdict rather than a weaker one accepted for convenience.**
    CONTRADICTED requires a probe outcome that positively contradicts a
    grade. On the network axis it is not reachable here: the DENIAL probe
    dials an unroutable literal (TEST-NET-1), so on a stack with no policy
    the connection fails anyway -- by unreachability rather than refusal --
    and the engine correctly declines to read "the sandbox refused this"
    from "the sandbox never had a chance to". With no signature claim on
    file it reports VACUOUS: it cannot confirm anything about this axis.

    That is still the forgery being caught, and the assertion pair is what
    makes it load-bearing: the honest stack reaches CONSISTENT (the test
    above), this one cannot. A report claiming `best_effort` whose battery
    can demonstrate no denial at all has failed to earn its grade.

    Asserting CONTRADICTED here would have meant engineering the denied
    address to be reachable-but-refused, which no stack-independent address
    can be -- the "green, honest, and not about the thing" trap one level up.
    """
    run_id = uuid.uuid4().hex
    spec = _spec()
    honest_dir = _new_root(run_id, "nc")
    honest_report = (
        confined_egress_darwin(sys.executable)
        .compile(spec, ctx=build_compile_ctx(spec, jail_dir=honest_dir, platform=sys.platform))
        .report
    )
    assert honest_report.axes[Axis.NETWORK].grade is Grade.BEST_EFFORT

    weakened = Stack([rlimits, env_scrub])
    handle = _launch(
        weakened, spec, ("/bin/sh", "-c", "while :; do sleep 0.2; done"), run_id=run_id
    )
    forged = dataclasses.replace(handle, report=honest_report)
    try:
        report = _probe(forged, _battery(origin))
        assert report.battery_verdict is not BatteryVerdict.CONSISTENT, (
            "a stack with no confinement at all, carrying a report that claims "
            f"best_effort egress, must not read as CONSISTENT. {report!r}"
        )
        assert report.battery_verdict is BatteryVerdict.VACUOUS, report
    finally:
        _teardown_group(handle)
