"""The egress proxy against real sockets: both paths, separately.

`.claude/rules/integration-tests.md` forbids using one path as evidence
about the other ("plain HTTP is not evidence about CONNECT tunnels"), so
the plain-HTTP filter and the CONNECT tunnel each get their own allow/deny
pair here. Nothing is asserted from the proxy's own decision log; the log
is checked separately, and only after the behaviour it describes has been
observed independently.

THE CONTROL, and why it is built the way it is: the allowed and the denied
request in each pair reach THE SAME real origin server, over loopback, by
two names that both resolve to it -- `localhost` is allowed, `127.0.0.1` is
not. So a denial cannot be explained by the destination being unreachable,
unresolvable, or absent, which is exactly what a `deny -> some-other-host`
test cannot rule out. The allowed half proves the proxy forwards; the
denied half proves it decides.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator

import pytest

from brig.proxy.filter import DENIAL_PREFIX

pytestmark = pytest.mark.integration

_BODY = b"origin-server-payload"


class _Origin:
    """A real server on loopback, speaking just enough to be a destination.

    Serves both roles the two paths need: a one-shot HTTP response for the
    plain path, and a byte echo for whatever a CONNECT tunnel carries --
    the proxy does not terminate TLS, so raw bytes are precisely what a
    tunnel moves, and a real TLS handshake would test Python's ssl module
    rather than this proxy.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self.port: int = self._sock.getsockname()[1]
        self.seen_paths: list[str] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

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
            try:
                first = conn.recv(4096)
            except OSError:
                return
            if not first:
                return
            if first.split(b" ", 1)[0] in (b"GET", b"POST", b"HEAD"):
                self.seen_paths.append(first.split(b" ")[1].decode("latin-1"))
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(len(_BODY)).encode()
                    + b"\r\nConnection: close\r\n\r\n"
                    + _BODY
                )
                return
            # Echo role, for the tunnel.
            try:
                conn.sendall(first)
                while not self._stop.is_set():
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    conn.sendall(chunk)
            except OSError:
                return

    def close(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._sock.close()


class _Proxy:
    """The proxy under test, as the separate process it really is.

    Spawned exactly as a `JAIL_LIFETIME` helper will spawn it -- `python -m
    brig.proxy`, its own session, port published to a file -- rather than
    by calling `serve()` in a thread. A thread would share this
    interpreter's memory and prove nothing about the process boundary the
    mechanism depends on.
    """

    def __init__(self, tmp: str, allow: tuple[str, ...]) -> None:
        self.decisions_path = os.path.join(tmp, "decisions.jsonl")
        port_file = os.path.join(tmp, "port")
        argv = [
            sys.executable,
            "-m",
            "brig.proxy",
            "--port-file",
            port_file,
            "--log",
            self.decisions_path,
        ]
        for host in allow:
            argv += ["--allow", host]
        self.proc = subprocess.Popen(argv, start_new_session=True)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if os.path.exists(port_file):
                with open(port_file) as fh:
                    text = fh.read().strip()
                if text:
                    self.port = int(text)
                    return
            if self.proc.poll() is not None:
                raise AssertionError(f"proxy exited early: {self.proc.returncode}")
            time.sleep(0.02)
        raise AssertionError("proxy never published a port")

    def close(self) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self.proc.pid, 15)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=5)
        if self.proc.poll() is None:  # pragma: no cover - only on a hung proxy
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self.proc.pid, 9)
            self.proc.wait(timeout=5)


@pytest.fixture
def origin() -> Iterator[_Origin]:
    server = _Origin()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def proxy(tmp_path: object) -> Iterator[_Proxy]:
    # `tmp_path` is safe here, unlike elsewhere in this suite: nothing in
    # this file binds a Unix socket, so the 104-byte `sun_path` trap that
    # forces short scratch roots does not apply.
    started = _Proxy(str(tmp_path), allow=("localhost",))
    try:
        yield started
    finally:
        started.close()


def _speak(proxy: _Proxy, request: bytes, *, expect_more: bool = False) -> bytes:
    conn = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
    conn.settimeout(10)
    try:
        conn.sendall(request)
        out = bytearray()
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            out.extend(chunk)
            if expect_more and b"\r\n\r\n" in bytes(out):
                break
        return bytes(out)
    finally:
        conn.close()


def test_plain_http_to_an_allowed_host_is_forwarded(proxy: _Proxy, origin: _Origin) -> None:
    """THE CONTROL for the denial below: same proxy, same origin, allowed
    name -- the origin's own payload comes back, so the proxy forwards."""
    got = _speak(
        proxy,
        f"GET http://localhost:{origin.port}/hello HTTP/1.1\r\nHost: localhost\r\n\r\n".encode(),
    )
    assert b"200 OK" in got, got[:200]
    assert _BODY in got, got[:200]
    assert "/hello" in origin.seen_paths, (
        f"origin never saw the request in origin form: {origin.seen_paths!r}"
    )


def test_plain_http_to_a_denied_host_is_refused(proxy: _Proxy, origin: _Origin) -> None:
    """Same reachable origin, by a name the policy does not permit."""
    got = _speak(
        proxy,
        f"GET http://127.0.0.1:{origin.port}/hello HTTP/1.1\r\nHost: x\r\n\r\n".encode(),
    )
    assert b"403 Forbidden" in got, got[:200]
    assert DENIAL_PREFIX.encode() in got, got[:200]
    assert _BODY not in got, "a denied request still reached the origin"
    assert "/hello" not in origin.seen_paths, (
        f"the origin was contacted despite the denial: {origin.seen_paths!r}"
    )


def test_connect_to_an_allowed_host_opens_a_real_tunnel(proxy: _Proxy, origin: _Origin) -> None:
    """A tunnel, not a status line: bytes go through it and come back.

    Asserting only on `200 Connection established` would pass against a
    proxy that answers and then drops the connection -- the CONNECT path's
    version of a vacuous test.
    """
    conn = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
    conn.settimeout(10)
    try:
        conn.sendall(f"CONNECT localhost:{origin.port} HTTP/1.1\r\n\r\n".encode())
        head = conn.recv(4096)
        assert b"200 Connection established" in head, head[:200]

        conn.sendall(b"tunnelled-bytes")
        echoed = conn.recv(4096)
        assert echoed == b"tunnelled-bytes", (
            f"tunnel opened but carried nothing back: {echoed!r} -- the proxy "
            "answered 200 without connecting the two sockets"
        )
    finally:
        conn.close()


def test_connect_to_a_denied_host_is_refused(proxy: _Proxy, origin: _Origin) -> None:
    got = _speak(proxy, f"CONNECT 127.0.0.1:{origin.port} HTTP/1.1\r\n\r\n".encode())
    assert b"403 Forbidden" in got, got[:200]
    assert DENIAL_PREFIX.encode() in got, got[:200]
    assert b"200 Connection established" not in got


def test_origin_form_has_no_destination_and_is_refused(proxy: _Proxy) -> None:
    """A request with no destination in it must not be resolved from the
    `Host` header: that field is client-controlled independently of where
    the client is dialling, so trusting it would let the allow decision be
    made about a host the connection is not going to."""
    got = _speak(proxy, b"GET /hello HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert b"403 Forbidden" in got, got[:200]
    assert b"origin-form" in got, got[:200]


def test_the_decision_log_records_both_outcomes(proxy: _Proxy, origin: _Origin) -> None:
    """Checked LAST and separately: the log is a sensor, and SPEC.md
    section 11 makes events evidence rather than the boundary, so it may
    never stand in for the observed behaviour above."""
    import json

    _speak(
        proxy,
        f"GET http://localhost:{origin.port}/logged HTTP/1.1\r\nHost: localhost\r\n\r\n".encode(),
    )
    _speak(
        proxy,
        f"GET http://127.0.0.1:{origin.port}/blocked HTTP/1.1\r\nHost: x\r\n\r\n".encode(),
    )

    deadline = time.monotonic() + 5.0
    rows: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        if os.path.exists(proxy.decisions_path):
            with open(proxy.decisions_path) as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
            if len(rows) >= 2:
                break
        time.sleep(0.02)

    decisions = {(row["decision"], row["host"]) for row in rows}
    assert ("allow", "localhost") in decisions, rows
    assert ("deny", "127.0.0.1") in decisions, rows
