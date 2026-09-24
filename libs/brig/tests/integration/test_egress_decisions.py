"""`read_egress_decisions`: the reader the proxy's file had been waiting for.

decision-157 (2026-09-08). `brig/proxy/server.py` has written one JSON line
per allow/deny since M6, and both its docstring and `connect_proxy`'s said a
`run`-layer reader would fold those records in wherever the embedder's
records go. No reader existed, so every decision the filter made reached a
file nobody opened -- a mechanism's whole live output, declared and
uncalled.

**The claim is read from what a REAL proxy wrote**, never from a
hand-constructed line. That is the point of putting this at the integration
tier rather than the unit one: the reader and the writer are two programs
that may not import each other (`proxy`'s empty layer row, decision-133), so
the ONLY thing that can prove they agree on the record's shape is a round
trip through the file itself. A unit test over a literal line would pin this
module's opinion of the format and go green forever while the proxy changed
underneath it.

THE CONTROL, in the tests that need one: the same reader, on the same jail,
answering differently for the allowed and the denied destination -- both of
which reach the SAME real origin over loopback by two names (`localhost`
permitted, `127.0.0.1` not), so a `deny` record cannot be explained by
unreachability.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import socket
import sys
import threading
import time

import pytest

from brig.core import EventKind, NetworkPolicy, Spec
from brig.mech import CompileCtx
from brig.mech.connect_proxy import ConnectProxy
from brig.run import teardown as teardown_mod
from brig.run.egress import decisions_path, read_egress_decisions
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail
from tests.conftest import workload_argv

pytestmark = pytest.mark.integration

_jail_counter = itertools.count()
_BODY = b"origin-server-payload"

#: How long a test waits for the proxy to have written the decision it is
#: about. Generous: the request has already been answered on the wire by the
#: time the line is flushed, so this only ever ends early on a failing path.
_IDLE_S = 25.0


class _Origin:
    """A real HTTP origin on loopback (see `test_proxy_egress._Origin`)."""

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self.port: int = self._sock.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5.0)
            with contextlib.suppress(OSError):
                if conn.recv(4096):
                    conn.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: "
                        + str(len(_BODY)).encode()
                        + b"\r\nConnection: close\r\n\r\n"
                        + _BODY
                    )

    def close(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._sock.close()


@pytest.fixture
def origin():  # type: ignore[no-untyped-def]
    server = _Origin()
    try:
        yield server
    finally:
        server.close()


def _new_jail_dir() -> str:
    path = f"/tmp/bg{os.getpid()}eg{next(_jail_counter)}"
    os.makedirs(path, exist_ok=True)
    return os.path.realpath(path)


def _jail(jail_dir: str, domains: tuple[str, ...]) -> CompiledJail:
    """One mechanism, compiled into a single-step jail -- never a preset
    stack, so a failure names `connect_proxy` and nothing else."""
    from brig.core import unenforced_report

    spec = Spec(network=NetworkPolicy(allowed_domains=domains))
    step = ConnectProxy(sys.executable).compile(
        spec, CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    )
    return CompiledJail(
        spec=spec,
        report=unenforced_report(),
        wrap=step.wrap,
        env=dict(step.env),
        staged=step.staged,
        helpers=step.helpers,
        requires=step.requires,
        mechanism_names=("connect_proxy",),
        matrix_version=1,
    )


def _fetch(url: str, out: str) -> str:
    """A workload that fetches `url` HONOURING the proxy variables, and does
    not care whether it succeeds -- what this file reads is the PROXY's
    record, not the workload's."""
    return (
        f"{sys.executable} -c "
        f'"import urllib.request,urllib.error\n'
        f"try:\n urllib.request.urlopen({url!r},timeout=15)\n"
        f"except Exception as e:\n pass\n"
        f"open({out!r},'w').write('done')\" "
    )


def _run(jail_dir: str, domains: tuple[str, ...], body: str, run_id: str) -> Handle:
    return SubprocessLauncher().launch(
        _jail(jail_dir, domains),
        argv=workload_argv(run_id, body),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-egress-reader",
        jail_dir=jail_dir,
    )


def _wait_for_the_proxy_to_record(jail_dir: str, count: int = 1) -> None:
    """Block until the proxy has written at least `count` whole lines.

    Counted from the FILE, not from the workload's own output: those are two
    processes writing two files, and the workload having its answer says
    nothing about the filter having flushed the line describing how it got
    it."""
    path = decisions_path(jail_dir)
    deadline = time.monotonic() + _IDLE_S
    while time.monotonic() < deadline:
        try:
            with open(path, encoding="utf-8") as decisions:
                if len([line for line in decisions if line.endswith("\n")]) >= count:
                    return
        except OSError:
            pass
        time.sleep(0.05)


def test_the_reader_returns_the_proxys_own_allow_decision(run_id: str, origin: _Origin) -> None:
    """The round trip: a real request through a real filter, and the reader
    hands back a stamped `Event` naming the destination the proxy permitted.

    Stamped is half the claim -- `ts` and `jail_id` are the two fields only
    `run` may supply (SPEC.md section 6), and a reader that returned raw
    lines would push that job onto the embedder."""
    jail_dir = _new_jail_dir()
    handle = _run(
        jail_dir,
        ("localhost",),
        _fetch(f"http://localhost:{origin.port}/x", os.path.join(jail_dir, "got")),
        run_id,
    )
    try:
        _wait_for_the_proxy_to_record(jail_dir)
        read = read_egress_decisions(handle.jail_dir, handle.jail_id)

        assert read.events, f"nothing read from {decisions_path(jail_dir)!r}"
        allows = [e for e in read.events if e.data["egress_decision"] == "allow"]
        assert allows, [dict(e.data) for e in read.events]
        assert allows[0].data["host"] == "localhost", dict(allows[0].data)
        assert allows[0].data["port"] == origin.port, dict(allows[0].data)

        assert allows[0].kind is EventKind.EGRESS
        assert allows[0].jail_id == handle.jail_id
        assert allows[0].ts > 0.0
    finally:
        teardown_mod.kill_jail(handle)


def test_the_reader_returns_a_deny_for_a_destination_outside_the_allow_list(
    run_id: str, origin: _Origin
) -> None:
    """THE CONTROL for the test above: the same origin, reachable, by a name
    the policy does not permit -- and what comes back says `deny`. Without
    it, "the reader returned a decision" would be satisfied by a reader that
    hard-coded one."""
    jail_dir = _new_jail_dir()
    handle = _run(
        jail_dir,
        ("localhost",),
        _fetch(f"http://127.0.0.1:{origin.port}/x", os.path.join(jail_dir, "got")),
        run_id,
    )
    try:
        _wait_for_the_proxy_to_record(jail_dir)
        read = read_egress_decisions(handle.jail_dir, handle.jail_id)

        denies = [e for e in read.events if e.data["egress_decision"] == "deny"]
        assert denies, [dict(e.data) for e in read.events]
        assert denies[0].data["host"] == "127.0.0.1", dict(denies[0].data)
        assert denies[0].data["detail"] == "not in allow list", dict(denies[0].data)
    finally:
        teardown_mod.kill_jail(handle)


def test_the_cursor_returns_what_is_new_and_never_the_same_line_twice(run_id: str, origin) -> None:  # type: ignore[no-untyped-def]
    """An embedder folds these into the record of the action that made the
    call, so the reader has to answer "what is new since I last looked". Read
    once, read again from the returned cursor: the second read is empty even
    though the file still holds everything the first one returned.

    THE CONTROL that keeps "empty" from being trivially true: a read from
    cursor 0 immediately afterwards returns the same records again, so the
    second read's emptiness is the cursor working rather than the file
    having been consumed or the reader having broken."""
    jail_dir = _new_jail_dir()
    handle = _run(
        jail_dir,
        ("localhost",),
        _fetch(f"http://localhost:{origin.port}/x", os.path.join(jail_dir, "got")),
        run_id,
    )
    try:
        _wait_for_the_proxy_to_record(jail_dir)
        first = read_egress_decisions(handle.jail_dir, handle.jail_id)
        assert first.events
        assert first.cursor > 0

        again = read_egress_decisions(handle.jail_dir, handle.jail_id, cursor=first.cursor)
        assert again.events == (), [dict(e.data) for e in again.events]
        assert again.cursor == first.cursor

        from_the_start = read_egress_decisions(handle.jail_dir, handle.jail_id)
        assert len(from_the_start.events) == len(first.events)
    finally:
        teardown_mod.kill_jail(handle)


def test_a_jail_with_no_proxy_reads_nothing_rather_than_failing(run_id: str) -> None:
    """A stack without `connect_proxy` writes no decisions file at all, and
    an embedder that asks anyway must get "nothing", not an error: the reader
    is called after every action, and most jails have no proxy."""
    jail_dir = _new_jail_dir()
    read = read_egress_decisions(jail_dir, "jail-with-no-proxy")
    assert read.events == ()
    assert read.cursor == 0
    assert not os.path.exists(decisions_path(jail_dir))


def test_a_half_written_last_line_is_left_for_the_next_read(run_id: str) -> None:
    """The proxy appends for the life of the jail, so a read can always land
    mid-write. A partial trailing line is neither parsed nor skipped: the
    cursor stops before it, and the next read -- once the writer has finished
    the line -- returns it whole.

    Written by hand here on purpose. Catching a real proxy between two
    `write` calls is a race no test can schedule, and what is under test is
    the READER's arithmetic, which a hand-written file exercises exactly."""
    jail_dir = _new_jail_dir()
    path = decisions_path(jail_dir)
    whole = (
        '{"detail": "", "decision": "allow", "host": "example.test", '
        '"kind": "egress", "monotonic": 1.5, "port": 443}\n'
    )
    with open(path, "w", encoding="utf-8") as decisions:
        decisions.write(whole + '{"detail": "", "decision": "de')

    first = read_egress_decisions(jail_dir, "jail-partial")
    assert len(first.events) == 1
    assert first.cursor == len(whole)

    with open(path, "a", encoding="utf-8") as decisions:
        decisions.write(
            'ny", "host": "other.test", "kind": "egress", "monotonic": 2.5, "port": 80}\n'
        )

    second = read_egress_decisions(jail_dir, "jail-partial", cursor=first.cursor)
    assert len(second.events) == 1
    assert second.events[0].data["egress_decision"] == "deny"
    assert second.events[0].data["host"] == "other.test"


def test_a_whole_line_that_is_not_the_proxys_record_is_loud(run_id: str) -> None:
    """The forgiving cases are exactly two -- no file, and a line that is not
    finished. Anything else means something other than this jail's proxy is
    writing to the path the mechanism announced, which is a fact an embedder
    must not have folded silently into its log."""
    jail_dir = _new_jail_dir()
    with open(decisions_path(jail_dir), "w", encoding="utf-8") as decisions:
        decisions.write('{"decision": "allow"}\n')

    with pytest.raises(ValueError) as exc_info:
        read_egress_decisions(jail_dir, "jail-bogus")
    assert "does not have the proxy's shape" in str(exc_info.value)
