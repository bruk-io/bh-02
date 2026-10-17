"""A container's processes started with `docker exec` (SPEC.md section 8, decision-203).

The agent of a container whose image has no interpreter for brig's supervisor. Docker cannot signal
an exec, so what `docker exec` gives is a way to start a process in the container, and what it
gives back is the client's exit status. Everything else is the host's, on the ids the host records:

- **A start is held at a gate and recorded before it runs a byte**, as the supervisor's is
  (`brig/run/_supervised.py`). The host runs `docker exec ... /bin/sh -c SHIM ...`; the shim checks
  that the program is there, announces its own pid in a file of the channel directory, and blocks
  reading a FIFO the host made beside it. The host finds the process the pid names on its own side
  (`find_host_pid`: a process whose `NSpid` ends in the number and whose pid namespace is the
  container's, so a number in the container never names a host process outside it), reads its start
  stamp, writes its record, and only then writes `go` to the FIFO, which `exec`s the program.
- **Control is `HostSupervisor`'s**: the host's ladder on the recorded pid, group and stamp, with the
  identity checks of decision-155 and the host's own scan of the process table to verify.
  `docker exec` makes the process a session leader (measured: pgid = sid = pid), so it leads a group
  of its own and the dial's peer check (decision-185) is the one every runtime makes.
- **What `wait` answers** is the status of the `docker exec` client, kept in the process that
  started it under the process's recorded pid: `128 + n` for a signal `n`, which a status of a
  process cannot be told from. Anywhere else it is `ExitStatusUnobservable`.

The file the shim announces in is the jail's to write, so the pid in it is the host's best reading
and not an unforgeable one: a co-tenant that races the host can name a decoy (SPEC.md section 9
grades it). The decisions (`exec_argv`, `announced_pid`, `nspid_of`, `pick_host_pid`) are pure; the
rest is the shell that runs `docker`, reads `/proc` and the files, and opens the gate.
"""

import contextlib
import errno
import math
import os
import shutil
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from signal import Signals
from typing import Final

from brig.run import _identity, _records, _waiters
from brig.run._exit_status import WorkloadSpawnFailed
from brig.run.host import HostSupervisor
from brig.run.runtime import (
    ExitStatusUnobservable,
    IoPolicy,
    JailRecord,
    ProcessRecord,
    Reservation,
    channel_dir_of,
    refuse_foreign_reservation,
)
from brig.run.teardown import KillOutcome, KillReport, end_group

#: How long `docker exec` may take to start the shim and have it announce its pid: a client and a
#: shell, about 0.1 s, so a miss is a wedged daemon.
_ANNOUNCE_TIMEOUT_S: Final = 30.0

#: How long the gate may take to open once the host has the process recorded: the shim is a few
#: instructions from reading it.
_GATE_TIMEOUT_S: Final = 10.0

_POLL_S: Final = 0.002

#: How long one look at `HostSupervisor.wait` may take before `ExecSupervisor.wait` asks again.
_WAIT_CHUNK_S: Final = 2.0

#: The shim `/bin/sh -c` runs, with the pid file, the gate and the argv as its positional parameters
#: (never interpolated). It checks the program is there before announcing anything (not one is exit
#: 127, with a message on the process's stderr), announces its pid with one `echo` (one `write`, so
#: the host never reads half a number), blocks reading the gate, and `exec`s the program only for
#: `go`: anything else is exit 125.
SHIM: Final = (
    'p=$1; g=$2; shift 2; command -v "$1" >/dev/null 2>&1 || '
    '{ echo "brig: $1: not found" >&2; exit 127; }; '
    'echo $$ >"$p" || exit 126; read go <"$g"; [ "$go" = go ] || exit 125; exec "$@"'
)


# ---------------------------------------------------------------------------------------------
# The decisions: pure.
# ---------------------------------------------------------------------------------------------


def exec_argv(
    docker: str, container_id: str, *, cwd: str, pidfile: str, gate: str, argv: Sequence[str]
) -> tuple[str, ...]:
    """The command line that starts `argv` in the container behind the gate: the shim, its pid
    file and its gate, then the argv. `--` keeps the container an operand. Pure."""
    return (
        docker,
        "exec",
        "--workdir",
        cwd,
        "--",
        container_id,
        "/bin/sh",
        "-c",
        SHIM,
        "brig-exec",
        pidfile,
        gate,
        *argv,
    )


def announced_pid(text: str) -> int | None:
    """The pid a shim announced, from the text of its file: one complete line of digits. `None`
    for anything else (nothing yet, half a line, a line that is not a number), which a caller
    reads as "not yet" until its deadline. Pure."""
    if not text.endswith("\n"):
        return None
    digits = text[:-1]
    if not digits.isascii() or not digits.isdigit() or len(digits) > 10:
        return None
    pid = int(digits)
    return pid if pid > 0 else None


def nspid_of(status: str) -> tuple[int, ...]:
    """The `NSpid:` line of a `/proc/<pid>/status`: the process's pid in each pid namespace it is
    in, outermost first, so its own namespace's is the last. Empty when there is none. Pure."""
    for line in status.splitlines():
        if line.startswith("NSpid:"):
            fields = line.split()[1:]
            return tuple(int(field) for field in fields) if all(f.isdigit() for f in fields) else ()
    return ()


def pick_host_pid(
    rows: Iterable[tuple[int, tuple[int, ...], str]], container_pid: int, pid_ns: str
) -> int | None:
    """The host pid of the process that is `container_pid` in the pid namespace `pid_ns`, from
    `rows` of `(host pid, NSpid, pid namespace)` for the host's processes. A process is in `pid_ns`
    when its namespace is, and its pid there is the last of its `NSpid`. `None` when no process, or
    more than one (which a namespace never has, so it is a doubt), is. Pure."""
    found = {
        host
        for host, nspid, ns in rows
        if ns == pid_ns and len(nspid) >= 2 and nspid[-1] == container_pid
    }
    return next(iter(found)) if len(found) == 1 else None


def spawn_failure(client_status: int, stderr: str, program: str, container_id: str) -> str:
    """What to tell the caller of a start whose `docker exec` client ended before the shim
    announced: the program, the container, the client's status and the tail of what it said (the
    shim's "not found", or Docker's own error for a missing container or working directory). Pure."""
    said = stderr.strip()[-500:]
    return (
        f"docker exec could not start {program!r} in container {container_id[:12]} (the client "
        f"ended with status {client_status} before the process was announced): "
        f"{said or 'it said nothing'}"
    )


# ---------------------------------------------------------------------------------------------
# The shell.
# ---------------------------------------------------------------------------------------------


def find_host_pid(container_pid: int, init_pid: int) -> int | None:
    """The host pid of the process that is `container_pid` in the pid namespace of the container
    whose PID 1 is the host's `init_pid`, found in `/proc`; `None` when the host sees no such
    process (it has gone, or the container's processes are not in this pid namespace)."""
    try:
        pid_ns = os.readlink(f"/proc/{init_pid}/ns/pid")
        names = os.listdir("/proc")
    except OSError:
        return None
    rows: list[tuple[int, tuple[int, ...], str]] = []
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/status", encoding="utf-8", errors="replace") as status:
                nspid = nspid_of(status.read())
            if len(nspid) < 2 or nspid[-1] != container_pid:
                continue
            rows.append((int(name), nspid, os.readlink(f"/proc/{name}/ns/pid")))
        except OSError:
            continue
    return pick_host_pid(rows, container_pid, pid_ns)


def _read_announcement(path: str) -> int | None:
    """The pid in `path`, if the shim has announced one: the file is the jail's, so it is opened
    without following a link and read no further than a pid is long."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        return announced_pid(os.read(fd, 64).decode("ascii", errors="replace"))
    except OSError:
        return None
    finally:
        os.close(fd)


def _write_gate(gate: str, word: bytes, *, proc: subprocess.Popen[bytes], seconds: float) -> bool:
    """Write `word` to the gate FIFO once the shim has it open for reading (a non-blocking open of
    a FIFO nobody reads is `ENXIO`, retried), unless the client has ended or `seconds` pass. Whether
    it was written."""
    deadline = time.monotonic() + seconds
    while proc.poll() is None and time.monotonic() < deadline:
        try:
            fd = os.open(gate, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as error:
            if error.errno not in (errno.ENXIO, errno.EINTR):
                return False
            time.sleep(_POLL_S)
            continue
        try:
            os.write(fd, word)
        except OSError:
            return False
        finally:
            os.close(fd)
        return True
    return False


def _wait_for_exec(client: subprocess.Popen[bytes], pid: int, process_id: str) -> None:
    """Return once the shim has `exec`ed the program (its command line no longer carries the
    start's id), the process has gone or the client has ended, or `_GATE_TIMEOUT_S` passes: as the
    supervisor answers a start once the exec has happened, so a signal sent as `start` returns
    meets the program and not the shim."""
    deadline = time.monotonic() + _GATE_TIMEOUT_S
    while time.monotonic() < deadline:
        cmdline = _cmdline(pid)
        if not cmdline or process_id not in cmdline or client.poll() is not None:
            return
        time.sleep(_POLL_S)


def _tail(path: str) -> str:
    try:
        with open(path, "rb") as log:
            return log.read()[-2000:].decode(errors="replace")
    except OSError:
        return ""


@dataclass(frozen=True, slots=True)
class ExecSupervisor:
    """Starts, signals, waits for and stops the processes of one container jail whose agent is
    `docker exec`. Holds the jail's record and what it needs to run the CLI: `docker`, the absolute
    path of the client, and `env`, the environment it is run with (the runtime's own, which names
    the daemon). `signal`, `wait` and `stop` are `HostSupervisor`'s on the recorded ids."""

    jail: JailRecord
    docker: str
    env: Mapping[str, str]

    def start(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        io: IoPolicy,
        channel: Reservation | None = None,
    ) -> ProcessRecord:
        """Start `argv` in the container (decision-203): held at the shim's gate until its record
        is written, in `cwd`, with the container's environment, stdin `/dev/null`, stdio per `io`
        in its records directory `<jail_dir>/procs/<id>/`, its `record.json` naming `channel`'s
        socket as the one it binds.

        Raises:
            ReservationRefused: `channel` is not a socket the runtime would reserve in this jail,
                or a process the jail knows already binds it; raised before anything is made.
            TetherClosed: the jail is tethered and its tether has ended; raised before anything
                is made.
            WorkloadSpawnFailed: `docker exec` could not start the shim (the container is gone,
                the working directory is not there), the program is not there, the host cannot
                name the process it started, or the gate would not open; nothing is left running.
            OSError: the records directory, the FIFO or the record could not be written (the
                process is released to exit first).
        """
        jail = self.jail
        if jail.held is not None and jail.held.tether is not None:
            jail.held.tether.fd()  # a tether that has ended refuses here, before anything is made
        if channel is not None:
            refuse_foreign_reservation(jail, channel)
        process_id = _records.new_id()
        order = time.time_ns()
        directory = _records.make_dir(jail.jail_dir, process_id)
        try:
            return self._started(
                tuple(argv), cwd, io, channel, process_id=process_id, order=order, where=directory
            )
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def _started(
        self,
        argv: tuple[str, ...],
        cwd: str,
        io: IoPolicy,
        channel: Reservation | None,
        *,
        process_id: str,
        order: int,
        where: str,
    ) -> ProcessRecord:
        """The start behind its records directory: the FIFO, the client, the announcement, the
        record and the gate.

        Raises:
            WorkloadSpawnFailed, OSError: as `start`.
        """
        container = self.jail.container
        if container is None or container.init_pid <= 0:
            raise WorkloadSpawnFailed(
                f"jail {self.jail.jail_id!r} has no container this process knows the PID 1 of, so "
                "a process started in it could not be named by the host"
            )
        chan = channel_dir_of(self.jail)
        pidfile, gate = f"{chan}/{process_id}.pid", f"{chan}/{process_id}.go"
        stdout_path = os.path.join(where, io.stdout_name)
        stderr_path = os.path.join(where, io.stderr_name)
        os.mkfifo(gate, 0o600)
        try:
            with open(stdout_path, "wb") as stdout_f, open(stderr_path, "wb") as stderr_f:
                client = subprocess.Popen(
                    exec_argv(
                        self.docker,
                        container.container_id,
                        cwd=cwd,
                        pidfile=pidfile,
                        gate=gate,
                        argv=argv,
                    ),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_f,
                    stderr=stderr_f,
                    env=dict(self.env),
                    close_fds=True,
                    start_new_session=True,
                )
            try:
                return self._recorded_and_released(
                    client,
                    argv,
                    channel,
                    process_id=process_id,
                    order=order,
                    pidfile=pidfile,
                    gate=gate,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    init_pid=container.init_pid,
                    container_id=container.container_id,
                )
            except BaseException:
                _write_gate(gate, b"x\n", proc=client, seconds=1.0)  # let the shim go, to exit
                with contextlib.suppress(OSError):
                    client.kill()
                client.wait()
                raise
        finally:
            for path in (pidfile, gate):
                with contextlib.suppress(OSError):
                    os.unlink(path)

    def _recorded_and_released(
        self,
        client: subprocess.Popen[bytes],
        argv: tuple[str, ...],
        channel: Reservation | None,
        *,
        process_id: str,
        order: int,
        pidfile: str,
        gate: str,
        stdout_path: str,
        stderr_path: str,
        init_pid: int,
        container_id: str,
    ) -> ProcessRecord:
        """Wait for the announcement, name the process, record it, open the gate.

        Raises:
            WorkloadSpawnFailed: as `start`.
            OSError: the record could not be written.
        """
        deadline = time.monotonic() + _ANNOUNCE_TIMEOUT_S
        announced: int | None = None
        while announced is None:
            announced = _read_announcement(pidfile)
            if announced is not None:
                break
            status = client.poll()
            if status is not None:
                raise WorkloadSpawnFailed(
                    spawn_failure(status, _tail(stderr_path), argv[0], container_id)
                )
            if time.monotonic() > deadline:
                raise WorkloadSpawnFailed(
                    f"docker exec did not start {argv[0]!r} in container {container_id[:12]} "
                    f"within {_ANNOUNCE_TIMEOUT_S:.0f}s: is the daemon answering?"
                )
            time.sleep(_POLL_S)
        pid = find_host_pid(announced, init_pid)
        if pid is None or process_id not in _cmdline(pid):
            raise WorkloadSpawnFailed(
                f"the shim of {argv[0]!r} announced pid {announced} in container "
                f"{container_id[:12]}, and the host cannot find that process in its own pid "
                "namespace (a daemon that is not on this host, a user-namespace remap) or it is "
                "not the shim: a process the host cannot name is a process it cannot end, so it "
                "was not allowed to run"
            )
        stamp = _identity.start_stamp(pid)
        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = -1
        if stamp == _identity.UNKNOWN or pgid != pid:
            raise WorkloadSpawnFailed(
                f"docker exec started {argv[0]!r} as host pid {pid}, but its start time is "
                f"{'unreadable' if stamp == _identity.UNKNOWN else 'readable'} and its process "
                f"group is {pgid}: it does not lead a group of its own, so it cannot be "
                "identified. It was not allowed to run"
            )
        held = self.jail.held
        _waiters.watch(
            client,
            jail_id=self.jail.jail_id,
            sensors=() if held is None else held.sensors,
            pid=pid,
        )
        record = ProcessRecord(
            id=process_id,
            order=order,
            pid=pid,
            pgid=pgid,
            start_time=stamp,
            argv=argv,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            channel=None if channel is None else channel.channel,
            bound_path=None if channel is None else channel.bound_path,
        )
        _records.write(self.jail.jail_dir, record)
        if not _write_gate(gate, b"go\n", proc=client, seconds=_GATE_TIMEOUT_S):
            item = end_group("exec_sibling", pgid, pid, stamp)
            raise WorkloadSpawnFailed(
                f"the gate of {argv[0]!r} (host pid {pid}) would not open within "
                f"{_GATE_TIMEOUT_S:.0f}s, so it was ended"
                + ("" if item.outcome is not KillOutcome.FAILED else f" (failed: {item.detail})")
            )
        _wait_for_exec(client, pid, process_id)
        return record

    def signal(self, process: ProcessRecord, sig: Signals) -> bool:
        """`sig` to `process`'s group by the host's identity checks (`HostSupervisor.signal`)."""
        return HostSupervisor(self.jail).signal(process, sig)

    def wait(self, process: ProcessRecord, timeout: float | None) -> int | None:
        """`process`'s exit status as `docker exec` reported it, or `None` while it runs at the
        deadline (`HostSupervisor.wait`). The client reports when the process has ended and
        everything holding its output has closed it, so a program that left a child holding its
        stdout holds the status back until the child ends: while the client is still waited for
        this keeps waiting, to the deadline, even though the process is gone.

        Raises:
            ExitStatusUnobservable: the process is gone and this process never observed how.
            ValueError: its exit record does not hold an integer.
        """
        deadline = math.inf if timeout is None else time.monotonic() + timeout
        host = HostSupervisor(self.jail)
        while True:
            try:
                status = host.wait(
                    process, min(_WAIT_CHUNK_S, max(0.0, deadline - time.monotonic()))
                )
            except ExitStatusUnobservable:
                if not _waiters.is_watched(process.pid):
                    raise
                status = None
            if status is not None:
                return status
            if time.monotonic() >= deadline:
                return None

    def stop(self, process: ProcessRecord) -> KillReport:
        """The host's ladder on `process`'s group (`HostSupervisor.stop`), one item."""
        return HostSupervisor(self.jail).stop(process)


def _cmdline(pid: int) -> str:
    """The command line of the host process `pid` as one string, `""` when it cannot be read."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as cmdline:
            return cmdline.read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""
