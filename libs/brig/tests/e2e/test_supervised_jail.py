"""A bwrap jail whose PID 1 is brig's supervisor, through the public API, in a real jail
(decision-190 to decision-192, TASK-0079.06).

Every claim here is an observation, made from outside the code under test: by the host with
`/bin/ps` and `/proc`, or from inside by a process the test started, never by asking the
supervisor what it thinks of itself. Each has its control in the same test:

- several processes share the jail's one instance (one mount, network and pid namespace, seen
  from inside), and another jail's differ;
- the supervisor is PID 1 and runs `python -I` with an empty environment, from a directory the
  jail can't write, its source read-only and read from memory;
- the kernel drops `SIGKILL`, `SIGSTOP` and the rest from inside while the same signals from the
  host land, and the supervisor keeps answering;
- orphans are reaped, with a process that leaves a zombie of its own as the control that the scan
  sees one;
- what a process could do to the supervisor through `/proc`, `ptrace` and `pidfd_getfd` is refused;
- no process holds the control socket;
- end-of-file ends everything, a `setsid()` child included, with a second jail that keeps its
  host as the control that it was the end of the host, not a general cleanup;
- a `JAIL_LIFETIME` helper, which runs on the host outside the jail's namespaces, ends with the
  creator as the jail's processes do, tether or none (decision-199, TASK-0079.29);
- a rehydrated jail can be destroyed and nothing else.
"""

from __future__ import annotations

import ast
import contextlib
import gc
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from brig.core import Grade
from brig.mech import Helper, HelperLifetime
from brig.run import (
    ExecFidelity,
    HostRuntime,
    Jail,
    KillOutcome,
    RuntimeKind,
    WorkloadSpawnFailed,
    group_alive,
)
from brig.run._supervisor_program import SUPERVISOR_SOURCE
from tests.conftest import NewJailDir
from tests.supervised_jail import (
    INTERPRETER,
    create_jail,
    instance_group,
    needs_a_supervised_jail,
    process_state,
    python,
    run_to_end,
    running_with,
    sh,
    stderr_of,
    supervisor_host_pid,
    unique_sleep,
    until,
)

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _needs_a_jail() -> None:
    needs_a_supervised_jail()


_NAMESPACES = (
    "import os; print(*(os.readlink('/proc/self/ns/' + n) for n in ('mnt', 'net', 'pid')))"
)


def _ended(jail: Jail) -> None:
    """`destroy` the jail and require that everything it names ended or was already gone."""
    report = jail.destroy()
    bad = [item for item in report.items if item.outcome is KillOutcome.FAILED]
    assert not bad, bad


# ---------------------------------------------------------------------------------------------
# AC4: several processes, one instance.
# ---------------------------------------------------------------------------------------------


def test_several_processes_share_the_jails_one_instance_and_another_jail_does_not(
    new_jail_dir: NewJailDir,
) -> None:
    """In a jail whose processes have no namespaces of their own (the block planted; uid 0 is
    this too), they are in the one instance's: decision-192. With namespaces they are not, and
    `tests/e2e/test_process_namespaces.py` is where that is shown."""
    first_dir, second_dir = new_jail_dir(), new_jail_dir()
    one = create_jail(first_dir, jail_id="one", namespaces=False)
    other = create_jail(second_dir, jail_id="other", namespaces=False)
    try:
        a = one.start(python(_NAMESPACES))
        b = one.start(python(_NAMESPACES))
        elsewhere = other.start(python(_NAMESPACES))
        results = [run_to_end(p) for p in (a, b, elsewhere)]
        assert [status for status, _ in results] == [0, 0, 0]
        seen_a, seen_b, seen_elsewhere = (out.split() for _, out in results)

        # One mount, one network and one pid namespace for both processes of the jail...
        assert seen_a == seen_b and len(seen_a) == 3
        # ... and the control: another jail's namespaces are other namespaces.
        assert not set(seen_a) & set(seen_elsewhere)

        assert a.fidelity is b.fidelity is ExecFidelity.SAME_INSTANCE
        assert a.pid != b.pid and len({a.id, b.id}) == 2
        assert [p.id for p in one.processes()] == [a.id, b.id]
    finally:
        _ended(one)
        _ended(other)


def test_a_process_of_the_jail_is_a_process_of_the_host_in_a_group_of_its_own(
    new_jail_dir: NewJailDir,
) -> None:
    """`Process.pid` is the process itself in the host's pid namespace, leader of its own group:
    the identity every host-side check asks about (`alive`, the dial, a rehydrated teardown)."""
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    marker, sleep = unique_sleep()
    try:
        process = jail.start(sleep)
        assert until(lambda: running_with(marker) == [process.pid])
        assert os.getpgid(process.pid) == process.pid
        assert process.alive() and jail.alive()
        process.stop()
        assert not process.alive()
        assert jail.alive(), "stopping one process must not end the jail"
    finally:
        _ended(jail)


# ---------------------------------------------------------------------------------------------
# AC1: what the jail runs, and how.
# ---------------------------------------------------------------------------------------------

_ABOUT_PID_1 = r"""
import os
with open("/proc/1/cmdline", "rb") as f:
    print("cmdline", f.read().split(b"\0")[:-1])
with open("/proc/1/stat") as f:
    print("name", f.read().split(")")[0].split("(")[1])
with open("/proc/self/environ", "rb") as f:  # the kernel's copy: not what CPython set on itself
    print("env", f.read())
for target in ("/", "/.brig-supervisor.py"):
    try:
        open(target + ("x" if target == "/" else ""), "w").close()
        print("WROTE", target)
    except OSError as e:
        print("refused", target, e.errno)
try:
    open("/.brig-supervisor.py", "a").close()
    print("WROTE the source")
except OSError as e:
    print("refused the source", e.errno)
print("mode", oct(os.stat("/.brig-supervisor.py").st_mode & 0o777))
with open("/.brig-supervisor.py") as f:
    print("source-bytes", len(f.read().encode()))
"""


def test_the_supervisor_is_pid_1_isolated_with_an_empty_environment_and_a_read_only_source(
    new_jail_dir: NewJailDir,
) -> None:
    """Read from a process that can see PID 1: one with no namespaces of its own (the block
    planted). With them it can't, which is the namespaces' test."""
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir, namespaces=False)
    try:
        status, out = run_to_end(jail.start(python(_ABOUT_PID_1)))
        assert status == 0, out
        lines = dict(line.split(" ", 1) for line in out.splitlines())

        # PID 1 is the interpreter, run isolated, on the program the jail was given.
        cmdline = ast.literal_eval(lines["cmdline"])  # a list this test's own script printed
        assert cmdline[:3] == [b"/usr/bin/python3", b"-I", b"/.brig-supervisor.py"]
        assert lines["name"].startswith("python3")

        # The environment it was started with is the scrub's, which here allows nothing: it is
        # what every process it started inherited, and it is empty.
        assert lines["env"] == "b''"

        # A directory the jail can't write, and a source that is read-only and is the program.
        assert "refused / 30" in out or "refused / 13" in out  # EROFS / EACCES
        assert "WROTE" not in out
        assert lines["mode"] == "0o444"
        assert int(lines["source-bytes"]) == len(SUPERVISOR_SOURCE.encode())

        # Delivered from memory: no copy of the program is on the host's disk in the jail's directory.
        for root, _, names in os.walk(jail_dir):
            for name in names:
                path = Path(root, name)
                assert "brig supervisor: PID 1" not in path.read_text(errors="ignore")[:4096]
    finally:
        _ended(jail)


def test_a_spec_that_does_not_mount_the_interpreter_is_refused_and_the_control_is_not(
    new_jail_dir: NewJailDir,
) -> None:
    from brig.core import FsPolicy, ReadModel, Spec
    from brig.mech.bwrap import InterpreterNotMounted
    from brig.run.compile_ctx import build_compile_ctx
    from brig.stack import strict_linux

    jail_dir = new_jail_dir()
    bare = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/bin",)))
    ctx = build_compile_ctx(bare, jail_dir=jail_dir, platform=sys.platform)
    with pytest.raises(InterpreterNotMounted, match="/usr/bin/python3"):
        strict_linux().compile(bare, ctx=ctx)
    # The control: the same Spec, under an interpreter it does mount, compiles.
    assert strict_linux("/bin/python3").compile(bare, ctx=ctx).supervisor is not None


# ---------------------------------------------------------------------------------------------
# AC5: reaping, and signals from inside.
# ---------------------------------------------------------------------------------------------

_ZOMBIES = r"""
import os
found = []
for name in os.listdir("/proc"):
    if name.isdigit():
        try:
            with open("/proc/%s/stat" % name) as f:
                data = f.read()
        except OSError:
            continue
        if data[data.rindex(")") + 2] == "Z":
            found.append(int(name))
print(sorted(found))
"""

_A_ZOMBIE_OF_ITS_OWN = (
    "import os, time\n"
    "child = os.fork()\n"
    "if child == 0:\n"
    "    os._exit(0)\n"
    "time.sleep(0.5)\n" + _ZOMBIES
)


def test_the_supervisor_reaps_orphans_and_the_scan_would_see_a_zombie(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    try:
        # Orphans: the shell exits, its two background children outlive it and end later, and are
        # reparented to PID 1, the supervisor.
        left = jail.start(sh("(sleep 0.2 &); (sleep 0.4 &); echo left"))
        assert run_to_end(left) == (0, "left\n")
        time.sleep(1.0)
        status, out = run_to_end(jail.start(python(_ZOMBIES)))
        assert (status, out.strip()) == (0, "[]"), out

        # The control: a process that does not wait for its own child leaves a zombie, and the
        # same scan finds it, so an empty answer above means nothing was left, not that the
        # scan cannot see.
        status, out = run_to_end(jail.start(python(_A_ZOMBIE_OF_ITS_OWN)))
        assert status == 0, stderr_of(jail.processes()[-1])
        assert out.strip() not in ("[]", ""), out
    finally:
        _ended(jail)


_SIGNAL_THE_INIT = (
    "kill -9 1; echo k9=$?; kill -STOP 1; echo kstop=$?; kill -TERM 1; echo kterm=$?; "
    "kill -INT 1; echo kint=$?; kill -USR1 1; echo kusr1=$?; sleep 0.3; echo done"
)


def test_signals_from_inside_the_jail_do_not_reach_the_supervisor_but_the_hosts_do(
    new_jail_dir: NewJailDir,
) -> None:
    """From a process that can see PID 1 (no namespaces of its own: the block planted). With
    them `kill 1` reaches the process itself, which is its own PID 1."""
    jail_dir, other_dir = new_jail_dir(), new_jail_dir()
    jail = create_jail(jail_dir, jail_id="signalled", namespaces=False)
    control = create_jail(other_dir, jail_id="control", namespaces=False)
    try:
        group = instance_group(jail)
        supervisor = supervisor_host_pid(group)
        assert process_state(supervisor) in ("S", "R")

        status, out = run_to_end(jail.start(sh(_SIGNAL_THE_INIT)))
        # The kernel accepts the calls (the sender is allowed to signal), and drops them.
        assert status == 0 and out.split()[-1] == "done" and "k9=0" in out and "kstop=0" in out, out
        assert process_state(supervisor) in ("S", "R"), "a signal from inside reached PID 1"
        # And it still answers.
        assert run_to_end(jail.start(sh("echo still here"))) == (0, "still here\n")

        # The control: the same signals from the host land. SIGSTOP stops it and SIGCONT resumes
        # it (so the state read above could have said stopped), and SIGKILL ends the jail's PID 1
        # and, with it, the jail.
        marker, sleep = unique_sleep()
        victim = control.start(sleep)
        assert until(lambda: running_with(marker) == [victim.pid])
        target = supervisor_host_pid(instance_group(control))
        os.kill(target, signal.SIGSTOP)
        assert until(lambda: process_state(target) == "T")
        os.kill(target, signal.SIGCONT)
        assert until(lambda: process_state(target) in ("S", "R"))
        os.kill(target, signal.SIGKILL)
        assert until(lambda: process_state(target) == "gone")
        assert until(lambda: running_with(marker) == []), "the namespace outlived its init"
    finally:
        _ended(jail)
        _ended(control)


# ---------------------------------------------------------------------------------------------
# What a process of the jail can do to the supervisor, and can't.
# ---------------------------------------------------------------------------------------------

_PROBE_THE_SUPERVISOR = r"""
import ctypes, os
for path in ("/proc/1/environ", "/proc/1/mem", "/proc/1/maps", "/proc/1/fd/0", "/proc/1/auxv"):
    try:
        with open(path, "rb") as f:
            f.read(16)
        print(path, "READABLE")
    except OSError as e:
        print(path, "refused", e.errno)
libc = ctypes.CDLL(None, use_errno=True)
pidfd = libc.syscall(434, 1, 0)  # pidfd_open(1)
print("pidfd_open", "ok" if pidfd >= 0 else "refused")
stolen = [t for t in range(0, 32) if libc.syscall(438, pidfd, t, 0) >= 0]  # pidfd_getfd
print("pidfd_getfd stole", stolen)
print("ptrace attach", libc.ptrace(16, 1, 0, 0), ctypes.get_errno())
"""

_HOLDINGS = r"""
import os, stat
held = []
for fd in range(0, 1024):
    try:
        mode = os.fstat(fd).st_mode
    except OSError:
        continue
    held.append((fd, "socket" if stat.S_ISSOCK(mode) else "other"))
print(held)
"""


def test_a_process_of_the_jail_can_not_read_attach_to_or_take_from_the_supervisor(
    new_jail_dir: NewJailDir,
) -> None:
    """From a process that can see PID 1 (no namespaces of its own: the block planted); with
    them the supervisor is not in its pid namespace at all."""
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir, namespaces=False)
    try:
        status, out = run_to_end(jail.start(python(_PROBE_THE_SUPERVISOR)))
        assert status == 0, stderr_of(jail.processes()[0])
        assert "READABLE" not in out, out
        assert "pidfd_getfd stole []" in out, out
        assert "ptrace attach -1 1" in out, out  # -1, EPERM
    finally:
        _ended(jail)


def test_no_process_the_supervisor_starts_holds_the_control_socket(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    try:
        status, out = run_to_end(jail.start(python(_HOLDINGS)))
        assert status == 0
        held = ast.literal_eval(out)  # a list of tuples this test's own script printed
        assert {fd for fd, _ in held} == {0, 1, 2}, held
        assert all(kind != "socket" for _, kind in held), held
        # A shell the same: nothing above descriptor 2 but what it opens itself for the listing.
        status, out = run_to_end(
            jail.start(sh("ls /proc/self/fd | grep -c -v -e '^[012]$' || true"))
        )
        assert status == 0 and out.strip() in ("0", "1"), out
    finally:
        _ended(jail)


# ---------------------------------------------------------------------------------------------
# AC2: stdio by SCM_RIGHTS.
# ---------------------------------------------------------------------------------------------


def test_stdio_the_host_opened_reaches_the_process_though_the_jail_cannot_see_the_path(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    try:
        code = (
            "import os, sys; print('to stdout'); print('to stderr', file=sys.stderr); "
            "print('sees-the-log-path', os.path.exists(sys.argv[1])); "
            "print('stdin', repr(sys.stdin.read()))"
        )
        probe = jail.start(python("pass"))  # to learn where the logs go
        run_to_end(probe)
        path = probe.stdout_path
        process = jail.start(python(code, path))
        status, out = run_to_end(process)
        assert status == 0, stderr_of(process)
        assert out.splitlines() == ["to stdout", "sees-the-log-path False", "stdin ''"]
        assert stderr_of(process) == "to stderr\n"
        assert os.path.exists(path) and path.startswith(os.path.realpath(jail_dir))
    finally:
        _ended(jail)


# ---------------------------------------------------------------------------------------------
# AC3: end-of-file ends everything.
# ---------------------------------------------------------------------------------------------

_HOST_THAT_DIES = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
from tests.supervised_jail import create_jail, sh
jail_dir, setsid_marker, plain_marker, held_marker = sys.argv[2:5] + [sys.argv[5]]
jail = create_jail(jail_dir)  # untethered: only the socket's end-of-file can end it
jail.start(sh(
    "setsid /bin/sleep %s & /bin/sleep %s & exec /bin/sleep %s" % (setsid_marker, plain_marker, held_marker)
))
print(json.dumps(jail.to_dict()["supervisor"]), flush=True)
time.sleep(600)
"""


def _stand_in_host(jail_dir: str, markers: tuple[str, str, str]) -> subprocess.Popen[str]:
    tests_parent = str(Path(__file__).resolve().parents[2])
    return subprocess.Popen(
        [sys.executable, "-I", "-c", _HOST_THAT_DIES, tests_parent, jail_dir, *markers],
        stdout=subprocess.PIPE,
        text=True,
    )


def _marker() -> str:
    return unique_sleep()[0]


def test_end_of_file_on_the_control_socket_ends_everything_a_setsid_child_included(
    new_jail_dir: NewJailDir,
) -> None:
    dead_dir, kept_dir = new_jail_dir(), new_jail_dir()
    dead_markers = (_marker(), _marker(), _marker())
    kept_markers = (_marker(), _marker(), _marker())
    dying = _stand_in_host(dead_dir, dead_markers)
    surviving = _stand_in_host(kept_dir, kept_markers)
    try:
        for host in (dying, surviving):
            assert host.stdout is not None and json.loads(host.stdout.readline())["pid"] > 1
        both = lambda markers: all(running_with(m) for m in markers)  # noqa: E731
        assert until(lambda: both(dead_markers) and both(kept_markers)), "the jails did not start"

        dying.kill()  # SIGKILL: the kernel closes the host's end of the socket, nothing runs
        dying.wait(10)

        assert until(lambda: not any(running_with(m) for m in dead_markers), 15.0), {
            m: running_with(m) for m in dead_markers
        }
        # The control: the other jail's host is alive, and everything in it, the setsid()
        # child included, still runs. It was the end of the host, not a general cleanup.
        assert both(kept_markers)
        surviving.kill()
        surviving.wait(10)
        assert until(lambda: not any(running_with(m) for m in kept_markers), 15.0)
    finally:
        for host in (dying, surviving):
            host.kill()
            host.wait(10)


# ---------------------------------------------------------------------------------------------
# decision-199: a helper is tethered to the creator as the jail's processes are.
# ---------------------------------------------------------------------------------------------

_HOST_WITH_A_HELPER = r"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
from brig.mech import Helper, HelperLifetime
from tests.supervised_jail import create_jail
jail_dir, helper_marker, process_marker, tethered = sys.argv[2:6]
helper = Helper(
    name="beacon", argv=("/bin/sleep", helper_marker), lifetime=HelperLifetime.JAIL_LIFETIME
)
watched, tether = os.pipe()
jail = create_jail(
    jail_dir, helpers=(helper,), **({"tether": watched} if tethered == "1" else {})
)
os.close(watched)
jail.start(["/bin/sleep", process_marker])
print(json.dumps(jail.to_dict()["helper_pids"]), flush=True)
time.sleep(600)
"""


def _kill_markers(*markers: str) -> None:
    for marker in markers:
        for pid in running_with(marker):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


def _helper(marker: str) -> Helper:
    return Helper(name="beacon", argv=("/bin/sleep", marker), lifetime=HelperLifetime.JAIL_LIFETIME)


def _stand_in_host_with_a_helper(
    jail_dir: str, helper_marker: str, process_marker: str, *, tethered: bool
) -> subprocess.Popen[str]:
    tests_parent = str(Path(__file__).resolve().parents[2])
    return subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            _HOST_WITH_A_HELPER,
            tests_parent,
            jail_dir,
            helper_marker,
            process_marker,
            "1" if tethered else "0",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )


@pytest.mark.parametrize("tethered", [False, True], ids=["untethered", "tethered"])
def test_a_helper_ends_with_a_creator_killed_as_the_jails_processes_do(
    tethered: bool, new_jail_dir: NewJailDir
) -> None:
    """The helper runs on the host, outside the jail's namespaces, so the supervisor's end-of-file
    does not reach it: it is tethered to the creator by a descriptor of its own. The control is
    the second creator, alive, whose helper and process both run until it is killed too."""
    dead_dir, kept_dir = new_jail_dir(), new_jail_dir()
    dead, kept = (_marker(), _marker()), (_marker(), _marker())
    dying = _stand_in_host_with_a_helper(dead_dir, *dead, tethered=tethered)
    surviving = _stand_in_host_with_a_helper(kept_dir, *kept, tethered=tethered)
    try:
        for host in (dying, surviving):
            assert host.stdout is not None and len(json.loads(host.stdout.readline())) == 1
        assert until(lambda: all(running_with(m) for m in (*dead, *kept))), (
            "the jails did not start"
        )

        dying.kill()  # SIGKILL: the kernel closes the creator's descriptors, nothing runs
        dying.wait(10)

        assert until(lambda: not running_with(dead[1]), 15.0), "the jail's process outlived it"
        assert until(lambda: not running_with(dead[0]), 15.0), {
            "the helper outlived its creator": running_with(dead[0])
        }
        assert all(running_with(m) for m in kept)  # it was the end of the creator, not a sweep
        surviving.kill()
        surviving.wait(10)
        assert until(lambda: not any(running_with(m) for m in kept), 15.0)
    finally:
        for host in (dying, surviving):
            host.kill()
            host.wait(10)
        _kill_markers(*dead, *kept)  # a helper that outlived its creator is not left behind


def test_a_helper_ends_with_a_supervised_jail_nobody_holds_any_more(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    helper_marker, process_marker = _marker(), _marker()

    def make() -> None:
        jail = create_jail(jail_dir, helpers=(_helper(helper_marker),))
        jail.start(["/bin/sleep", process_marker])
        assert until(lambda: bool(running_with(helper_marker) and running_with(process_marker)))

    try:
        make()
        gc.collect()
        assert until(lambda: not running_with(process_marker), 15.0), "the jail outlived its object"
        assert until(lambda: not running_with(helper_marker), 15.0), "its helper outlived it"
    finally:
        _kill_markers(helper_marker, process_marker)


def test_a_tether_still_ends_a_supervised_jail_whose_host_lives(new_jail_dir: NewJailDir) -> None:
    """decision-167's tether runs outside everything and is independent of the socket: the write
    end of the tether closed ends the jail while this process still holds its end of the socket."""
    jail_dir = new_jail_dir()
    watched, tether = os.pipe()
    jail = create_jail(jail_dir, tether=watched)
    os.close(watched)
    marker, sleep = unique_sleep()
    try:
        jail.start(sleep)
        assert until(lambda: bool(running_with(marker)))
        control = instance_group(jail)
        assert jail.alive()
        os.close(tether)
        assert until(lambda: not running_with(marker), 15.0), "the tether did not end the jail"
        assert until(lambda: not jail.alive())
        assert control > 1
    finally:
        _ended(jail)


def test_a_jail_nobody_holds_any_more_ends(new_jail_dir: NewJailDir) -> None:
    """The rule, stated: a supervised jail lives as long as the object that holds its end of the
    socket, tether or none (decision-191)."""
    jail_dir = new_jail_dir()
    marker, sleep = unique_sleep()

    def make() -> int:
        jail = create_jail(jail_dir)
        jail.start(sleep)
        assert until(lambda: bool(running_with(marker)))
        return instance_group(jail)

    group = make()
    gc.collect()
    assert until(lambda: not running_with(marker), 15.0), "the jail outlived its object"
    assert group > 1


# ---------------------------------------------------------------------------------------------
# Starts, signals, waits and stops: the requests, end to end.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("namespaces", [True, False], ids=["as-the-host-gives", "no-namespaces"])
def test_start_wait_interrupt_and_stop_are_requests_the_supervisor_answers(
    namespaces: bool,
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir, namespaces=namespaces)
    try:
        assert run_to_end(jail.start(sh("exit 3"))) == (3, "")
        killed = jail.start(sh("kill -KILL $$"))
        # A process that is PID 1 of its own pid namespace can't SIGKILL itself: the kernel drops
        # it, as it drops any signal an init gets from inside (decision-195).
        assert killed.wait(10) == (0 if killed.namespaces else -signal.SIGKILL)

        # interrupt delivers SIGINT to the process's group; a process that handles it says so.
        catches = jail.start(
            python(
                "import signal, sys, time\n"
                "signal.signal(signal.SIGINT, lambda *a: (print('interrupted', flush=True), sys.exit(0)))\n"
                "print('ready', flush=True)\n"
                "time.sleep(60)"
            )
        )
        assert until(lambda: "ready" in Path(catches.stdout_path).read_text())
        assert catches.interrupt() is True
        assert run_to_end(catches)[1] == "ready\ninterrupted\n"
        assert catches.interrupt() is False  # gone: not delivered

        # a wait with a deadline answers None-as-timeout while it runs; stop ends it, verified
        marker, sleep = unique_sleep()
        running = jail.start(sleep)
        with pytest.raises(TimeoutError):
            running.wait(0.3)
        report = running.stop()
        assert [(i.kind, i.outcome) for i in report.items] == [("exec_sibling", KillOutcome.ENDED)]
        assert not running_with(marker)
        # killed by the SIGTERM a process would die of; a PID 1 that handles none is sent the
        # SIGKILL that ends it, and its status says that (decision-195).
        assert running.wait(5) == (-signal.SIGKILL if running.namespaces else -signal.SIGTERM)
    finally:
        _ended(jail)


def test_a_failed_exec_is_a_failed_start_with_its_reason_and_the_jail_goes_on(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    try:
        with pytest.raises(WorkloadSpawnFailed, match="FileNotFoundError"):
            jail.start(["/no/such/program"])
        with pytest.raises(WorkloadSpawnFailed, match="FileNotFoundError"):
            jail.start(["/bin/true"], cwd="/no/such/directory")
        procs = Path(jail_dir, "procs")
        assert not procs.exists() or list(procs.iterdir()) == [], "a failed start left records"
        assert jail.processes() == ()
        assert run_to_end(jail.start(sh("echo and on"))) == (0, "and on\n")
    finally:
        _ended(jail)


def test_a_status_learned_is_kept_and_answered_after_the_jail_is_gone(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    try:
        process = jail.start(sh("exit 7"))
        assert process.wait(10) == 7
        assert process.exit_events() == ()
        _ended(jail)
        assert process.wait(1) == 7
    finally:
        _ended(jail)


# ---------------------------------------------------------------------------------------------
# Destroy, and a jail rehydrated in another process.
# ---------------------------------------------------------------------------------------------


def test_destroy_reports_the_processes_then_the_instance_and_leaves_nothing(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    marker, sleep = unique_sleep()
    escaping = unique_sleep()[0]
    try:
        first = jail.start(sleep)
        second = jail.start(sh(f"setsid /bin/sleep {escaping} & wait"))
        assert until(lambda: bool(running_with(marker)) and len(running_with(escaping)) == 2)
        began = time.monotonic()
        report = jail.destroy()
        # The prompt end: the supervisor's PID 1 drops the ladder's SIGTERM, so a destroy that
        # did not close the socket first would wait out the ladder's whole grace period (2 s).
        assert time.monotonic() - began < 1.5, "destroy waited out the ladder's grace"
        assert [item.kind for item in report.items] == [
            "workload_group",
            "exec_sibling",
            "supervisor",
        ]
        assert all(item.outcome is not KillOutcome.FAILED for item in report.items), report
        # The instance was running and is gone: ended by end-of-file and verified.
        assert report.items[-1].outcome is KillOutcome.ENDED
        assert not running_with(marker) and not running_with(escaping), (
            "something survived the jail"
        )
        assert not jail.alive() and not first.alive() and not second.alive()
        again = jail.destroy()
        assert all(item.outcome is KillOutcome.ALREADY_GONE for item in again.items), again
    finally:
        _ended(jail)


# A program that answers SIGTERM by saying it came and carrying on, which a program that
# ignores it is, plus a second one in a session of its own, which a ladder per group never
# names, and both stamp a file every 10 ms so that a test sees them run.
_STUBBORN = """
import os, signal, subprocess, sys, time
ws, name, role = sys.argv[1:4]
def on_term(*_):
    open(os.path.join(ws, "term-" + name), "w").write("SIGTERM")
signal.signal(signal.SIGTERM, on_term)
if role == "parent":
    subprocess.Popen(
        [sys.executable, "-I", __file__, ws, name + "-child", "child"], start_new_session=True
    )
while True:
    open(os.path.join(ws, "tick-" + name), "w").write(str(time.time()))
    time.sleep(0.01)
"""


@pytest.mark.parametrize("grace", [0, 0.6], ids=["at-once", "with-grace"])
def test_destroy_at_once_sends_no_sigterm_and_ends_the_instance_first_a_setsid_child_included(
    grace: float,
    new_jail_dir: NewJailDir,
) -> None:
    """decision-193. Two programs ignore SIGTERM (each starts another in a session of its own),
    and `destroy(grace=0)` ends the jail with the kernel's end of its namespace: none of them is
    told SIGTERM (no handler ran), and nothing runs a moment after, in well under what the
    ladder's grace gives a program that ignores it. The control, the same jail destroyed with a
    grace period of 0.6 s: every group is sent SIGTERM first (the handlers ran) and each of the
    two waits out the grace period, so it takes longer than that."""
    jail_dir = new_jail_dir()
    workspace = new_jail_dir()
    Path(workspace, "stubborn.py").write_text(_STUBBORN)
    jail = create_jail(jail_dir, workspace=workspace)
    names = (f"a{_marker()}", f"b{_marker()}")
    try:
        for name in names:
            jail.start([INTERPRETER, "-I", f"{workspace}/stubborn.py", workspace, name, "parent"])
        ticks = [
            Path(workspace, f"tick-{name}{suffix}") for name in names for suffix in ("", "-child")
        ]
        assert until(lambda: all(tick.exists() for tick in ticks), 10.0), "CONTROL: they never ran"
        first = [tick.read_text() for tick in ticks]
        time.sleep(0.2)
        assert [tick.read_text() for tick in ticks] != first, "CONTROL: they are not running"

        began = time.monotonic()
        report = jail.destroy(grace=grace)
        elapsed = time.monotonic() - began

        assert [item.kind for item in report.items] == [
            "workload_group",
            "exec_sibling",
            "supervisor",
        ]
        assert all(item.outcome is KillOutcome.ENDED for item in report.items), report
        assert until(lambda: not any(running_with(name) for name in names), 5.0), (
            "something survived"
        )
        last = [tick.read_text() for tick in ticks]
        time.sleep(0.3)
        assert [tick.read_text() for tick in ticks] == last, (
            "a program of the jail is still running"
        )
        told = sorted(path.name for path in Path(workspace).glob("term-*"))
        if grace == 0:
            assert told == [], f"SIGTERM was sent first: {told}"
            assert elapsed < 1.0, f"destroy(grace=0) took {elapsed:.2f} s"
        else:
            assert told == sorted(f"term-{name}" for name in names), told  # the setsid children not
            assert elapsed > 2 * grace, f"two programs ignoring SIGTERM took {elapsed:.2f} s"
    finally:
        _ended(jail)


def test_the_instance_group_names_the_jail_whose_program_ended_and_the_jail_did_not(
    new_jail_dir: NewJailDir,
) -> None:
    """decision-193. A program starts another in a session of its own and ends: its own group is
    gone and the jail, which the other holds, is not. `Jail.instance_group` is the group that holds
    PID 1, found in the process table the way the other tests find it, and it lives as long as the
    jail does, which is the number a record of which jail holds a placeholder has to name. The
    other program outlives the first in a jail whose processes have no namespaces of their own (the
    block planted); in one that has them it ends with the first's pid namespace, which
    `tests/e2e/test_process_namespaces.py` shows."""
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir, namespaces=False)
    marker, _ = unique_sleep()
    try:
        program = jail.start(sh(f"setsid /bin/sleep {marker} & exit 0"))
        assert until(lambda: bool(running_with(marker)))
        assert program.wait(10) == 0
        group = jail.instance_group
        assert group is not None and group == instance_group(jail)
        assert supervisor_host_pid(group) > 1  # a process of that group is PID 1 of its namespace
        assert until(lambda: not group_alive(program.pid)), "CONTROL: the program's own group ended"
        assert group_alive(group) and running_with(marker) and jail.alive()
        _ended(jail)
        assert not group_alive(group) and not jail.alive()
        assert until(lambda: not running_with(marker), 5.0)
    finally:
        _ended(jail)


def test_a_rehydrated_supervised_jail_can_be_destroyed_and_nothing_else(
    new_jail_dir: NewJailDir,
) -> None:
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    marker, sleep = unique_sleep()
    try:
        jail.start(sleep)
        assert until(lambda: bool(running_with(marker)))
        d = json.loads(json.dumps(jail.to_dict()))
        assert d["version"] == 11 and d["supervisor"]["pid"] == instance_group(jail)

        again = Jail.from_dict(d, runtimes={RuntimeKind.HOST: HostRuntime()})
        assert again.alive()
        assert not hasattr(again, "start") and not hasattr(again, "probe")
        (process,) = again.processes()
        assert not any(hasattr(process, name) for name in ("interrupt", "stop", "wait"))
        assert process.alive() and process.fidelity is ExecFidelity.SAME_INSTANCE

        report = again.destroy()
        assert all(item.outcome is not KillOutcome.FAILED for item in report.items), report
        assert [item.kind for item in report.items][-1] == "supervisor"
        assert not running_with(marker) and not again.alive()
        assert not jail.alive()
    finally:
        _ended(jail)


def test_the_report_names_what_the_supervisor_does_not_grade(new_jail_dir: NewJailDir) -> None:
    """The three mechanism axes are enforced; of the two axes the runtime grades, `control` is
    `enforced` at the jail scope, which the control battery proves (decision-201,
    tests/e2e/test_control_battery.py), and `channel_exclusivity` stays `unenforced`, which
    nothing yet proves."""
    jail_dir = new_jail_dir()
    jail = create_jail(jail_dir)
    try:
        axes = {axis.value: graded.grade for axis, graded in jail.report.axes.items()}
        assert axes["fs_read"] is axes["fs_write"] is axes["network"] is Grade.ENFORCED
        assert axes["control"] is Grade.ENFORCED
        assert axes["channel_exclusivity"] is Grade.UNENFORCED
    finally:
        _ended(jail)
