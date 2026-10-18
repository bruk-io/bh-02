"""`connect_proxy` through a real launch: the mechanism, the helper, and
the workload's own view of the network.

This is the seam test the two tiers below it cannot reach.
`test_connect_proxy_compile.py` proves the render; `test_proxy_egress.py`
proves the filter; neither proves that a launched workload is actually
POINTED at that filter and constrained by it. Here a real
`Jail.create` and `jail.start` compiles the mechanism, starts the helper, and runs a
workload that makes real HTTP requests -- and the claim is read from what
the WORKLOAD saw, never from the proxy's log or the report.

THE CONTROL is built the same way as `test_proxy_egress.py`'s: allowed and
denied requests reach the SAME real origin over loopback by two names that
both resolve to it (`localhost` permitted, `127.0.0.1` not), so a denial
cannot be explained by unreachability.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Iterator

import pytest

from brig.core import NetworkPolicy, Spec
from brig.mech import CompileCtx
from brig.mech.connect_proxy import DECISIONS_FILE, PORT_FILE, ConnectProxy
from brig.run import IoPolicy
from brig.stack import CompiledJail
from tests.conftest import launch, workload_argv

pytestmark = pytest.mark.integration

_BODY = b"origin-server-payload"


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


@pytest.fixture(autouse=True)
def _launching_environment_exempts_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """TASK-0076: the launching environment holds a NO_PROXY naming loopback, as
    many hosts' do. The jail must not inherit it: a workload that did would
    reach the origin directly, outside the egress filter."""
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "localhost,127.0.0.1,::1,169.254.0.0/16")


@pytest.fixture
def origin() -> Iterator[_Origin]:
    server = _Origin()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def jail_dir() -> Iterator[str]:
    """A jail directory nothing has ever been in, removed after the test.

    **It is new on purpose, never named from the process id.** The wrap reads
    `proxy.port` the moment the workload starts, and the proxy publishes it
    some tens of milliseconds later (Python start-up), so a directory that
    already holds one -- a jail's earlier run left it -- is read first: the
    workload is pointed at a port nobody listens on and its request dies with
    `ConnectionRefusedError`, where the 403 under test was due (TASK-0140). A
    directory named `/tmp/bp<pid>-<n>` and kept is exactly that: a later
    process that gets the same pid (a pid space of 32768 wraps within a day of
    test runs) is handed the earlier one's files, and the failure reads as a
    proxy that did not deny. A fresh `mkdtemp` directory cannot be anyone's
    earlier jail, so the race is not run at all.

    Short, under `/tmp` and not `tmp_path`: the proxy's port file and the
    leak sweep's argv both want short paths. Resolved, as `CompileCtx`
    requires of a `jail_dir`.
    """
    path = os.path.realpath(tempfile.mkdtemp(prefix="bp", dir="/tmp"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _jail(jail_dir: str, domains: tuple[str, ...]) -> tuple[CompiledJail, object]:
    """Compile the mechanism into a single-step jail.

    Built here rather than through a preset stack on purpose: a preset
    would drag in seatbelt and rlimits, and a failure would not say which
    mechanism caused it. One mechanism per integration test
    (`.claude/rules/integration-tests.md`).
    """
    from brig.core import unenforced_report

    step = ConnectProxy(sys.executable).compile(
        Spec(network=NetworkPolicy(allowed_domains=domains)),
        CompileCtx(jail_dir=jail_dir, platform=sys.platform),
    )
    jail = CompiledJail(
        spec=Spec(network=NetworkPolicy(allowed_domains=domains)),
        report=unenforced_report(),
        wrap=step.wrap,
        env=dict(step.env),
        staged=step.staged,
        helpers=step.helpers,
        requires=step.requires,
        mechanism_names=("connect_proxy",),
        matrix_version=1,
    )
    return jail, step


def _fetch_script(url: str, out: str) -> str:
    """A workload that fetches `url` HONOURING the proxy variables.

    `urllib` reads `http_proxy` from the environment on its own, which is
    the point: the mechanism's whole delivery is those variables, so the
    workload must be something that consults them the way a real tool
    does, not something handed the proxy address directly.
    """
    return (
        f"{sys.executable} -c "
        f'"import urllib.request,sys;'
        f"open({out!r},'w').write("
        f"(lambda: (lambda r: 'OK:'+r.read().decode())(urllib.request.urlopen({url!r},timeout=15)))()"
        f" if True else '')\" 2>{out}.err"
    )


def _run(jail_dir: str, domains: tuple[str, ...], body: str, run_id: str):  # type: ignore[no-untyped-def]
    jail, _step = _jail(jail_dir, domains)
    return launch(
        jail,
        argv=workload_argv(run_id, body),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-connect-proxy",
        jail_dir=jail_dir,
    )


#: How long a file's contents must stop changing before `_wait_file`
#: believes the writer is done with it. See that function.
_SETTLE_S = 0.15


def _read_nonempty(path: str) -> str | None:
    """`path`'s whole contents, or `None` while it is absent or empty."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path) as fh:
        return fh.read() or None


def _wait_file(path: str, timeout: float = 25.0) -> str | None:
    """`path`'s contents once the writer has stopped adding to them, or
    `None` if they never became non-empty AND SETTLED within `timeout`.

    THE SETTLE IS LOAD-BEARING, not caution. `{out}.err` is the shell's
    `2>` redirect of the workload's stderr, and a Python traceback reaches
    it line by line, so a reader that returned at the first non-empty read
    could get exactly `"Traceback (most recent call last):\n"` and nothing
    else -- which is a real, observed intermittent failure of the 403
    assertion below, and one that reads as "the proxy did not deny" when
    what actually happened is "the test looked too early".

    WHICH IS WHY THE DEADLINE RETURNS `None`, not the last read. Handing
    back a snapshot that was still growing when the clock ran out would put
    the truncated read this function exists to prevent back into the
    caller's hands, and silently -- indistinguishable, at the call site,
    from a write that genuinely finished. Every caller already treats
    `None` as "no answer" and says so in its own message, so an unsettled
    write fails as the unsettled write it is. One extra settle is granted
    past the nominal deadline first: a write that came to rest exactly on
    the boundary is a finished write, and should not be thrown away for
    landing late.
    """
    deadline = time.monotonic() + timeout
    previous: str | None = None
    while time.monotonic() < deadline:
        current = _read_nonempty(path)
        if current is None:
            time.sleep(0.05)
            continue
        if current == previous:
            return current
        previous = current
        time.sleep(_SETTLE_S)
    if previous is None:
        return None
    time.sleep(_SETTLE_S)
    final = _read_nonempty(path)
    return final if final == previous else None


def test_the_workload_reaches_an_allowed_host_through_the_proxy(
    run_id: str, jail_dir: str, origin: _Origin
) -> None:
    """THE CONTROL: the origin's own payload arrives in the workload's
    hands, so the proxy variables were set, the helper was running, and
    traffic actually flowed."""
    out = os.path.join(jail_dir, "got")
    jail, process = _run(
        jail_dir,
        ("localhost",),
        _fetch_script(f"http://localhost:{origin.port}/x", out),
        run_id,
    )
    try:
        got = _wait_file(out)
        assert got is not None, (
            "the workload produced nothing -- see "
            f"{out}.err and {os.path.join(jail_dir, PORT_FILE)}"
        )
        assert got == "OK:" + _BODY.decode(), got
    finally:
        jail.destroy()


def test_the_workload_is_refused_a_host_outside_the_allow_list(
    run_id: str, jail_dir: str, origin: _Origin
) -> None:
    """Same reachable origin, by a name the policy does not permit. The
    workload sees an HTTP 403 carrying the proxy's own signature -- not a
    connection error, which is what a test against an unreachable host
    would have produced whether or not any policy existed."""
    out = os.path.join(jail_dir, "got")
    jail, process = _run(
        jail_dir,
        ("localhost",),
        _fetch_script(f"http://127.0.0.1:{origin.port}/x", out),
        run_id,
    )
    try:
        err = _wait_file(f"{out}.err")
        assert err is not None, "the workload neither succeeded nor failed"
        assert "403" in err, err
        assert _BODY.decode() not in (_wait_file(out, timeout=1.0) or ""), (
            "a denied request still returned the origin's payload"
        )
    finally:
        jail.destroy()


def test_the_denial_signature_matches_what_the_proxy_actually_wrote(
    run_id: str, jail_dir: str, origin: _Origin
) -> None:
    """The signature is only worth having if it matches the real wire
    text. Checked against bytes the running proxy produced, not against a
    constructed string -- the drift this catches is exactly the one the
    duplicated constant makes possible (decision-133)."""
    out = os.path.join(jail_dir, "got")
    _jail_obj, step = _jail(jail_dir, ("localhost",))
    jail, process = _run(
        jail_dir,
        ("localhost",),
        # `--` reads the body verbatim: urllib raises on 403, so the body
        # is fetched from the exception, which is where the proxy's text is.
        f'{sys.executable} -c "import urllib.request,urllib.error;'
        f"\nimport sys\ntry:\n urllib.request.urlopen('http://127.0.0.1:{origin.port}/x',timeout=15)\n"
        f"except urllib.error.HTTPError as e:\n open({out!r},'wb').write(e.read())\" ",
        run_id,
    )
    try:
        body = _wait_file(out)
        assert body is not None, "the proxy's 403 body never reached the workload"
        pattern = step.denial_signatures[0]  # type: ignore[attr-defined]
        assert pattern.search(body), (
            f"the mechanism's denial signature does not match the proxy's real wire text: {body!r}"
        )
    finally:
        jail.destroy()


def test_the_helper_dies_with_the_jail(run_id: str, jail_dir: str, origin: _Origin) -> None:
    """A surviving proxy is a listening socket nobody owns. Proven alive
    first, so "gone after kill" cannot pass against one that never ran."""
    jail, process = _run(jail_dir, ("localhost",), "sleep 30", run_id)
    assert len(jail._base.helper_pids) == 1
    pid = jail._base.helper_pids[0]
    try:
        assert _wait_file(os.path.join(jail_dir, PORT_FILE)) is not None, (
            "the proxy helper never published a port"
        )
        assert os.path.exists(os.path.join(jail_dir, PORT_FILE))
        alive = subprocess_alive(pid)
        assert alive, f"proxy helper {pid} is not running while the jail is up"
    finally:
        jail.destroy()

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and subprocess_alive(pid):
        time.sleep(0.05)
    assert not subprocess_alive(pid), f"proxy helper {pid} outlived its jail"


def subprocess_alive(pid: int) -> bool:
    import subprocess

    done = subprocess.run(
        ["/bin/ps", "-o", "state=", "-p", str(pid)], capture_output=True, text=True
    )
    return done.stdout.strip() not in ("", "Z")


def test_the_decisions_file_lands_where_the_mechanism_said_it_would(
    run_id: str, jail_dir: str, origin: _Origin
) -> None:
    """The compile-time `decisions_path` and the file the proxy actually
    writes must be the same path, or a `run`-layer reader
    (`brig.run.egress_decisions`) reads nothing.

    **The wait is on the PROXY going idle, never on the workload's output.**
    Those are two different processes writing two different files, and the
    workload's is neither necessary nor sufficient for this one: a workload
    can have the origin's bytes in hand before the proxy has flushed the line
    describing how they got there, and a workload that failed for its own
    reasons says nothing about whether a decision was recorded. Waiting for
    the workload first was therefore a wait for the wrong event that happened
    to usually be late enough. What "idle" means here is exactly what
    `_wait_file` measures: the decisions file has become non-empty and has
    stopped changing.
    """
    out = os.path.join(jail_dir, "got")
    jail, process = _run(
        jail_dir,
        ("localhost",),
        _fetch_script(f"http://localhost:{origin.port}/x", out),
        run_id,
    )
    try:
        text = _wait_file(os.path.join(jail_dir, DECISIONS_FILE))
        assert text is not None, "no decisions file at the announced path"
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        assert any(row["decision"] == "allow" and row["host"] == "localhost" for row in rows), rows
    finally:
        jail.destroy()
