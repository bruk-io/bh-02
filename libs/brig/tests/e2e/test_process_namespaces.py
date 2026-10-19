"""Each process of a supervised jail in namespaces of its own, from inside a real jail
(decision-195, decision-196, TASK-0079.07).

Every claim here is made by a program the jail runs, and every one has its control beside it: the
same program in a jail whose processes have no namespaces of their own (`namespaces=False`, the
block of decision-195 planted; also what a jail run as uid 0 is, and then the control is the whole
suite). Two processes of the second can see, signal and connect to each other here, so a refusal in
the first is the namespaces' doing and not the sandbox's.

Each test runs in both modes, `namespaces` and `fallback`, and states what each shows. Where the
host gives no namespaces (a jail run as uid 0, a host that blocks nested user namespaces) the first
mode skips, by name, and the fallback is what runs: it is the criterion that start falls back and
says so.
"""

from __future__ import annotations

import json
import os
import random
import re
import signal
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

import brig.run.teardown as teardown
from brig.core import Grade
from brig.run import ExecFidelity, HostRuntime, Jail, KillOutcome, Process, RuntimeKind
from tests.conftest import NewJailDir
from tests.supervised_jail import (
    blocked,
    create_jail,
    needs_a_supervised_jail,
    needs_namespaces,
    python,
    running_with,
    sh,
    stderr_of,
    the_kernel_gives_namespaces_in_a_jail,
    unique_sleep,
    until,
)

pytestmark = pytest.mark.e2e

_STOP_GRACE_S = 2.0


@pytest.fixture(autouse=True)
def _needs_a_jail() -> None:
    needs_a_supervised_jail()


@pytest.fixture(params=["namespaces", "fallback"])
def mode(request: pytest.FixtureRequest) -> str:
    if request.param == "namespaces":
        needs_namespaces()
    return str(request.param)


Rig = Callable[..., tuple[Jail, str]]


@pytest.fixture
def make(mode: str, new_jail_dir: NewJailDir) -> Iterator[Rig]:
    """`make(channel=..., scratch=...)` is a jail of the mode under test and a workspace in
    which processes leave each other files to look for. Everything it made is ended, and
    nothing it names is allowed to be left, when the test is done: the jails are destroyed
    here, and the directories removed after, by `new_jail_dir`."""
    made: list[Jail] = []

    def build(
        *, channel: bool = False, scratch: bool = False, jail_id: str = "probed"
    ) -> tuple[Jail, str]:
        jail_dir = new_jail_dir()
        workspace = new_jail_dir()
        os.chmod(workspace, 0o777)
        jail = create_jail(
            jail_dir,
            workspace=workspace,
            channel=channel,
            scratch=scratch,
            namespaces=mode == "namespaces",
            jail_id=jail_id,
        )
        made.append(jail)
        return jail, workspace

    yield build
    for jail in made:
        report = jail.destroy()
        assert not [i for i in report.items if i.outcome is KillOutcome.FAILED], report


def _isolated(mode: str) -> bool:
    return mode == "namespaces"


def _nspid(pid: int) -> list[int]:
    """The pids `pid` has, host's first, from `NSpid` in `/proc/<pid>/status`, read by the host."""
    text = Path(f"/proc/{pid}/status").read_text()
    found = re.search(r"^NSpid:\s+(.*)$", text, re.MULTILINE)
    assert found is not None
    return [int(number) for number in found.group(1).split()]


def _said(process: Process, word: str, timeout: float = 15.0) -> str:
    """What `process` has written to its stdout once it holds `word`, polled."""
    assert until(lambda: word in Path(process.stdout_path).read_text(errors="replace"), timeout), (
        f"{word!r} never came: {Path(process.stdout_path).read_text()!r} {stderr_of(process)!r}"
    )
    return Path(process.stdout_path).read_text()


def _json_of(process: Process) -> dict[str, object]:
    """The one JSON line `process` printed."""
    assert until(lambda: Path(process.stdout_path).read_text().strip().endswith("}"), 15.0), (
        Path(process.stdout_path).read_text(),
        stderr_of(process),
    )
    return dict(json.loads(Path(process.stdout_path).read_text().splitlines()[0]))


def _up(path: str) -> bool:
    return os.path.exists(path)


# ---------------------------------------------------------------------------------------------
# A process is PID 1 of a pid namespace of its own, with a /proc for it.
# ---------------------------------------------------------------------------------------------

_WHO = r"""
import json, os, time
pids = sorted(int(name) for name in os.listdir('/proc') if name.isdigit())
print(json.dumps({"pid": os.getpid(), "uid": os.getuid(), "gid": os.getgid(), "pids": pids}), flush=True)
time.sleep(60)
"""

_NAMESPACES = (
    "import os, time; print(*(os.readlink('/proc/self/ns/' + n) for n in "
    "('user', 'mnt', 'pid', 'net', 'ipc')), flush=True); time.sleep(60)"
)


def test_a_process_is_pid_1_of_a_pid_namespace_of_its_own_with_a_proc_for_it(
    mode: str, make: Rig
) -> None:
    jail, _ = make()
    first, second = jail.start(python(_WHO)), jail.start(python(_WHO))
    seen = {process.id: _json_of(process) for process in (first, second)}
    for process in (first, second):
        said, host = seen[process.id], _nspid(process.pid)
        if _isolated(mode):
            assert said["pid"] == 1 and said["pids"] == [1], said
            # three levels from the host: its own pid, the jail's, and 1 in its own namespace
            assert len(host) == 3 and host[-1] == 1 and host[0] == process.pid
            # its ids are what they were: the one mapping an unprivileged process may write
            assert (said["uid"], said["gid"]) == (os.geteuid(), os.getegid())
            assert process.namespaces is True
        else:
            # the control: the jail's one pid namespace, with the supervisor in it as PID 1
            assert said["pid"] != 1 and 1 in said["pids"] and said["pid"] in said["pids"]  # type: ignore[operator]
            assert len(host) == 2 and host[-1] == said["pid"]
            assert process.namespaces is False
        assert process.fidelity is ExecFidelity.SAME_INSTANCE
    if not _isolated(mode):
        # (the control, continued: the second process can read the first's pid)
        assert seen[first.id]["pid"] in seen[second.id]["pids"]  # type: ignore[operator]


def test_each_process_has_a_user_pid_mount_network_and_ipc_namespace_of_its_own(
    mode: str, make: Rig
) -> None:
    jail, _ = make()
    first, second = jail.start(python(_NAMESPACES)), jail.start(python(_NAMESPACES))
    seen_first = _said(first, "ipc:").split()
    seen_second = _said(second, "ipc:").split()
    assert len(seen_first) == len(seen_second) == 5
    if _isolated(mode):
        assert not set(seen_first) & set(seen_second), (seen_first, seen_second)
    else:
        assert seen_first[1:] == seen_second[1:], "the control: one instance's mount, pid, net, ipc"


# ---------------------------------------------------------------------------------------------
# It can't see, signal or find a sibling.
# ---------------------------------------------------------------------------------------------

_HOLD = r"""
import sys, time
open(sys.argv[1], 'w').write('up')
time.sleep(60)
"""

_LOOK_FOR_A_SIBLING = r"""
import json, os, signal, sys
target, marker = int(sys.argv[1]), sys.argv[2]
seen = []
for name in os.listdir('/proc'):
    if name.isdigit() and int(name) != os.getpid():
        try:
            if marker.encode() in open('/proc/%s/cmdline' % name, 'rb').read():
                seen.append(int(name))
        except OSError:
            pass
try:
    os.kill(target, 0)
    exists = True
except ProcessLookupError:
    exists = False
try:
    os.kill(target, signal.SIGTERM)
    sent = True
except (ProcessLookupError, PermissionError):
    sent = False
print(json.dumps({"seen": seen, "exists": exists, "sent": sent}), flush=True)
"""


def test_a_process_can_not_see_or_signal_a_sibling(mode: str, make: Rig) -> None:
    jail, workspace = make()
    ready = os.path.join(workspace, "a-up")
    marker = f"sibling-{random.randrange(10**9)}"
    a = jail.start(python(_HOLD, ready, marker))
    assert until(lambda: _up(ready), 15.0)
    in_the_jail = _nspid(a.pid)[1]  # the number the jail itself gives it

    b = jail.start(python(_LOOK_FOR_A_SIBLING, str(in_the_jail), marker))
    result = _json_of(b)
    if _isolated(mode):
        assert result == {"seen": [], "exists": False, "sent": False}, result
        assert a.alive() and running_with(marker) == [a.pid], "the signal reached it"
    else:
        # the control: a sibling is in the process table, there, and takes the signal
        assert result == {"seen": [in_the_jail], "exists": True, "sent": True}, result
        assert until(lambda: not a.alive(), 10.0), "the control's SIGTERM did not end it"


# ---------------------------------------------------------------------------------------------
# It can't connect to a sibling's socket, abstract socket or System V IPC.
# ---------------------------------------------------------------------------------------------

_LISTEN = r"""
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen()
open(sys.argv[2], 'w').write('up')
time.sleep(60)
"""

_REACH_A_SOCKET = r"""
import json, os, socket, sys, time
mine, theirs, chan = sys.argv[1:4]
server = socket.socket(socket.AF_UNIX)
server.bind(mine)
server.listen()
listing = sorted(os.listdir(chan))
try:
    probe = socket.socket(socket.AF_UNIX)
    probe.connect(theirs)
    reached = True
except OSError as error:
    reached = type(error).__name__
print(json.dumps({"listing": listing, "reached": reached}), flush=True)
time.sleep(60)
"""


def test_a_process_sees_only_its_own_socket_and_can_not_connect_to_a_siblings(
    mode: str, make: Rig
) -> None:
    jail, workspace = make(channel=True)
    ready = os.path.join(workspace, "a-listening")
    mine, theirs = jail.channel("ctl"), jail.channel("ctl")
    a = jail.start(python(_LISTEN, mine.bound_path, ready), channel=mine)
    assert until(lambda: _up(ready), 15.0)
    a.wait_ready(10)
    chan = os.path.dirname(mine.bound_path)

    b = jail.start(
        python(_REACH_A_SOCKET, theirs.bound_path, mine.bound_path, chan), channel=theirs
    )
    result = _json_of(b)
    own = os.path.basename(theirs.bound_path)
    if _isolated(mode):
        # one directory of its own over the channel directory: its socket, and nothing of a sibling's
        assert result == {"listing": [own], "reached": "FileNotFoundError"}, result
        assert a.endpoint != a.bound_path and a.endpoint == mine.endpoint
        assert os.path.dirname(os.path.dirname(a.endpoint or "")) == chan
    else:
        # the control: the sibling's socket is in the directory, and takes the connection
        assert result == {
            "listing": sorted([os.path.basename(mine.bound_path), own]),
            "reached": True,
        }, result
        assert a.endpoint == a.bound_path
    # Whichever it is, the host dials each of them, through its own verified dial (decision-185).
    b.wait_ready(10)
    a.connect().close()
    b.connect().close()


_BIND_ABSTRACT = r"""
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind('\0' + sys.argv[1])
server.listen()
open(sys.argv[2], 'w').write('up')
time.sleep(60)
"""

_CONNECT_ABSTRACT = r"""
import json, socket, sys
probe = socket.socket(socket.AF_UNIX)
try:
    probe.connect('\0' + sys.argv[1])
    reached = True
except OSError as error:
    reached = type(error).__name__
print(json.dumps({"reached": reached}), flush=True)
"""


def test_a_process_can_not_connect_to_a_siblings_abstract_socket(mode: str, make: Rig) -> None:
    jail, workspace = make()
    ready = os.path.join(workspace, "abstract-up")
    name = f"brig-{random.randrange(10**9)}"
    jail.start(python(_BIND_ABSTRACT, name, ready))
    assert until(lambda: _up(ready), 15.0)
    result = _json_of(jail.start(python(_CONNECT_ABSTRACT, name)))
    # a network namespace of its own holds its own abstract sockets; in one, they are shared
    assert result == {"reached": "ConnectionRefusedError" if _isolated(mode) else True}, result


_MAKE_A_QUEUE = r"""
import ctypes, sys, time
libc = ctypes.CDLL(None, use_errno=True)
queue = libc.msgget(int(sys.argv[1]), 0o1000 | 0o600)
assert queue >= 0, ctypes.get_errno()
open(sys.argv[2], 'w').write('up')
time.sleep(60)
"""

_FIND_THE_QUEUE = r"""
import ctypes, errno, json, sys
libc = ctypes.CDLL(None, use_errno=True)
queue = libc.msgget(int(sys.argv[1]), 0)
print(json.dumps({"found": queue >= 0, "errno": "" if queue >= 0 else errno.errorcode[ctypes.get_errno()]}), flush=True)
"""


def test_a_process_can_not_find_a_siblings_system_v_ipc(mode: str, make: Rig) -> None:
    jail, workspace = make()
    ready = os.path.join(workspace, "queue-up")
    key = str(random.randrange(1, 2**31 - 1))
    jail.start(python(_MAKE_A_QUEUE, key, ready))
    assert until(lambda: _up(ready), 15.0)
    result = _json_of(jail.start(python(_FIND_THE_QUEUE, key)))
    assert result == (
        {"found": False, "errno": "ENOENT"} if _isolated(mode) else {"found": True, "errno": ""}
    ), result


# ---------------------------------------------------------------------------------------------
# A scratch directory of its own.
# ---------------------------------------------------------------------------------------------

_USE_THE_SCRATCH = r"""
import json, os, sys, time
scratch, mine, ready = sys.argv[1:4]
before = sorted(os.listdir(scratch))
open(os.path.join(scratch, mine), 'w').write('mine')
print(json.dumps({"before": before, "after": sorted(os.listdir(scratch))}), flush=True)
open(ready, 'w').write('up')
time.sleep(60)
"""


def test_a_process_has_a_scratch_directory_of_its_own(mode: str, make: Rig) -> None:
    jail, workspace = make(scratch=True)
    scratch = os.path.join(os.path.realpath(jail.jail_dir), "tmp")
    ready = [os.path.join(workspace, f"scratch-{n}") for n in "ab"]
    a = jail.start(python(_USE_THE_SCRATCH, scratch, "a.txt", ready[0]))
    assert until(lambda: _up(ready[0]), 15.0)
    b = jail.start(python(_USE_THE_SCRATCH, scratch, "b.txt", ready[1]))
    assert until(lambda: _up(ready[1]), 15.0)
    first, second = _json_of(a), _json_of(b)
    assert first == {"before": [], "after": ["a.txt"]}, first
    if _isolated(mode):
        assert second == {"before": [], "after": ["b.txt"]}, second
        # each wrote into a directory of its own, which the host can see
        assert Path(scratch, a.id, "a.txt").read_text() == "mine"
        assert Path(scratch, b.id, "b.txt").read_text() == "mine"
    else:
        assert second == {"before": ["a.txt"], "after": ["a.txt", "b.txt"]}, second


# ---------------------------------------------------------------------------------------------
# Stopping a process ends its namespace: a setsid() child goes with it.
# ---------------------------------------------------------------------------------------------

_START_A_CHILD_OF_ITS_OWN = r"""
import os, sys, time
duration = open(sys.argv[1]).read()  # the child's mark: a sleep's duration no other process has
if os.fork() == 0:
    os.setsid()
    os.execv('/bin/sleep', ['sleep', duration])
print('forked', flush=True)
time.sleep(60)
"""


def test_a_setsid_child_ends_with_the_process_that_stop_ends(mode: str, make: Rig) -> None:
    jail, workspace = make()
    marker, _sleep = unique_sleep()
    mark = Path(workspace, "mark")
    mark.write_text(marker)
    parent = jail.start(python(_START_A_CHILD_OF_ITS_OWN, str(mark)))
    _said(parent, "forked")
    assert until(lambda: len(running_with(marker)) == 1, 10.0)
    (child,) = running_with(marker)
    assert os.getsid(child) != os.getsid(parent.pid), "it is not in the parent's session"

    report = parent.stop()
    assert [item.outcome for item in report.items] == [KillOutcome.ENDED], report
    if _isolated(mode):
        assert until(lambda: running_with(marker) == [], 5.0), "the child outlived the stop"
    else:
        # the control: a group-shaped stop leaves a child that left the group, and only the
        # jail's destroy ends it
        assert not until(lambda: running_with(marker) == [], 1.0)
        assert running_with(marker) == [child]
        jail.destroy()
        assert until(lambda: running_with(marker) == [], 5.0)


def test_a_process_that_ends_takes_a_setsid_child_with_it(mode: str, make: Rig) -> None:
    """The program is PID 1 of its namespace, so its own exit ends the namespace too."""
    jail, _ = make()
    marker, _sleep = unique_sleep()
    program = jail.start(sh(f"setsid /bin/sleep {marker} & exit 0"))
    assert program.wait(10) == 0
    if _isolated(mode):
        assert until(lambda: running_with(marker) == [], 5.0)
    else:
        assert until(lambda: len(running_with(marker)) == 1, 5.0)
        assert not until(lambda: running_with(marker) == [], 1.0), "the control's child left"


# ---------------------------------------------------------------------------------------------
# No capability, a loopback of its own, and the supervisor out of reach.
# ---------------------------------------------------------------------------------------------

_WHAT_IT_HOLDS = r"""
import ctypes, json, socket
libc = ctypes.CDLL(None, use_errno=True)
fields = {}
for line in open('/proc/self/status'):
    name, _, value = line.partition(':')
    if name in ('CapPrm', 'CapEff', 'CapBnd', 'CapAmb', 'NoNewPrivs'):
        fields[name] = value.strip()
mount = libc.mount(b'tmpfs', b'/', b'tmpfs', 0, None)
mount_errno = ctypes.get_errno()
unshare = libc.unshare(0x20000)  # CLONE_NEWNS
unshare_errno = ctypes.get_errno()
server = socket.socket()
server.bind(('127.0.0.1', 0))
server.listen()
client = socket.create_connection(server.getsockname(), timeout=5)
fields.update(mount=mount, mount_errno=mount_errno, unshare=unshare, unshare_errno=unshare_errno, loopback=True)
print(json.dumps(fields), flush=True)
"""


def test_a_process_holds_no_capability_cannot_mount_and_has_a_loopback(
    mode: str, make: Rig
) -> None:
    jail, _ = make()
    result = _json_of(jail.start(python(_WHAT_IT_HOLDS)))
    zero = "0" * 16
    assert [result[key] for key in ("CapPrm", "CapEff", "CapBnd", "CapAmb")] == [zero] * 4, result
    assert result["NoNewPrivs"] == "1"
    # EPERM: it made a user namespace to have its own, and can't use it for anything
    assert (result["mount"], result["mount_errno"]) == (-1, 1), result
    assert (result["unshare"], result["unshare_errno"]) == (-1, 1), result
    assert result["loopback"] is True


_LOOK_FOR_THE_SUPERVISOR = r"""
import json, os
hits = []
for name in os.listdir('/proc'):
    if name.isdigit():
        try:
            if b'.brig-' + b'supervisor.py' in open('/proc/%s/cmdline' % name, 'rb').read():
                hits.append(int(name))
        except OSError:
            pass
print(json.dumps({"supervisor": hits, "pid1_is_me": os.getpid() == 1}), flush=True)
"""


def test_the_supervisor_is_not_in_a_process_pid_namespace(mode: str, make: Rig) -> None:
    jail, _ = make()
    result = _json_of(jail.start(python(_LOOK_FOR_THE_SUPERVISOR)))
    if _isolated(mode):
        assert result == {"supervisor": [], "pid1_is_me": True}, result
    else:
        assert result == {"supervisor": [1], "pid1_is_me": False}, result  # the control


# ---------------------------------------------------------------------------------------------
# A signal to a process that is PID 1 is what it would be to any process.
# ---------------------------------------------------------------------------------------------

_HANDLES_SIGTERM = r"""
import signal, sys, time
def goodbye(*_):
    open(sys.argv[1], 'w').write('handled')
    sys.exit(0)
signal.signal(signal.SIGTERM, goodbye)
print('ready', flush=True)
time.sleep(60)
"""

_IGNORES_SIGTERM = r"""
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print('ready', flush=True)
time.sleep(60)
"""

_DEFAULT_SIGINT = r"""
import time
print('ready', flush=True)
time.sleep(60)
"""


def test_stop_ends_a_process_that_handles_no_sigterm_at_once(mode: str, make: Rig) -> None:
    jail, _ = make()
    marker, sleep = unique_sleep()
    process = jail.start(sleep)
    assert until(lambda: running_with(marker) == [process.pid], 10.0)
    began = time.monotonic()
    report = process.stop()
    elapsed = time.monotonic() - began
    assert [i.outcome for i in report.items] == [KillOutcome.ENDED]
    assert elapsed < 1.0, f"stop waited {elapsed:.2f}s on a SIGTERM nothing could deliver"
    # A SIGTERM a PID 1 does not handle is dropped by the kernel; it is sent what ends it.
    assert process.wait(5) == (-signal.SIGKILL if _isolated(mode) else -signal.SIGTERM)


def test_a_process_that_handles_sigterm_is_sent_it_and_gets_to_say_goodbye(
    mode: str, make: Rig
) -> None:
    jail, workspace = make()
    goodbye = os.path.join(workspace, "goodbye")
    process = jail.start(python(_HANDLES_SIGTERM, goodbye))
    _said(process, "ready")
    report = process.stop()
    assert [i.outcome for i in report.items] == [KillOutcome.ENDED]
    assert Path(goodbye).read_text() == "handled" and process.wait(5) == 0


def test_a_process_that_ignores_sigterm_has_its_grace_and_then_the_sigkill(
    mode: str, make: Rig
) -> None:
    jail, _ = make()
    process = jail.start(python(_IGNORES_SIGTERM))
    _said(process, "ready")
    began = time.monotonic()
    report = process.stop()
    elapsed = time.monotonic() - began
    assert [i.outcome for i in report.items] == [KillOutcome.ENDED]
    assert _STOP_GRACE_S - 0.3 < elapsed < _STOP_GRACE_S + 3.0, elapsed
    assert process.wait(5) == -signal.SIGKILL


def test_interrupt_ends_a_process_that_handles_no_sigint_as_it_would_any_other(
    mode: str, make: Rig
) -> None:
    jail, _ = make()
    marker, sleep = unique_sleep()
    plain = jail.start(sleep)
    assert until(lambda: running_with(marker) == [plain.pid], 10.0)
    assert plain.interrupt() is True
    assert plain.wait(5) == (-signal.SIGKILL if _isolated(mode) else -signal.SIGINT)
    # CPython installs a handler: the KeyboardInterrupt it raises is the program's own end
    python_program = jail.start(python(_DEFAULT_SIGINT))
    _said(python_program, "ready")
    assert python_program.interrupt() is True
    # (it then ends by the SIGINT it handled, as CPython does; a PID 1 can't be ended by a signal
    # it sends itself, and CPython's own fallback is the status a shell gives that: 130)
    assert python_program.wait(5) == (130 if _isolated(mode) else -signal.SIGINT)
    assert "KeyboardInterrupt" in stderr_of(python_program)


def test_destroy_does_not_wait_out_a_grace_for_processes_that_handle_no_sigterm(
    mode: str, make: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    jail, _ = make()
    markers = []
    for _ in range(3):
        marker, sleep = unique_sleep()
        markers.append(marker)
        jail.start(sleep)
    assert until(lambda: all(len(running_with(m)) == 1 for m in markers), 10.0)
    began = time.monotonic()
    report = jail.destroy()
    elapsed = time.monotonic() - began
    assert not [i for i in report.items if i.outcome is KillOutcome.FAILED], report
    assert elapsed < 1.5, f"destroy took {elapsed:.2f}s"
    assert all(running_with(m) == [] for m in markers)

    if _isolated(mode):
        # The control, with the host's first rung always SIGTERM: a namespace's init drops it, and
        # the same destroy waits out the grace for each of the three.
        monkeypatch.setattr(teardown, "_first_rung", lambda leader_pid: signal.SIGTERM)
        other, _ = make(jail_id="slow")
        markers = []
        for _ in range(2):
            marker, sleep = unique_sleep()
            markers.append(marker)
            other.start(sleep)
        assert until(lambda: all(len(running_with(m)) == 1 for m in markers), 10.0)
        began = time.monotonic()
        other.destroy()
        assert time.monotonic() - began > 2 * _STOP_GRACE_S - 0.5


def test_a_failed_start_leaves_no_directory_made_for_it_and_the_jail_goes_on(
    mode: str, make: Rig
) -> None:
    from brig.run import WorkloadSpawnFailed

    jail, _ = make(channel=True, scratch=True)
    chan = os.path.join(os.path.realpath(jail.jail_dir), "chan")
    scratch = os.path.join(os.path.realpath(jail.jail_dir), "tmp")
    reservation = jail.channel("ctl")
    with pytest.raises(WorkloadSpawnFailed, match="FileNotFoundError"):
        jail.start(["/no/such/program"], channel=reservation)
    # the directories made for the process that never ran are gone with it
    assert until(lambda: os.listdir(chan) == [] and os.listdir(scratch) == [], 5.0), (
        os.listdir(chan),
        os.listdir(scratch),
    )
    # and the jail starts the next one, on a socket of its own
    assert jail.processes() == ()
    again = jail.channel("ctl")
    process = jail.start(sh("exit 0"), channel=again)
    assert process.wait(10) == 0


# ---------------------------------------------------------------------------------------------
# The grade, and the fallback that says why.
# ---------------------------------------------------------------------------------------------


def test_the_process_scope_is_graded_and_says_whether_namespaces_hold_and_why(
    mode: str, make: Rig
) -> None:
    """The grades are what the control battery proves (decision-201,
    tests/e2e/test_control_battery.py holds them to it): `best_effort` with namespaces,
    `cooperative` without."""
    jail, _ = make()
    process = jail.start(sh("echo started"))
    assert process.wait(10) == 0  # the fallback starts it all the same
    assert process.control.grade is (Grade.BEST_EFFORT if _isolated(mode) else Grade.COOPERATIVE)
    if _isolated(mode):
        assert process.namespaces is True
        assert "ends the process's pid namespace" in process.control.detail
        assert "setsid()" in process.control.detail
    else:
        assert process.namespaces is False
        detail = process.control.detail
        assert "signals the process's group" in detail and "setsid()" in detail
        # it names what blocked them: uid 0 (root), or the user namespace the block refused
        assert ("uid 0" in detail) if os.geteuid() == 0 else ("unshare" in detail), detail
    # The jail's report is the compile-time claim, whatever the process has: its control is the
    # jail scope's, which the battery proves for a supervised jail with namespaces or without.
    axes = {axis.value: graded.grade for axis, graded in jail.report.axes.items()}
    assert axes["control"] is Grade.ENFORCED
    # The record carries it: a jail rehydrated in another process reads the same.
    again = Jail.from_dict(
        json.loads(json.dumps(jail.to_dict())), runtimes={RuntimeKind.HOST: HostRuntime()}
    )
    assert [p.namespaces for p in again.processes()] == [process.namespaces]


@pytest.mark.skipif(os.geteuid() == 0, reason="uid 0 is the fallback of every test here")
def test_a_blocked_nested_user_namespace_is_a_graded_fallback_not_a_failed_start(
    new_jail_dir: NewJailDir,
) -> None:
    """The planted block, by its name: bwrap told to refuse a nested user namespace. The jail
    starts, a process in it starts, and the grade says what the host would not give, in the words
    of the call that was refused. The control: the same jail unblocked (when the host gives them)."""
    from brig.run.compile_ctx import build_compile_ctx
    from brig.stack import strict_linux
    from tests.supervised_jail import spec_for

    # The control that the block blocks, asked of unshare(1) (not of brig): where the kernel gives
    # an unprivileged process namespaces in a jail, it gives none in the one with the block planted.
    if the_kernel_gives_namespaces_in_a_jail():
        assert not the_kernel_gives_namespaces_in_a_jail(blocked_jail=True)
    jail_dir = new_jail_dir()
    spec = spec_for()
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    compiled = strict_linux("/usr/bin/python3").compile(spec, ctx=ctx)
    planted = blocked(compiled)
    assert "--disable-userns" in planted.wrap(("x",)) and "--disable-userns" not in compiled.wrap(
        ("x",)
    )
    jail = Jail.create(
        planted, runtime=HostRuntime(), cwd="/", jail_id="planted", jail_dir=jail_dir
    )
    try:
        process = jail.start(["/bin/true"])
        assert process.wait(10) == 0
        assert process.namespaces is False and process.control.grade is Grade.COOPERATIVE
        assert re.search(r"unshare\(.*\): No space left on device", process.control.detail), (
            process.control.detail
        )
    finally:
        jail.destroy()
