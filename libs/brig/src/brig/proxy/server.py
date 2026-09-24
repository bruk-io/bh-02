"""A minimal filtering HTTP/CONNECT proxy, loopback-only.

Scope, stated so nobody mistakes it for a general proxy: it speaks exactly
enough HTTP to make an allow/deny decision about a destination and then get
out of the way. It does not cache, does not rewrite, does not terminate TLS,
and does not inspect a tunnel's bytes once one is opened.

**The two paths are genuinely different and are never used as evidence
about each other** (`.claude/rules/integration-tests.md`: "plain HTTP is not
evidence about CONNECT tunnels"):

- `CONNECT host:port` -- the HTTPS path. The destination is read from the
  request line in cleartext, checked, and on success answered with
  `200 Connection established`, after which bytes are pumped blind.
- absolute-form `GET http://host/path` -- the plain-HTTP path. The
  destination is read from the URL, checked, and the request replayed
  upstream in origin form.

**The named gap** (SPEC.md §7's "SNI-co-hosting gap named in detail"): the
check binds the destination the client *asked for*, not the one it ends up
speaking to. Inside an opened tunnel a client sends whatever SNI it likes,
so a permitted host co-located with a forbidden one on the same address is
reachable. That is why this mechanism is graded `best_effort` at its best
and never `enforced`, and why the grade is `cooperative` when nothing but
env-vars routes the workload here -- a hostile process simply ignores
`HTTPS_PROXY` and connects directly. Confinement to this proxy is another
mechanism's job (a seatbelt rule, a netns); this file provides the filter,
never the confinement.
"""

from __future__ import annotations

import argparse
import json
import os
import selectors
import socket
import threading
import time
from typing import Final

from brig.proxy.filter import DENIAL_PREFIX, host_allowed, split_host_port

#: Bytes moved per pump iteration once a tunnel is open.
_CHUNK: Final = 65536
#: Cap on a request head. A client that sends more than this before its
#: blank line is answered with a denial, not read forever: this process
#: fronts a jail, and an unbounded read is a way for one to pin its memory.
_MAX_HEAD: Final = 16384
_HEAD_TIMEOUT_S: Final = 20.0
_UPSTREAM_TIMEOUT_S: Final = 30.0


class _Decisions:
    """The proxy's sensor output: one JSON line per allow/deny.

    Written directly to this proxy's own file: the process imports nothing
    from the library (see the package docstring), so the file format is the
    seam. It is the PROXY's file, not a jail-wide log -- brig keeps none
    (SPEC.md §11, decision-152) -- and a `run`-layer reader may fold it in
    wherever the embedder's records go. SPEC.md §11 makes events evidence,
    never a boundary, so a lost line here weakens an audit trail and never
    a denial.
    """

    def __init__(self, path: str | None) -> None:
        self._path = path
        self._lock = threading.Lock()

    def record(self, *, decision: str, host: str, port: int, detail: str = "") -> None:
        if self._path is None:
            return
        line = json.dumps(
            {
                "kind": "egress",
                "decision": decision,
                "host": host,
                "port": port,
                "detail": detail,
                "monotonic": round(time.monotonic(), 6),
            },
            sort_keys=True,
        )
        # Append-and-flush per line, opened per write: the reader may be
        # tailing this file while the jail runs, and a held buffer would
        # make a live read lag the decision it describes.
        with self._lock, open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()


def _read_head(conn: socket.socket) -> bytes:
    """Read up to and including the blank line ending the request head."""
    conn.settimeout(_HEAD_TIMEOUT_S)
    buf = bytearray()
    while b"\r\n\r\n" not in buf and b"\n\n" not in buf:
        if len(buf) > _MAX_HEAD:
            raise ValueError(f"request head exceeds {_MAX_HEAD} bytes")
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _deny(conn: socket.socket, host: str, why: str) -> None:
    body = f"{DENIAL_PREFIX}{host}\n{why}\n".encode()
    conn.sendall(
        b"HTTP/1.1 403 Forbidden\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n"
        b"\r\n" + body
    )


def _pump(a: socket.socket, b: socket.socket) -> None:
    """Move bytes both ways until either side closes.

    `selectors` rather than a thread per direction: two threads per tunnel
    plus one per connection is three per request, and this process is
    spawned per jail on a developer's machine, not on a server.
    """
    a.setblocking(False)
    b.setblocking(False)
    sel = selectors.DefaultSelector()
    sel.register(a, selectors.EVENT_READ, b)
    sel.register(b, selectors.EVENT_READ, a)
    try:
        while True:
            events = sel.select(timeout=_UPSTREAM_TIMEOUT_S)
            if not events:
                return
            for key, _ in events:
                src = key.fileobj
                dst = key.data
                assert isinstance(src, socket.socket)
                try:
                    chunk = src.recv(_CHUNK)
                except BlockingIOError, InterruptedError:
                    continue
                except OSError:
                    return
                if not chunk:
                    return
                try:
                    dst.sendall(chunk)
                except OSError:
                    return
    finally:
        sel.close()


def _connect_upstream(host: str, port: int) -> socket.socket:
    upstream = socket.create_connection((host, port), timeout=_UPSTREAM_TIMEOUT_S)
    upstream.settimeout(None)
    return upstream


def _handle_connect(
    conn: socket.socket, authority: str, allow: tuple[str, ...], log: _Decisions
) -> None:
    try:
        host, port = split_host_port(authority, default_port=443)
    except ValueError as exc:
        log.record(decision="deny", host=authority, port=0, detail=str(exc))
        _deny(conn, authority, f"unparseable authority: {exc}")
        return
    if not host_allowed(host, allow):
        log.record(decision="deny", host=host, port=port, detail="not in allow list")
        _deny(conn, host, "host is not in this jail's network allow list")
        return
    try:
        upstream = _connect_upstream(host, port)
    except OSError as exc:
        # NOT a denial: an upstream that is down must not look like a policy
        # decision, or a probe reading the denial signature would call a
        # network outage a working sandbox.
        log.record(decision="allow", host=host, port=port, detail=f"upstream unreachable: {exc}")
        conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        return
    log.record(decision="allow", host=host, port=port)
    with upstream:
        conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        conn.settimeout(None)
        _pump(conn, upstream)


def _handle_absolute(
    conn: socket.socket, method: str, url: str, rest: bytes, allow: tuple[str, ...], log: _Decisions
) -> None:
    without_scheme = url.split("://", 1)[1]
    authority, slash, path = without_scheme.partition("/")
    try:
        host, port = split_host_port(authority, default_port=80)
    except ValueError as exc:
        log.record(decision="deny", host=authority, port=0, detail=str(exc))
        _deny(conn, authority, f"unparseable authority: {exc}")
        return
    if not host_allowed(host, allow):
        log.record(decision="deny", host=host, port=port, detail="not in allow list")
        _deny(conn, host, "host is not in this jail's network allow list")
        return
    try:
        upstream = _connect_upstream(host, port)
    except OSError as exc:
        log.record(decision="allow", host=host, port=port, detail=f"upstream unreachable: {exc}")
        conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        return
    log.record(decision="allow", host=host, port=port)
    origin_form = (slash + path) if slash else "/"
    head = f"{method} {origin_form} HTTP/1.1\r\n".encode() + rest
    with upstream:
        upstream.sendall(head)
        conn.settimeout(None)
        _pump(conn, upstream)


def handle(conn: socket.socket, allow: tuple[str, ...], log: _Decisions) -> None:
    """Serve one client connection to completion, then close it."""
    with conn:
        try:
            head = _read_head(conn)
        except (OSError, ValueError) as exc:
            with contextlib_suppress_oserror():
                _deny(conn, "-", f"unreadable request: {exc}")
            return
        if not head:
            return
        first_line, _, rest = head.partition(b"\r\n")
        fields = first_line.decode("latin-1").split()
        if len(fields) < 2:
            with contextlib_suppress_oserror():
                _deny(conn, "-", "malformed request line")
            return
        method, target = fields[0], fields[1]
        try:
            if method.upper() == "CONNECT":
                _handle_connect(conn, target, allow, log)
            elif "://" in target:
                _handle_absolute(conn, method, target, rest, allow, log)
            else:
                # Origin-form to a proxy has no destination in it. Refusing
                # is the honest answer; guessing one from the Host header
                # would make the allow decision depend on a field the
                # client controls independently of where it is dialling.
                log.record(decision="deny", host="-", port=0, detail="origin-form request")
                _deny(
                    conn,
                    "-",
                    "origin-form request has no destination; use CONNECT or absolute-form",
                )
        except OSError:
            return


class contextlib_suppress_oserror:
    """`contextlib.suppress(OSError)` without the import.

    A denial sent to a client that has already hung up raises, and that is
    not worth a traceback -- but the package docstring's point about a
    small import graph applies to the stdlib too when the alternative is
    four lines.
    """

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc, OSError)


def serve(
    *, allow: tuple[str, ...], port_file: str | None, log_path: str | None, ready_fd: int | None
) -> None:
    """Bind loopback, publish the port, and serve until killed.

    Binds `127.0.0.1` explicitly, never `0.0.0.0`: this proxy exists to be
    the one egress path for a local jail, and a filter reachable from the
    network is an open relay wearing a sandbox's name.

    Port 0 plus a published port file is deliberate. A fixed port collides
    when two jails run at once, and the collision surfaces as one jail
    silently using another's policy -- so the kernel picks, and the caller
    learns the number by reading `port_file` after it appears. The file is
    written to a temporary name and renamed, so a reader never sees a
    half-written port.
    """
    log = _Decisions(log_path)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(64)
    port = server.getsockname()[1]

    if port_file is not None:
        tmp = f"{port_file}.tmp{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(str(port))
        os.replace(tmp, port_file)
    if ready_fd is not None:
        os.write(ready_fd, f"{port}\n".encode())
        os.close(ready_fd)

    with server:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn, allow, log), daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brig.proxy", description=__doc__)
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="HOST",
        help="permitted destination; exact name or *.suffix. Repeatable. "
        "No --allow at all denies everything, which is a valid policy.",
    )
    parser.add_argument("--port-file", help="path the chosen port is published to")
    parser.add_argument("--log", dest="log_path", help="path decisions are appended to as JSONL")
    parser.add_argument(
        "--ready-fd", type=int, help="fd the chosen port is written to, then closed"
    )
    args = parser.parse_args(argv)
    serve(
        allow=tuple(args.allow),
        port_file=args.port_file,
        log_path=args.log_path,
        ready_fd=args.ready_fd,
    )
    return 0
