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
PROTOCOL: Final = 1

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

The wire (decision-191): the control socket is a SOCK_SEQPACKET socketpair, one JSON object per
message, file descriptors by SCM_RIGHTS. A request is {"id": n, "op": ..., ...}; its reply is
{"id": n, "ok": true|false, ...}. The supervisor says {"hello": 1, ...} once before any request.
"""

import array  # socket.send_fds and recv_fds import it themselves, late, on newer Pythons
import ctypes
import json
import os
import select
import signal
import socket
import sys
import time
import traceback
import warnings  # os.get_exec_path imports it, late, on every Python; the rehearsal covers the rest

PROTOCOL = 1

#: One message from the host; larger is a protocol error, never read half.
MAX_MESSAGE = 1 << 20

#: Descriptors the host may pass with one message: a start's three stdio files.
MAX_FDS = 4

PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4

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
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        die("could not make itself undumpable (prctl: errno %d)" % ctypes.get_errno())
    if libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0) != 0:
        die("is still dumpable after prctl")


class Supervisor:
    def __init__(self, control, environment):
        self.control = control
        self.environment = environment
        self.poller = select.poll()
        self.wake_r, self.wake_w = os.pipe()
        os.set_blocking(self.wake_r, False)
        os.set_blocking(self.wake_w, False)
        self.children = {}  # process id -> [pid, status or None]
        self.by_pid = {}  # pid -> process id
        self.starting = {}  # process id -> [gate_w, err_r, pid, awaiting go]
        self.exec_watch = {}  # err_r fd -> process id
        self.waiters = []  # [request id, process id, deadline]
        self.stoppers = []  # [request id, process id, phase, deadline, grace]
        self.poller.register(self.control.fileno(), select.POLLIN)
        self.poller.register(self.wake_r, select.POLLIN)
        self.control_poll = select.poll()
        self.control_poll.register(self.control.fileno(), select.POLLIN | select.POLLHUP)
        self.mute = False  # during the rehearsal, replies go nowhere

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
        gate_r, gate_w = os.pipe()
        err_r, err_w = os.pipe()
        try:
            pid = os.fork()
        except BaseException:
            for fd in (gate_r, gate_w, err_r, err_w):
                os.close(fd)
            raise
        if pid == 0:
            self.child(gate_r, gate_w, err_r, err_w, fds, argv, cwd)
        try:
            # The child does this too: whichever runs first, the group exists before the host
            # is told of the process, so the host never reads it in this one's.
            os.setpgid(pid, pid)
        except OSError:
            pass
        for fd in (gate_r, err_w, *fds):
            os.close(fd)
        del fds[:]
        try:
            pidfd = os.pidfd_open(pid)
        except BaseException:
            os.kill(pid, signal.SIGKILL)
            os.close(gate_w)
            os.close(err_r)
            self.children[process] = [pid, None]
            self.by_pid[pid] = process
            raise
        self.children[process] = [pid, None]
        self.by_pid[pid] = process
        self.starting[process] = [gate_w, err_r, pid, False]
        try:
            self.send({"id": rid, "ok": True, "stage": "spawned", "pid": pid}, [pidfd])
        finally:
            os.close(pidfd)

    def child(self, gate_r, gate_w, err_r, err_w, stdio, argv, cwd):
        """The forked child, until exec: leader of a process group of its own, held at the gate
        until the host has written down who it is, then its descriptors, then the program.
        Never returns."""
        try:
            os.close(self.control.fileno())
            os.close(gate_w)
            os.close(err_r)
            os.setpgid(0, 0)
            if os.read(gate_r, 1) != b"g":
                os._exit(125)
            for target, fd in enumerate(stdio):
                os.dup2(fd, target)
            os.closerange(3, err_w)
            os.closerange(err_w + 1, os.sysconf("SC_OPEN_MAX"))
            signal.set_wakeup_fd(-1)
            for name in ("SIGPIPE", "SIGXFSZ", "SIGINT", "SIGCHLD"):
                signal.signal(getattr(signal, name), signal.SIG_DFL)
            signal.pthread_sigmask(signal.SIG_SETMASK, [])
            os.chdir(cwd)
            os.execvpe(argv[0], argv, self.environment)
        except BaseException as error:
            try:
                os.write(err_w, ("%s: %s" % (type(error).__name__, error)).encode())
            finally:
                os._exit(127)

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
            try:
                os.killpg(entry[0], sig)
                delivered = True
            except ProcessLookupError:
                pass
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
        self.signal_group(entry[0], signal.SIGTERM)
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

    def run(self):
        self.send({"hello": 1, "protocol": PROTOCOL, "python": sys.version.split()[0]})
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
