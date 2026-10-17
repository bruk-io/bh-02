"""The supervisor's program, as text, and the argv that runs it (SPEC.md section 8, decision-191).

A bwrap jail's PID 1 is brig's supervisor (decision-190): one program, started by
`HostRuntime.create` as the jail's only process, which then starts, signals, waits for and stops
every other process of the jail on request. `SUPERVISOR_SOURCE` is that program. It is kept as a
string, as `brig.run._exit_status.WRAPPER_SOURCE` is, for two reasons that are this module's whole
design:

- **It can't import brig.** It runs inside the jail, under the jail's own Python (any 3.9 or later,
  `python -I`), where brig is not mounted; it is delivered as one file by `bwrap --ro-bind-data`
  from the host's memory. So it is the standard library and nothing else, written in the syntax of
  the oldest Python it supports, which the workspace's formatter, set to 3.15, would rewrite in a
  `.py` file (parentheses off a multi-type `except`, for one). As text it is data, and the unit
  tier compiles it, and the integration tier runs it, under the jail's interpreter.
- **Importing this module starts nothing.** The program is text until a runtime hands it to an
  interpreter.

What it does and why each choice is a defence is in the program's own docstring and in SPEC.md
section 8: it is undumpable, holds no handler a process of the jail could use, keeps its control
socket from everything it starts, imports before it starts anything, and fails closed.
"""

from typing import Final

from brig.core.runtime import SUPERVISOR_SOURCE_PATH, SupervisorPlan

#: The wire's version: the program says it in its hello, and the host refuses another.
PROTOCOL: Final = 2

SUPERVISOR_SOURCE: Final = r'''"""brig supervisor: PID 1 of a bubblewrap jail (SPEC.md section 8, decision-191).

One program for every bwrap jail. It holds the jail's processes: it starts, signals, waits for and
stops them on request, reaps every orphan the jail makes, and ends the whole jail when the host
that started it is gone. It runs as `python -I <this file> <control fd>` under the jail's own
confinement, from a file bwrap bound read-only out of the host's memory (`--ro-bind-data`).

Everything it reads from its control socket is the host's. Everything a process of the jail can
reach is the model's: its signals, its /proc, its files. So the program imports everything before
it can start anything, holds no handler a process could use but one that only wakes it, makes
itself undumpable, never lets a process it starts hold the control socket, and fails closed: any
error it cannot handle ends it, and with it, by the kernel's own rule for a pid namespace's init,
everything in the jail.

Where the host lets an unprivileged process have namespaces of its own (it finds out before it says
it is ready, by doing it once) each process it starts is PID 1 of a pid namespace of its own, in
mount, network, IPC and user namespaces of its own too (decision-195): siblings can't see, signal or
reach one another, and ending it ends everything it started, a setsid() child included. Where it
doesn't, a process is started as it always was and the hello says why not.

The wire (decision-191): the control socket is a SOCK_SEQPACKET socketpair, one JSON object per
message, file descriptors by SCM_RIGHTS. A request is {"id": n, "op": ..., ...}; its reply is
{"id": n, "ok": true|false, ...}. The supervisor says {"hello": 1, ...} once before any request.
"""

import array  # socket.send_fds and recv_fds import it themselves, late, on newer Pythons
import ctypes
import fcntl
import json
import os
import select
import signal
import socket
import struct
import sys
import time
import traceback
import warnings  # os.get_exec_path imports it, late, on every Python; the rehearsal covers the rest

PROTOCOL = 2

#: One message from the host; larger is a protocol error, never read half.
MAX_MESSAGE = 1 << 20

#: Descriptors the host may pass with one message: a start's three stdio files.
MAX_FDS = 4

PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4
PR_CAPBSET_DROP = 24
PR_CAP_AMBIENT = 47
PR_CAP_AMBIENT_CLEAR_ALL = 4
CAPABILITY_V3 = 0x20080522

#: What `unshare(2)` is asked for (decision-195): user, mount, pid, network and IPC namespaces.
CLONE_NEWNS = 0x00020000
CLONE_NEWIPC = 0x08000000
CLONE_NEWUSER = 0x10000000
CLONE_NEWPID = 0x20000000
CLONE_NEWNET = 0x40000000
NAMESPACES = CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWIPC

MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18

SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 1

#: How long the start of a process in namespaces may take to say which process it made: a few
#: system calls, so a miss is a wedged host, and ends the start.
NAMESPACE_START_TIMEOUT_S = 10.0

#: The signals whose default action does not end a process (it is ignored, or stops or continues
#: it): the ones the kernel delivers to a pid namespace's init as it does to any process.
UNTERMINATING = frozenset(
    int(number)
    for number in (
        signal.SIGCHLD,
        signal.SIGCONT,
        signal.SIGSTOP,
        signal.SIGTSTP,
        signal.SIGTTIN,
        signal.SIGTTOU,
        signal.SIGURG,
        signal.SIGWINCH,
    )
)

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p]

#: How often a stop or a wait is looked at when nothing else wakes the loop.
TICK_S = 0.05


def log(text):
    try:
        sys.stderr.write("brig supervisor: " + text + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def die(text, code=70):
    log(text)
    os._exit(code)


def check_platform():
    if sys.version_info < (3, 9) or not hasattr(os, "pidfd_open"):
        die(
            "needs Python 3.9 and Linux 5.3 (os.pidfd_open): %s is %s"
            % (sys.executable, sys.version.split()[0])
        )
    if os.getpid() != 1:
        die("is not PID 1 of its pid namespace (pid %d): it reaps orphans and ends the jail as init" % os.getpid())


def inherited_environment():
    """The environment this process was started with, from the kernel's copy, so a variable the
    interpreter set for itself (LC_CTYPE under locale coercion) is not handed to every process of
    the jail. Falls back to os.environ where /proc cannot be read."""
    try:
        with open("/proc/self/environ", "rb") as handle:
            raw = handle.read()
    except OSError:
        return dict(os.environ)
    env = {}
    for entry in raw.split(b"\0"):
        if b"=" in entry:
            name, _, value = entry.partition(b"=")
            env[os.fsdecode(name)] = os.fsdecode(value)
    return env


def make_undumpable():
    """A process of the jail runs as this one's uid, with no capability. Dumpable would let it
    read this process's environment and descriptors in /proc, attach to it with ptrace, and take
    its control socket with pidfd_getfd. Undumpable closes all three for a caller without
    CAP_SYS_PTRACE."""
    if LIBC.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        die("could not make itself undumpable (prctl: errno %d)" % ctypes.get_errno())
    if LIBC.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0) != 0:
        die("is still dumpable after prctl")


# --- namespaces (decision-195) -------------------------------------------------------------


def libc_call(result, what):
    """`what` failed with the errno `ctypes` kept, when `result` is not the 0 of success."""
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, "%s: %s" % (what, os.strerror(code)))


def mount(source, target, fstype, flags):
    libc_call(
        LIBC.mount(
            None if source is None else os.fsencode(source),
            os.fsencode(target),
            None if fstype is None else os.fsencode(fstype),
            flags,
            None,
        ),
        "mount %s on %s" % (fstype or source or "-", target),
    )


def write_file(path, text):
    descriptor = os.open(path, os.O_WRONLY)
    try:
        os.write(descriptor, text.encode())
    finally:
        os.close(descriptor)


def new_namespaces():
    """In a process forked for it: leave for new user, mount, pid, network and IPC namespaces.
    The next fork is PID 1 of the new pid namespace, not this process. The user namespace maps
    this process's ids to themselves, the one mapping an unprivileged process may write, so the
    files it owns stay its own; it can't map the root user, which is the case the host refuses
    before it gets here. Dumpable again for that, as a process that has just made a user
    namespace is not: the files in /proc/self are root's until it is, and exec resets it."""
    uid, gid = os.geteuid(), os.getegid()
    libc_call(LIBC.unshare(NAMESPACES), "unshare(user, mount, pid, network and IPC namespaces)")
    libc_call(LIBC.prctl(PR_SET_DUMPABLE, 1, 0, 0, 0), "prctl(PR_SET_DUMPABLE)")
    write_file("/proc/self/setgroups", "deny")
    write_file("/proc/self/uid_map", "%d %d 1" % (uid, uid))
    write_file("/proc/self/gid_map", "%d %d 1" % (gid, gid))


def bring_up_loopback():
    """A new network namespace holds a loopback device that is down; bwrap brings the jail's up."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        flags = struct.unpack("16sH22x", fcntl.ioctl(probe, SIOCGIFFLAGS, struct.pack("16sH22x", b"lo", 0)))[1]
        fcntl.ioctl(probe, SIOCSIFFLAGS, struct.pack("16sH22x", b"lo", flags | IFF_UP))
    finally:
        probe.close()


def isolate(binds):
    """In PID 1 of the new namespaces: nothing of the mounts propagates out of this mount
    namespace or into it, `/proc` is a fresh one for this pid namespace, each `(source, target)` of
    `binds` is a bind mount (a directory of this process's own over the shared one), and the
    loopback device is up."""
    mount(None, "/", None, MS_REC | MS_PRIVATE)
    mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC)
    for source, target in binds:
        mount(source, target, None, MS_BIND)
    bring_up_loopback()


def drop_capabilities():
    """A process that made a user namespace holds every capability in it: the bounding set, the
    permitted, effective and inheritable sets and the ambient ones are emptied, so nothing it
    runs can mount, remount or write a sysctl, in the namespaces it owns or any it makes
    (decision-177's promise for a process of the jail, kept in the user namespace it now
    owns)."""
    for capability in range(64):
        if LIBC.prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) != 0:
            if ctypes.get_errno() == 22:  # EINVAL: past the last capability
                break
            libc_call(-1, "prctl(PR_CAPBSET_DROP, %d)" % capability)
    header = ctypes.create_string_buffer(struct.pack("Ii", CAPABILITY_V3, 0))
    data = ctypes.create_string_buffer(24)
    libc_call(LIBC.capset(header, data), "capset")
    libc_call(LIBC.prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0), "prctl(PR_CAP_AMBIENT)")


def signal_for_init(pid, number):
    """The signal to send `pid`, PID 1 of a pid namespace its sender is outside, to do what
    `number` does to an ordinary process. The kernel drops every signal such a sender gives an
    init that has no handler for it (SIGKILL and SIGSTOP excepted), so a SIGTERM that would end any
    other process is dropped: one whose default action ends a process, that the process neither
    handles nor ignores, is SIGKILL, which ends it and with it the namespace. A handled or
    ignored signal is sent as it is, the handler running or the signal ignored as for any
    process; a signal that does not end a process by default is too."""
    if number == signal.SIGKILL or number in UNTERMINATING:
        return number
    try:
        with open("/proc/%d/status" % pid, "rb") as status:
            lines = status.read().splitlines()
    except OSError:
        return number
    held = 0
    for line in lines:
        if line.startswith((b"SigCgt:", b"SigIgn:")):
            held |= int(line.split()[1], 16)
    if held & (1 << (number - 1)):
        return number
    return signal.SIGKILL


class Supervisor:
    def __init__(self, control, environment):
        self.control = control
        self.environment = environment
        self.poller = select.poll()
        self.wake_r, self.wake_w = os.pipe()
        os.set_blocking(self.wake_r, False)
        os.set_blocking(self.wake_w, False)
        self.children = {}  # process id -> [pid, status or None, whether it is PID 1 of a pid namespace]
        self.by_pid = {}  # pid -> process id
        self.directories = {}  # process id -> the directories made for it, removed when it is gone
        self.starting = {}  # process id -> [gate_w, err_r, pid, awaiting go]
        self.exec_watch = {}  # err_r fd -> process id
        self.waiters = []  # [request id, process id, deadline]
        self.stoppers = []  # [request id, process id, phase, deadline, grace]
        self.poller.register(self.control.fileno(), select.POLLIN)
        self.poller.register(self.wake_r, select.POLLIN)
        self.control_poll = select.poll()
        self.control_poll.register(self.control.fileno(), select.POLLIN | select.POLLHUP)
        self.mute = False  # during the rehearsal, replies go nowhere
        self.namespaces = False  # whether each process starts in namespaces of its own
        self.namespaces_reason = ""  # why not, when it doesn't

    # --- wire ---------------------------------------------------------------------------

    def send(self, message, fds=()):
        data = json.dumps(message).encode()
        if not self.mute:
            socket.send_fds(self.control, [data], list(fds))

    def reply(self, rid, **fields):
        fields["id"] = rid
        self.send(fields)

    def fail(self, rid, text):
        self.reply(rid, ok=False, error=text)

    def receive(self):
        """The next message and its descriptors, None when nothing is waiting, EOF at end."""
        if not self.control_poll.poll(0):
            return None
        data, fds, flags, _ = socket.recv_fds(self.control, MAX_MESSAGE, MAX_FDS)
        for fd in fds:
            os.set_inheritable(fd, False)
        if not data:
            return "EOF"
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            for fd in fds:
                os.close(fd)
            log("a message from the host was truncated")
            return ({}, [])
        try:
            message = json.loads(data)
        except ValueError:
            message = None
        return (message, fds)

    # --- requests -----------------------------------------------------------------------

    def handle(self, message, fds):
        rid = message.get("id") if isinstance(message, dict) else None
        try:
            if not isinstance(rid, int) or isinstance(rid, bool):
                raise ValueError("a request needs an integer id")
            op = message.get("op")
            handler = {
                "start": self.op_start,
                "go": self.op_go,
                "signal": self.op_signal,
                "wait": self.op_wait,
                "stop": self.op_stop,
            }.get(op)
            if handler is None:
                raise ValueError("unknown op %r" % (op,))
            handler(rid, message, fds)
        except Exception as error:
            if isinstance(rid, int):
                self.fail(rid, "%s: %s" % (type(error).__name__, error))
            else:
                log("a request with no id failed: %s: %s" % (type(error).__name__, error))
        for fd in fds:  # whatever a handler did not take
            os.close(fd)

    def known(self, message):
        process = message.get("process")
        entry = self.children.get(process) if isinstance(process, str) else None
        if entry is None:
            raise ValueError("no process %r started in this jail" % (process,))
        return process, entry

    def op_start(self, rid, message, fds):
        process, argv, cwd = message.get("process"), message.get("argv"), message.get("cwd")
        if not isinstance(process, str) or not process:
            raise ValueError("start needs a process id")
        if process in self.children:
            raise ValueError("process %r was already started" % process)
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(a, str) and "\0" not in a for a in argv)
            or not argv[0]
        ):
            raise ValueError("start needs a non-empty argv of strings")
        if not isinstance(cwd, str) or not cwd or "\0" in cwd:
            raise ValueError("start needs a working directory")
        if len(fds) != 3:
            raise ValueError("start needs exactly three descriptors: stdin, stdout, stderr")
        binds = self.directories_for(process, message) if self.namespaces else None
        made = []
        try:
            for _ in range(3):
                made.extend(os.pipe())
            pid = os.fork()
        except BaseException:
            self.abandon(process, made)
            raise
        gate_r, gate_w, err_r, err_w, report_r, report_w = pipes = tuple(made)
        if pid == 0:
            self.child(pipes, fds, argv, cwd, binds)
        os.close(report_w)
        if binds is None:
            os.close(report_r)
            inner = pid
            try:
                # The child does this too: whichever runs first, the group exists before the
                # host is told of the process, so the host never reads it in this one's.
                os.setpgid(pid, pid)
            except OSError:
                pass
        else:
            try:
                inner = self.pid_in_namespaces(pid, report_r, err_r)
            except BaseException:
                self.abandon(process, (gate_r, gate_w, err_r, err_w))
                raise
            finally:
                os.close(report_r)
        for fd in (gate_r, err_w, *fds):
            os.close(fd)
        del fds[:]
        self.children[process] = [inner, None, binds is not None]
        self.by_pid[inner] = process
        try:
            pidfd = os.pidfd_open(inner)
        except BaseException:
            os.kill(inner, signal.SIGKILL)
            os.close(gate_w)
            os.close(err_r)
            raise
        self.starting[process] = [gate_w, err_r, inner, False]
        try:
            self.send({"id": rid, "ok": True, "stage": "spawned", "pid": inner}, [pidfd])
        finally:
            os.close(pidfd)

    def abandon(self, process, pipes):
        """A start that failed before there was a process to answer for: its pipes closed and the
        directories made for it removed."""
        for fd in pipes:
            os.close(fd)
        self.remove_directories(process)

    def directories_for(self, process, message):
        """The bind mounts a process in namespaces of its own gets, `(source, target)` each, with
        the directories they bind made. In the channel directory (`chan`: its path in the jail and
        the name of the socket the process will bind there, if it has one) it gets a directory of
        its own over it, so it sees only that and no other process's socket; in the jail's scratch
        directory (`scratch`) one of its own, so its files are its own. A directory the jail can
        not write holds no socket and no file of anyone's: the process gets nothing over it, unless
        it was promised a socket there, which is an error.

        Raises:
            ValueError: `chan` or `scratch` is not what the host sends, or a directory promised
                a socket cannot hold one.
            OSError: a directory could not be made."""
        binds = []
        made = []
        chan, scratch = message.get("chan"), message.get("scratch")
        wanted = []
        if chan is not None:
            if not isinstance(chan, dict):
                raise ValueError("start's chan is not a directory and a name")
            wanted.append((chan.get("dir"), chan.get("name")))
        if scratch is not None:
            wanted.append((scratch, None))
        for shared, name in wanted:
            if (
                not isinstance(shared, str)
                or not shared.startswith("/")
                or "\0" in shared
                or not (name is None or (isinstance(name, str) and name and "/" not in name))
            ):
                raise ValueError("start names %r, which is not a directory and a socket's name" % ((shared, name),))
            if not os.path.isdir(shared) or not os.access(shared, os.W_OK):
                if name is not None:
                    raise ValueError(
                        "the channel directory %s is not one this jail can write, so it can "
                        "hold no socket" % shared
                    )
                continue
            source = os.path.join(shared, name or process)
            try:
                os.mkdir(source, 0o700)
            except BaseException:
                for earlier in made:
                    try:
                        os.rmdir(earlier)
                    except OSError:
                        pass
                raise
            made.append(source)
            binds.append((source, shared))
        self.directories[process] = made
        return binds

    def remove_directories(self, process):
        """The directories made for `process`, the ones it left empty removed."""
        for source in self.directories.pop(process, []):
            try:
                os.rmdir(source)
            except OSError:
                pass

    def pid_in_namespaces(self, child, report_r, err_r):
        """The number, in this pid namespace, of the process `child` made PID 1 of a new one. A
        child that could not leave for namespaces says why on `err_r` and ends.

        Raises:
            ValueError: it could not, or did not answer."""
        waiting = select.poll()
        waiting.register(report_r, select.POLLIN | select.POLLHUP)
        if not waiting.poll(int(NAMESPACE_START_TIMEOUT_S * 1000)):
            os.kill(child, signal.SIGKILL)
            raise ValueError("the process that makes a new process's namespaces did not answer")
        said = os.read(report_r, 32)
        if said.isdigit():
            return int(said)
        os.set_blocking(err_r, False)
        try:
            problem = os.read(err_r, 4096).decode(errors="replace")
        except BlockingIOError:
            problem = ""
        raise ValueError(problem or "the process that makes its namespaces ended without saying why")

    def child(self, pipes, stdio, argv, cwd, binds):
        """The forked child of a start. Never returns. With no namespaces it is the process:
        leader of a process group of its own, held at the gate until the host has written down
        who it is, then its descriptors, then the program. With them it leaves for them first and
        forks the process, which is PID 1 of the new pid namespace and leads a group in it, then
        tells the supervisor which it is and ends."""
        gate_r, gate_w, err_r, err_w, report_r, report_w = pipes
        try:
            os.close(self.control.fileno())
            os.close(gate_w)
            os.close(err_r)
            os.close(report_r)
            if binds is None:
                os.close(report_w)
                os.setpgid(0, 0)
                self.exec_after_gate(gate_r, err_w, stdio, argv, cwd, None)
            new_namespaces()
            inner = os.fork()
            if inner == 0:
                os.close(report_w)
                os.setpgid(0, 0)
                self.exec_after_gate(gate_r, err_w, stdio, argv, cwd, binds)
            try:
                os.setpgid(inner, inner)
            except OSError:
                pass
            os.write(report_w, str(inner).encode())
            os._exit(0)
        except BaseException as error:
            try:
                os.write(err_w, ("%s: %s" % (type(error).__name__, error)).encode())
            finally:
                os._exit(127)

    def exec_after_gate(self, gate_r, err_w, stdio, argv, cwd, binds):
        """The process, until exec: held at the gate, then in the namespaces' mounts, with its
        three descriptors as 0, 1 and 2 and no capability. Never returns."""
        if os.read(gate_r, 1) != b"g":
            os._exit(125)
        if binds is not None:
            isolate(binds)
        for target, fd in enumerate(stdio):
            os.dup2(fd, target)
        os.closerange(3, err_w)
        os.closerange(err_w + 1, os.sysconf("SC_OPEN_MAX"))
        signal.set_wakeup_fd(-1)
        for name in ("SIGPIPE", "SIGXFSZ", "SIGINT", "SIGCHLD"):
            signal.signal(getattr(signal, name), signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_SETMASK, [])
        if binds is not None:
            drop_capabilities()
        os.chdir(cwd)
        os.execvpe(argv[0], argv, self.environment)

    def op_go(self, rid, message, fds):
        process = message.get("process")
        entry = self.starting.get(process) if isinstance(process, str) else None
        if entry is None or entry[3]:
            raise ValueError("no started process %r is waiting for go" % (process,))
        gate_w, err_r, _, _ = entry
        if message.get("proceed") is not True:
            os.close(gate_w)
            os.close(err_r)
            del self.starting[process]
            self.reply(rid, ok=True, started=False)
            return
        os.write(gate_w, b"g")
        os.close(gate_w)
        entry[3] = rid
        self.exec_watch[err_r] = process
        self.poller.register(err_r, select.POLLIN | select.POLLHUP)

    def exec_done(self, err_r):
        process = self.exec_watch.pop(err_r)
        self.poller.unregister(err_r)
        rid = self.starting.pop(process)[3]
        try:
            problem = os.read(err_r, 4096)
        finally:
            os.close(err_r)
        if problem:
            self.reply(rid, ok=False, error=problem.decode(errors="replace"))
        else:
            self.reply(rid, ok=True, started=True)

    def op_signal(self, rid, message, fds):
        _, entry = self.known(message)
        sig = message.get("sig")
        if not isinstance(sig, int) or isinstance(sig, bool) or not 0 < sig < 65:
            raise ValueError("signal needs a signal number")
        delivered = False
        if entry[1] is None:
            delivered = self.deliver(entry, sig)
        self.reply(rid, ok=True, delivered=delivered)

    def op_wait(self, rid, message, fds):
        process, _ = self.known(message)
        timeout = message.get("timeout")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout < 0:
            raise ValueError("wait needs a timeout in seconds")
        self.waiters.append([rid, process, time.monotonic() + timeout])
        self.service()

    def op_stop(self, rid, message, fds):
        process, entry = self.known(message)
        grace = message.get("grace")
        if not isinstance(grace, (int, float)) or isinstance(grace, bool) or grace < 0:
            raise ValueError("stop needs a grace period in seconds")
        if self.group_empty(entry[0]):
            self.reply(rid, ok=True, outcome="already_gone", detail="")
            return
        self.deliver(entry, signal.SIGTERM)
        self.stoppers.append([rid, process, 1, time.monotonic() + grace, grace])
        self.service()

    # --- the loop -----------------------------------------------------------------------

    @staticmethod
    def group_empty(pgid):
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    @staticmethod
    def signal_group(pgid, sig):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass

    def deliver(self, entry, number):
        """`number` to a process's group, as the process would take it if it were no namespace's
        init: the one that is (`entry[2]`) is sent what ends it where the kernel would drop the
        signal. True when there was a group to signal."""
        pid = entry[0]
        try:
            os.killpg(pid, signal_for_init(pid, number) if entry[2] else number)
        except ProcessLookupError:
            return False
        return True

    def reap(self):
        """Every child that has ended: the ones a request started, with their status kept for
        `wait`, and every orphan the jail's processes left, whose status nobody asked for."""
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return
            if pid == 0:
                return
            process = self.by_pid.get(pid)
            if process is not None:
                del self.by_pid[pid]
                self.children[process][1] = os.waitstatus_to_exitcode(status)
                self.remove_directories(process)

    def service(self):
        """Answer what can be answered: waits whose process ended or whose time is up, stops whose
        group is empty or whose next rung is due."""
        now = time.monotonic()
        kept = []
        for waiter in self.waiters:
            rid, process, deadline = waiter
            status = self.children[process][1]
            if status is not None:
                self.reply(rid, ok=True, status=status)
            elif now >= deadline:
                self.reply(rid, ok=True, status=None)
            else:
                kept.append(waiter)
        self.waiters = kept
        kept = []
        for stopper in self.stoppers:
            rid, process, phase, deadline, grace = stopper
            pgid = self.children[process][0]
            if self.group_empty(pgid):
                self.reply(rid, ok=True, outcome="ended", detail="")
            elif now < deadline:
                kept.append(stopper)
            elif phase == 1:
                self.signal_group(pgid, signal.SIGKILL)
                stopper[2], stopper[3] = 2, now + grace
                kept.append(stopper)
            else:
                self.reply(
                    rid,
                    ok=True,
                    outcome="failed",
                    detail="process group %d still had a member after SIGTERM and SIGKILL" % pgid,
                )
        self.stoppers = kept

    def timeout_ms(self):
        """How long the loop may sleep: until the next wait's deadline, and in short ticks while
        a stop is under way. Never past either; None when neither is pending."""
        now = time.monotonic()
        due = [deadline for _, _, deadline in self.waiters]
        due += [min(deadline, now + TICK_S) for _, _, _, deadline, _ in self.stoppers]
        if not due:
            return None
        return max(0, int((min(due) - now) * 1000) + 1)

    def rehearse(self):
        """Do each kind of thing the supervisor will ever do, once, before it says it is ready:
        look a program up through the search path, pass descriptors over a socket, start a
        process (which fails to exec), wait for it, signal it and stop it. Whatever the
        interpreter loads late for any of it is loaded now, in this process, which every process
        it starts is forked from; the guard that refuses imports once it is ready
        (`NoMoreImports`) then finds nothing to refuse. Replies go nowhere; nothing is left."""
        self.mute = True
        try:
            # The last thing a started process does is look for its program through the search
            # path, and what that imports is imported by the child, which is gone with it: do it
            # here, where it stays, with a name no program has, so it ends in the error it is for.
            os.execvpe("brig-rehearsal-no-such-program", ["brig-rehearsal"], self.environment)
        except OSError:
            pass
        first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        socket.send_fds(first, [b"rehearsal"], [0])
        for fd in socket.recv_fds(second, 64, 1)[1]:
            os.close(fd)
        first.close()
        second.close()
        stdio = [os.open("/dev/null", os.O_RDWR) for _ in range(3)]
        name = "rehearsal"
        self.op_start(0, {"process": name, "argv": ["brig-rehearsal-no-such-program"], "cwd": "/"}, stdio)
        self.op_go(0, {"process": name, "proceed": True}, [])
        self.exec_done(next(iter(self.exec_watch)))
        while self.children[name][1] is None:
            self.reap()
        self.op_signal(0, {"process": name, "sig": 1}, [])
        self.op_wait(0, {"process": name, "timeout": 0}, [])
        self.op_stop(0, {"process": name, "grace": 0}, [])
        self.service()
        del self.children[name]
        self.mute = False

    def probe_namespaces(self):
        """Whether a process of this jail can have namespaces of its own here, found out by doing
        it once: leave for them, fork the PID 1 of the new pid namespace, give it a fresh /proc and
        a loopback, drop its capabilities. Empty when it can, else why not, in a line. Nothing is
        left running. Whatever the interpreter loads late for it is loaded now, as for the
        rehearsal."""
        if os.geteuid() == 0:
            return (
                "the jail runs as uid 0: bwrap covers its /proc/irq and /proc/bus there, and "
                "the kernel refuses a fresh /proc under mounts that hide those "
                "(mount_too_revealing), so a process could have no /proc of its own"
            )
        reader, writer = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(reader)
                os.close(self.control.fileno())
                new_namespaces()
                inner = os.fork()
                if inner == 0:
                    try:
                        isolate([])
                        drop_capabilities()
                        os.write(writer, b"ok")
                    except BaseException as error:
                        os.write(writer, ("%s" % error).encode())
                    os._exit(0)
                os.waitpid(inner, 0)
            except BaseException as error:
                os.write(writer, ("%s" % error).encode())
            os._exit(0)
        os.close(writer)
        said = os.read(reader, 4096)
        os.close(reader)
        os.waitpid(pid, 0)
        if said == b"ok":
            return ""
        return said.decode(errors="replace") or "the probe ended without saying why"

    def run(self):
        self.send(
            {
                "hello": 1,
                "protocol": PROTOCOL,
                "python": sys.version.split()[0],
                "namespaces": {"held": self.namespaces, "reason": self.namespaces_reason},
            }
        )
        while True:
            events = self.poller.poll(self.timeout_ms())
            for fd, _ in events:
                if fd == self.wake_r:
                    try:
                        os.read(self.wake_r, 4096)
                    except BlockingIOError:
                        pass
                elif fd in self.exec_watch:
                    self.exec_done(fd)
            self.reap()
            while True:
                got = self.receive()
                if got is None:
                    break
                if got == "EOF":
                    log("the host's end of the control socket closed: ending the jail")
                    os._exit(0)
                self.handle(*got)
            self.service()


class NoMoreImports:
    """Once the supervisor has said it is ready, an import is a bug: it would read files the
    jail can write (the standard library's, where a Spec lets it) while processes of the jail
    run, and the program's promise is that every import was done before any of them existed. A
    finder first on the path that refuses every module not already loaded makes the promise
    something that fails loudly where it is broken, not something a reader has to trust."""

    @staticmethod
    def find_spec(name, path=None, target=None):
        raise ImportError(
            "brig supervisor: %r was not imported before the supervisor was ready, and it "
            "imports nothing after" % name
        )


def wake(signum, frame):
    """SIGCHLD's handler: the wake-up descriptor does the work; nothing here reads a signal's
    sender or acts on it."""


def quiet_stdin():
    """Descriptor 0 is /dev/null. bwrap reads the source from it and closes it, so it is free when
    this starts: the first thing opened would take it."""
    null = os.open("/dev/null", os.O_RDONLY)
    if null != 0:
        os.dup2(null, 0)
        os.close(null)


def main():
    quiet_stdin()
    check_platform()
    environment = inherited_environment()
    try:
        control = socket.socket(fileno=int(sys.argv[1]))
    except (IndexError, ValueError, OSError):
        die("needs its control socket's descriptor as its one argument")
    os.set_inheritable(control.fileno(), False)
    make_undumpable()
    # Nothing but the wake-up a child's end needs: every other signal keeps its default, which
    # for a pid namespace's init means a signal from inside is dropped (SIGKILL and SIGSTOP
    # included) and one from the host's side is the host's.
    supervisor = Supervisor(control, environment)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.set_wakeup_fd(supervisor.wake_w, warn_on_full_buffer=False)
    signal.signal(signal.SIGCHLD, wake)
    supervisor.rehearse()
    supervisor.namespaces_reason = supervisor.probe_namespaces()
    supervisor.namespaces = not supervisor.namespaces_reason
    sys.meta_path.insert(0, NoMoreImports)
    try:
        supervisor.run()
    except BaseException as error:
        try:
            log("fatal: %s: %s" % (type(error).__name__, error))
            traceback.print_exc()
        finally:
            os._exit(70)


main()
'''


def supervisor_argv(plan: SupervisorPlan, control_fd: int) -> tuple[str, ...]:
    """The argv the jail's PID 1 runs, after the stack's wrap: `plan`'s interpreter, isolated
    (`-I`: no working or script directory on the import path, no `PYTHON*` variable, no user
    site directory), the program at `SUPERVISOR_SOURCE_PATH`, and the descriptor of its end of
    the control socket. Pure."""
    return (plan.interpreter, "-I", SUPERVISOR_SOURCE_PATH, str(control_fd))
