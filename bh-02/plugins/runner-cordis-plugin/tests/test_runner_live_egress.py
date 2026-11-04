"""The grants battery, in real jails (decision-0012 items 4, 6 and 8, TASK-0181.07 and .09): what a
jail's proxy refuses is asked while the program runs and, on yes, the program's next connection is
reached with no restart; a declined one stays refused; a revoke refuses the next connection and
leaves an open one open; a grant already kept as always is reached by the first connection with
nothing asked; a program that ignores the proxy reaches nothing, granted or not; and the grades are
honest about it (`network` best-effort and never enforced, `egress` proxied, still confined).
The names resolve from a table (`egress_hosts`, the seam brig gives a test) to the host's loopback,
which is a private address, so each destination is granted twice: the name, then the address.

They run only in a real jail, so they skip on the host; `scripts/linux-jail-check` proves them."""

import asyncio
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from runner_cordis_plugin import BrigConfig, BrigJail, Broker, Unjailed, is_confined, store
from runner_cordis_plugin.commands import grants_command
from runner_cordis_plugin.grants import Answer, Asker, Grant, Kind, Request, Source
from runner_cordis_plugin.prompting import question

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").exists(),
    reason="the jail is bubblewrap's: Linux with /usr/bin/bwrap only",
)


@dataclass(frozen=True)
class _Host:
    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""
    grants: str = ""


# Listens (the jail sees it ready), then every 0.2 s asks the proxy the jail reaches (127.0.0.1:3128)
# to connect to argv[2] and appends what that came to in argv[3]. The first connection that is let
# through is kept open, and each round sends `ping` down it: its line says `pong` or `broken`.
_REACH_AGAIN_AND_AGAIN = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
target, log = sys.argv[2], sys.argv[3]
tunnel = None
while True:
    link, status = None, "refused"
    try:
        link = socket.create_connection(("127.0.0.1", 3128), timeout=10)
        link.sendall(f"CONNECT {target} HTTP/1.1\\r\\nHost: {target}\\r\\n\\r\\n".encode())
        head = b""
        while b"\\r\\n\\r\\n" not in head:
            head += link.recv(1)
        status = head.split(b"\\r\\n")[0].decode().split(" ", 2)[1]
    except OSError as error:
        status = type(error).__name__
    if status == "200" and tunnel is None:
        tunnel = link
    elif link is not None:
        link.close()
    held = "none"
    if tunnel is not None:
        try:
            tunnel.sendall(b"ping")
            held = "pong" if tunnel.recv(4) == b"pong" else "broken"
        except OSError:
            held = "broken"
    with open(log, "a") as out:
        out.write(f"new {status} tunnel {held} pid {os.getpid()}\\n")
    time.sleep(0.2)
"""


# Listens (the jail sees it ready), then connects to the host server's port on 127.0.0.1 twice and
# logs what each came to: first directly, ignoring the proxy settings, then through the proxy
# (127.0.0.1:3128, CONNECT), where it sends `ping` down the tunnel and logs the answer.
_IGNORE_THE_PROXY = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
port, log = int(sys.argv[2]), sys.argv[3]
try:
    socket.create_connection(("127.0.0.1", port), timeout=5).close()
    direct = "reached"
except OSError as error:
    direct = "failed " + type(error).__name__
try:
    link = socket.create_connection(("127.0.0.1", 3128), timeout=10)
    link.sendall(f"CONNECT 127.0.0.1:{port} HTTP/1.1\\r\\nHost: 127.0.0.1:{port}\\r\\n\\r\\n".encode())
    head = b""
    while b"\\r\\n\\r\\n" not in head:
        head += link.recv(1)
    status = head.split(b"\\r\\n")[0].decode().split(" ", 2)[1]
    answer = ""
    if status == "200":
        link.sendall(b"ping")
        answer = link.recv(4).decode()
    proxied = f"{status} {answer}"
except OSError as error:
    proxied = "failed " + type(error).__name__
with open(log, "w") as out:
    out.write(f"direct {direct}\\nproxied {proxied}\\n")
time.sleep(60)
"""

# Listens (the jail sees it ready) and does nothing else.
_LISTEN_ONLY = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
time.sleep(60)
"""


@contextmanager
def _a_host_server() -> Iterator[int]:
    """A server on the host's loopback: it answers `pong` to each `ping` on a connection, until the
    connection closes. Yields its port."""
    server = socket.create_server(("127.0.0.1", 0))
    server.settimeout(0.2)
    done = threading.Event()

    def serve(connection: socket.socket) -> None:
        with connection:
            while connection.recv(4):
                connection.sendall(b"pong")

    def accept() -> None:
        while not done.is_set():
            try:
                connection, _ = server.accept()
            except OSError:
                continue
            threading.Thread(target=serve, args=(connection,), daemon=True).start()

    thread = threading.Thread(target=accept)
    thread.start()
    try:
        yield server.getsockname()[1]
    finally:
        done.set()
        thread.join(timeout=5)
        server.close()


class _Person:
    """The prompt: answers each question `answer`, and keeps what it was asked and how it was put."""

    def __init__(self, answer: Answer = Answer.ONCE) -> None:
        self.answer = answer
        self.asked: list[Request] = []
        self.shown: list[dict[str, object]] = []

    async def __call__(self, request: Request) -> Answer | None:
        self.asked.append(request)
        self.shown.append(question(request, places=(), runtime_dir=""))
        return self.answer


async def _lines(log: Path, until: Callable[[list[str]], bool], *, what: str) -> list[str]:
    """What the program logged, once `until` holds of it (15 s at most)."""
    deadline = time.monotonic() + 15
    lines: list[str] = []
    while time.monotonic() < deadline:
        lines = log.read_text().splitlines() if log.exists() else []
        if until(lines):
            return lines
        await asyncio.sleep(0.1)
    raise AssertionError(f"{what}: after 15 s the program had logged {lines[-5:]}")


def _argv(target: str, log: Path) -> Callable[[str], list[str]]:
    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", _REACH_AGAIN_AND_AGAIN, endpoint, target, str(log)]

    return argv


async def test_a_refused_destination_is_asked_and_on_yes_the_next_connection_is_reached_without_a_restart(
    tmp_path: Path,
) -> None:
    """The program asks for `svc.test:PORT` again and again. The proxy refuses the name (asked as the
    name), then the address the name resolved to, which is private (asked as the IP literal, with its
    warning); on the two yeses the program's next connection reaches the host server, in the one jail
    and the one process it started with. Seen failing: with `Egress.begin` not called, the program
    was refused for 15 s and the question never asked."""
    project = tmp_path / "project"
    project.mkdir()
    log = project / "log"
    before = asyncio.all_tasks()
    with _a_host_server() as port:
        broker = Broker(None)
        person = _Person()
        broker.serve(person)
        one = BrigJail(BrigConfig(), _Host(), egress_hosts={"svc.test": ("127.0.0.1",)}, grants=broker)
        started = await one.start(_argv(f"svc.test:{port}", log), cwd=str(project), owner="python")
        try:
            lines = await _lines(
                log, lambda each: any(line.startswith("new 200") for line in each), what="reached"
            )
        finally:
            await started.stop()
    assert lines[0].startswith("new 403")
    assert [request.grant for request in person.asked] == [
        Grant(Kind.NET, "svc.test", port),
        Grant(Kind.NET, "127.0.0.1", port),
    ]
    assert {request.asker for request in person.asked} == {Asker(Source.INPUT, "python")}
    assert person.shown[0]["warning"] == ""
    assert "not a public address" in str(person.shown[1]["warning"])
    assert len({line.split(" pid ")[1] for line in lines}) == 1  # one process the whole time
    await asyncio.sleep(0.3)
    assert {task for task in asyncio.all_tasks() - before if not task.done()} == set()  # nothing outlives it


async def test_a_name_that_resolves_to_loopback_is_asked_as_the_ip_literal_alone(tmp_path: Path) -> None:
    """`svc.test` is granted; it resolves to 127.0.0.1, a private address, which the proxy refuses as
    `private-address`: the question is `net 127.0.0.1:PORT` and no other, and it says it reaches the
    person's network."""
    project = tmp_path / "project"
    project.mkdir()
    log = project / "log"
    with _a_host_server() as port:
        broker = Broker(None)
        person = _Person()
        broker.serve(person)
        await broker.ask(Request(Grant(Kind.NET, "svc.test", port), Asker(Source.ROW, "test"), "it fetches"))
        one = BrigJail(BrigConfig(), _Host(), egress_hosts={"svc.test": ("127.0.0.1",)}, grants=broker)
        started = await one.start(_argv(f"svc.test:{port}", log), cwd=str(project), owner="python")
        try:
            await _lines(log, lambda each: any(line.startswith("new 200") for line in each), what="reached")
        finally:
            await started.stop()
    private = [request for request in person.asked if request.grant.target != "svc.test"]
    assert [request.grant for request in private] == [Grant(Kind.NET, "127.0.0.1", port)]
    assert [request.grant.target for request in person.asked] == ["svc.test", "127.0.0.1"]
    assert "on your network" in str(person.shown[1]["warning"])
    assert "127.0.0.1" in private[0].reason and "svc.test" in private[0].reason


async def test_a_revoke_refuses_the_next_connection_and_leaves_an_open_one_open_and_says_so(
    tmp_path: Path,
) -> None:
    """Both destinations are always-grants, so the program opens a tunnel and keeps it. `/grants revoke`
    of the name takes it from the running jail: the next connection is refused while the tunnel, open
    since before, still carries `ping`/`pong`, and the words say open connections stay open. Seen
    failing: with no sync of a revoke to the running jail, the program was still let through."""
    project = tmp_path / "project"
    project.mkdir()
    log = project / "log"
    directory = tmp_path / "state" / "grants"
    with _a_host_server() as port:
        asker = Asker(Source.ROW, "test")
        directory.mkdir(parents=True, mode=0o700)
        name, address = Grant(Kind.NET, "svc.test", port), Grant(Kind.NET, "127.0.0.1", port)
        store.write(directory, [Request(name, asker, "it fetches"), Request(address, asker, "it fetches")])
        broker = Broker(directory)
        one = BrigJail(
            BrigConfig(),
            _Host(grants=str(directory)),
            egress_hosts={"svc.test": ("127.0.0.1",)},
            grants=broker,
        )
        started = await one.start(_argv(f"svc.test:{port}", log), cwd=str(project), owner="python")
        try:
            await _lines(
                log, lambda each: any(line.startswith("new 200 tunnel pong") for line in each), what="open"
            )
            (entry,) = [each for each in await broker.list() if each.request.grant == name]
            said = await grants_command(broker, f"revoke {entry.id}")
            mark = len(log.read_text().splitlines())
            after = await _lines(
                log,
                lambda each: any(
                    " tunnel pong" in line and line.startswith("new 403") for line in each[mark:]
                ),
                what="refused",
            )
        finally:
            await started.stop()
    assert "connections already open" in said and "stay open" in said
    refused = [line for line in after[mark:] if line.startswith("new 403")]
    assert refused and all("tunnel pong" in line for line in refused)  # the open one was not cut


def _listen_only(endpoint: str) -> list[str]:
    return [sys.executable, "-I", "-c", _LISTEN_ONLY, endpoint]


async def test_a_program_that_ignores_the_proxy_reaches_nothing_though_the_destination_is_granted(
    tmp_path: Path,
) -> None:
    """`net 127.0.0.1:PORT` stands as an always-grant for a listener on the host's loopback. From
    inside the jail a direct `socket.create_connection` to it fails (the jail's loopback is its own,
    and nothing listens there), while the same destination through the proxy is reached and carries
    `ping`/`pong`: a grant opens the proxy's door and no other."""
    project = tmp_path / "project"
    project.mkdir()
    log = project / "log"
    directory = tmp_path / "state" / "grants"
    directory.mkdir(parents=True, mode=0o700)
    with _a_host_server() as port:
        address = Grant(Kind.NET, "127.0.0.1", port)
        store.write(directory, [Request(address, Asker(Source.ROW, "test"), "it fetches")])
        one = BrigJail(BrigConfig(), _Host(grants=str(directory)), grants=Broker(directory))

        def argv(endpoint: str) -> list[str]:
            return [sys.executable, "-I", "-c", _IGNORE_THE_PROXY, endpoint, str(port), str(log)]

        started = await one.start(argv, cwd=str(project), owner="python")
        try:
            lines = await _lines(log, lambda each: len(each) == 2, what="both connections")
        finally:
            await started.stop()
    assert lines[0].startswith("direct failed "), lines
    assert lines[1] == "proxied 200 pong"


async def test_a_declined_destination_is_asked_once_and_stays_refused(tmp_path: Path) -> None:
    """The person says no: the program is refused again and again, and the question is asked once
    (a no is kept for the session)."""
    project = tmp_path / "project"
    project.mkdir()
    log = project / "log"
    with _a_host_server() as port:
        broker = Broker(None)
        person = _Person(Answer.NO)
        broker.serve(person)
        one = BrigJail(BrigConfig(), _Host(), egress_hosts={"svc.test": ("127.0.0.1",)}, grants=broker)
        started = await one.start(_argv(f"svc.test:{port}", log), cwd=str(project), owner="python")
        try:
            lines = await _lines(log, lambda each: len(each) >= 6, what="refused again and again")
        finally:
            await started.stop()
    assert all(line.startswith("new 403") for line in lines)
    assert [request.grant for request in person.asked] == [Grant(Kind.NET, "svc.test", port)]


async def test_a_grant_kept_as_always_is_reached_by_the_first_connection_with_nothing_asked(
    tmp_path: Path,
) -> None:
    """The name and its address are always-grants in `grants.toml` before the start: the program's
    first connection is let through, and the person was never asked."""
    project = tmp_path / "project"
    project.mkdir()
    log = project / "log"
    directory = tmp_path / "state" / "grants"
    directory.mkdir(parents=True, mode=0o700)
    with _a_host_server() as port:
        asker = Asker(Source.ROW, "test")
        name, address = Grant(Kind.NET, "svc.test", port), Grant(Kind.NET, "127.0.0.1", port)
        store.write(directory, [Request(name, asker, "it fetches"), Request(address, asker, "it fetches")])
        broker = Broker(directory)
        person = _Person()
        broker.serve(person)
        one = BrigJail(
            BrigConfig(),
            _Host(grants=str(directory)),
            egress_hosts={"svc.test": ("127.0.0.1",)},
            grants=broker,
        )
        started = await one.start(_argv(f"svc.test:{port}", log), cwd=str(project), owner="python")
        try:
            lines = await _lines(log, lambda each: bool(each), what="a first connection")
        finally:
            await started.stop()
    assert lines[0].startswith("new 200"), lines
    assert person.asked == []


async def test_a_real_start_grades_the_network_best_effort_and_proxied_and_approval_counts_it_confined(
    tmp_path: Path,
) -> None:
    """The grades are honest: brig cannot vouch for more than best effort on `network`, so it is never
    `enforced`, and `egress` says the only route is the proxy's; `approval` counts that as confined.
    A start with a destination granted grades the same."""
    project = tmp_path / "project"
    project.mkdir()
    directory = tmp_path / "state" / "grants"
    directory.mkdir(parents=True, mode=0o700)
    grant = Grant(Kind.NET, "svc.test", 443)
    store.write(directory, [Request(grant, Asker(Source.ROW, "test"), "it fetches")])
    for broker in (Broker(None), Broker(directory)):
        one = BrigJail(BrigConfig(), _Host(grants=str(directory)), grants=broker)
        started = await one.start(_listen_only, cwd=str(project), owner="python")
        try:
            report = started.report()
        finally:
            await started.stop()
        assert report["network"] == "best_effort" and report["egress"] == "proxied", report
        assert is_confined(report)


async def test_an_unconfined_start_grades_every_part_unenforced_and_is_not_confined(tmp_path: Path) -> None:
    """`--no-jail`: nothing is graded better than unenforced, and approval asks."""
    started = await Unjailed().start(_listen_only, cwd=str(tmp_path), owner="python")
    try:
        report = started.report()
    finally:
        await started.stop()
    assert set(report.values()) == {"unenforced"}
    assert not is_confined(report)
