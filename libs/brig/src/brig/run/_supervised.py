"""A supervised jail's `Supervisor`: starts, signals, waits and stops, each a request to the
jail's PID 1 (SPEC.md sections 8 and 9, decision-191 and decision-192).

`HostRuntime.supervisor` hands this out for a jail whose runtime holds the link to its supervisor
(`Held.link`): the process that created it. Everything below is the host's half of the wire in
`brig/run/_supervisor_link.py`; the program on the other end is `brig/run/_supervisor_program.py`.

**A start is two requests, so a process never runs before it is written down.** The supervisor
forks the process and holds it at a gate, before it has opened a descriptor or run a byte, and
answers with the process's number inside the jail and a pidfd; the host turns the pidfd into the
process's *host* pid (`/proc/self/fdinfo/<fd>`, the kernel's own translation between pid
namespaces), reads when that process started, checks it leads a group of its own, writes its record
(`<jail_dir>/procs/<id>/record.json`, kill authority, so written by the host alone), and only then
says `go`: the supervisor opens the stdio the host passed by `SCM_RIGHTS`, changes directory and
execs, and answers once the exec has happened or failed. So every record names a process that
existed when it was written, a pid that could not have been anyone else's, and a failed exec is a
failed start with its reason. The old shape had a window between the spawn and the record in which
a process ran unrecorded; this one has none.

**What a record names is the host's view of the process.** Its `pid` is the process's pid in the
host's pid namespace, its `pgid` its own (the supervisor puts each process in a session of its
own), its stamp the moment it started: the identity every check of the host-side machinery
(`Process.alive`, the verified dial of `brig/run/dial.py`, a rehydrated jail's teardown) already
makes, unchanged. What control the host has of a supervised process, though, is the request, not
the number: `signal`, `wait` and `stop` name the process by its id, so a number the jail could
influence is never what the supervisor acts on.
"""

import contextlib
import math
import os
import re
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass
from signal import Signals
from typing import Final

from brig.core.runtime import scratch_dir
from brig.run import _identity, _records, _waiters
from brig.run._exit_status import WorkloadSpawnFailed
from brig.run._supervisor_link import (
    SupervisorGone,
    SupervisorLink,
    SupervisorRefused,
)
from brig.run.runtime import (
    ExitStatusUnobservable,
    IoPolicy,
    JailRecord,
    ProcessRecord,
    Reservation,
    channel_dir_of,
    refuse_foreign_reservation,
)
from brig.run.teardown import KillItem, KillOutcome, KillReport, group_alive

#: How long the supervisor may take to answer a request that does only a few system calls
#: (a start's two steps, a signal): ten times what a slow host needs, so a miss means the
#: supervisor is wedged and not slow (SPEC.md section 8, decision-191). A miss ends the jail.
REQUEST_TIMEOUT_S: Final = 30.0

#: The longest one `wait` request holds the supervisor's answer: a wait without a deadline, or
#: a long one, is asked again, so a wedged supervisor is found within this and the slack.
WAIT_CHUNK_S: Final = 5.0

#: Added to what a request itself may take (a wait's chunk, a stop's two graces) to make its
#: host-side deadline.
SLACK_S: Final = 10.0

#: The ladder's grace, as the host's own ladder has it (`brig.run.teardown.DEFAULT_GRACE_S`): once
#: after `SIGTERM`, once after `SIGKILL`.
STOP_GRACE_S: Final = 2.0

_FDINFO_PID: Final = re.compile(r"^Pid:\s+(-?\d+)\s*$", re.MULTILINE)


def host_pid_of(pidfd: int) -> int | None:
    """The pid in this process's own pid namespace of the process `pidfd` names, as the kernel
    reports it in `/proc/self/fdinfo/<fd>`: `None` when that process has gone, or is not one this
    namespace can see, or when the kernel reports no pid (a kernel before 5.4)."""
    try:
        with open(f"/proc/self/fdinfo/{pidfd}", encoding="utf-8") as info:
            text = info.read()
    except OSError:
        return None
    found = _FDINFO_PID.search(text)
    if found is None:
        return None
    pid = int(found.group(1))
    return pid if _records.is_process_id(pid) else None


def stop_item(kind: str, process: ProcessRecord, outcome: str, detail: str, gone: bool) -> KillItem:
    """The `KillItem` for the supervisor's answer to a `stop`, checked against the host's own
    observation: `outcome` is what the supervisor said (`ended`, `already_gone`, `failed`), and
    `gone` is whether the host, scanning the process table itself, found the process's group
    empty. `ended` is only reported when both agree: a supervisor that says a group ended while the
    host sees it run is a `FAILED` item, never `ENDED` (law 1). Pure."""
    identity = str(process.pgid)
    if outcome == "failed":
        return KillItem(kind, identity, KillOutcome.FAILED, detail)
    if not gone:
        return KillItem(
            kind,
            identity,
            KillOutcome.FAILED,
            f"the supervisor said process group {process.pgid} was {outcome.replace('_', ' ')}, "
            "but the host still finds a member of it running; end it yourself "
            f"(`kill -KILL -- -{process.pgid}`) or destroy the jail",
        )
    if outcome == "already_gone":
        return KillItem(
            kind,
            identity,
            KillOutcome.ALREADY_GONE,
            "process group had already ended before stop() ran",
        )
    return KillItem(kind, identity, KillOutcome.ENDED, "")


@dataclass(frozen=True, slots=True)
class LinkedSupervisor:
    """Starts, signals, waits for and stops the processes of one supervised jail, by request
    on `link`. Holds nothing but the jail's record and the link: what a request learned is
    in the link (`SupervisorLink.statuses`)."""

    jail: JailRecord
    link: SupervisorLink

    def start(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        io: IoPolicy,
        channel: Reservation | None = None,
    ) -> ProcessRecord:
        """Start `argv` in the jail (decision-191, decision-192): a process of the jail, in a
        session of its own, in `cwd`, with the environment the supervisor holds (the stack's own,
        scrubbed as it scrubs), stdin `/dev/null`, stdio per `io` in its records directory
        `<jail_dir>/procs/<id>/`, made before anything is asked; its `record.json` written before
        it runs a byte, naming `channel`'s socket as the one it binds.

        Raises:
            ReservationRefused: `channel` is not a socket the runtime would reserve in this jail,
                or a process the jail knows already binds it; raised before anything is made.
            TetherClosed: the jail is tethered and its tether has ended; raised before anything
                is made.
            WorkloadSpawnFailed: the supervisor could not start the argv (not found, a directory
                that is not there, ...), or could not tell who the process is; the process was
                ended, and nothing of it is left.
            SupervisorGone: the supervisor's socket is closed (the jail ended or was destroyed).
            SupervisorUnresponsive: the supervisor did not answer in time; the jail was destroyed.
            OSError: the records directory or the record could not be written (the process is
                ended first).
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
            # Nothing is left running (`_started` ended or never started it), so the directory
            # records nothing; left, it would hold the jail directory for the next `create`.
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
        """The two requests of a start, and the record between them (see the module docstring).

        Raises:
            WorkloadSpawnFailed, SupervisorGone, SupervisorUnresponsive, OSError: as `start`.
        """
        stdout_path = os.path.join(where, io.stdout_name)
        stderr_path = os.path.join(where, io.stderr_name)
        with (
            open(stdout_path, "wb") as stdout_f,
            open(stderr_path, "wb") as stderr_f,
            open(os.devnull, "rb") as stdin_f,
        ):
            try:
                spawned = self.link.request(
                    "start",
                    {
                        "process": process_id,
                        "argv": list(argv),
                        "cwd": cwd,
                        **self._shared(channel),
                    },
                    fds=(stdin_f.fileno(), stdout_f.fileno(), stderr_f.fileno()),
                    timeout=REQUEST_TIMEOUT_S,
                )
            except SupervisorRefused as refused:
                raise WorkloadSpawnFailed(
                    f"the supervisor could not start {argv[0]!r} in jail "
                    f"{self.jail.jail_id!r}: {refused.reason}"
                ) from refused
        try:
            record = self._recorded(
                spawned.fds,
                argv,
                channel,
                process_id=process_id,
                order=order,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        except BaseException:
            self._abort(process_id)
            raise
        try:
            self.link.request(
                "go", {"process": process_id, "proceed": True}, timeout=REQUEST_TIMEOUT_S
            )
        except SupervisorRefused as refused:
            raise WorkloadSpawnFailed(
                f"the supervisor could not start {argv[0]!r} in jail {self.jail.jail_id!r}: "
                f"{refused.reason}"
            ) from refused
        return record

    def _shared(self, channel: Reservation | None) -> dict[str, object]:
        """What a start tells the supervisor about the directories every process of the jail
        shares, when its processes have mount namespaces of their own (decision-195): the channel
        directory and the name of the socket this process will bind in it (`None` for one with
        no channel), and the scratch directory. Each process gets a directory of its own over
        each. Nothing without namespaces: the directories are shared, as they always were."""
        namespaces = self.jail.namespaces
        if namespaces is None or not namespaces.held:
            return {}
        name = (
            None if channel is None else os.path.basename(channel.bound_path).removesuffix(".sock")
        )
        return {
            "chan": {"dir": channel_dir_of(self.jail), "name": name},
            "scratch": scratch_dir(os.path.realpath(self.jail.jail_dir)),
        }

    def _recorded(
        self,
        pidfds: Sequence[int],
        argv: tuple[str, ...],
        channel: Reservation | None,
        *,
        process_id: str,
        order: int,
        stdout_path: str,
        stderr_path: str,
    ) -> ProcessRecord:
        """Who the process held at the supervisor's gate is, written down: its host pid from the
        pidfd the supervisor sent, the moment it started, its group; the record on disk.

        Raises:
            WorkloadSpawnFailed: no pidfd came, the kernel names no host pid for it, its start
                time can't be read, or it does not lead a group of its own.
            OSError: the record could not be written.
        """
        try:
            pid = host_pid_of(pidfds[0]) if pidfds else None
        finally:
            for fd in pidfds:
                os.close(fd)
        if pid is None:
            raise WorkloadSpawnFailed(
                f"the supervisor started {argv[0]!r} but the host cannot tell which process "
                "it is (no pidfd, or a kernel that reports none): a process the host cannot "
                "name is a process it cannot end, so it was not allowed to run"
            )
        stamp = _identity.start_stamp(pid)
        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = -1
        if stamp == _identity.UNKNOWN or pgid != pid:
            raise WorkloadSpawnFailed(
                f"the supervisor started {argv[0]!r} as host pid {pid}, but its start time "
                f"is {'unreadable' if stamp == _identity.UNKNOWN else 'readable'} and its "
                f"process group is {pgid}: it does not lead a group of its own, so it cannot "
                "be identified. It was not allowed to run"
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
            namespaces=self.jail.namespaces is not None and self.jail.namespaces.held,
        )
        _records.write(self.jail.jail_dir, record)
        return record

    def _abort(self, process_id: str) -> None:
        """Tell the supervisor not to run the process it holds at its gate. Best effort: if it
        cannot be told, the supervisor is gone or wedged, and the jail's end is the answer."""
        with contextlib.suppress(SupervisorGone, SupervisorRefused):
            self.link.request(
                "go", {"process": process_id, "proceed": False}, timeout=REQUEST_TIMEOUT_S
            )

    def signal(self, process: ProcessRecord, sig: Signals) -> bool:
        """Deliver `sig` to `process`'s group, inside the jail, by request. `True`: delivered;
        `False`: the process is gone or the jail's socket is.

        Raises:
            SupervisorUnresponsive: the supervisor did not answer in time; the jail was destroyed.
        """
        try:
            reply = self.link.request(
                "signal",
                {"process": process.id, "sig": int(sig)},
                timeout=REQUEST_TIMEOUT_S,
            )
        except SupervisorGone, SupervisorRefused:
            return False
        return reply.fields.get("delivered") is True

    def wait(self, process: ProcessRecord, timeout: float | None) -> int | None:
        """`process`'s exit status (`Popen.returncode`'s convention), or `None` while it still
        runs at the deadline (`timeout=None`: none). Asked of the supervisor in chunks of at most
        `WAIT_CHUNK_S`, each with a host-side deadline, so a wedged supervisor is found while a
        long wait is under way. A status once learned is kept by the link, so it is answered after
        the jail is gone.

        Raises:
            ExitStatusUnobservable: the jail's socket is closed and the process's status never
                reached this process, or the supervisor knows no such process.
            SupervisorUnresponsive: the supervisor did not answer in time; the jail was destroyed.
        """
        known = self.link.statuses.get(process.id)
        if known is not None:
            return known
        deadline = math.inf if timeout is None else time.monotonic() + timeout
        while True:
            chunk = min(WAIT_CHUNK_S, max(0.0, deadline - time.monotonic()))
            try:
                reply = self.link.request(
                    "wait",
                    {"process": process.id, "timeout": chunk},
                    timeout=chunk + SLACK_S,
                )
            except (SupervisorGone, SupervisorRefused) as error:
                known = self.link.statuses.get(process.id)
                if known is not None:
                    return known
                raise ExitStatusUnobservable(
                    f"process {process.id} (pid {process.pid}) of jail {self.jail.jail_id!r}: "
                    f"its status never reached this process ({error}); a supervised jail "
                    "answers for a process only while its supervisor does"
                ) from error
            status = reply.fields.get("status")
            if isinstance(status, int) and not isinstance(status, bool):
                self.link.statuses[process.id] = status
                held = self.jail.held
                _waiters.record_status(
                    process.pid,
                    status,
                    jail_id=self.jail.jail_id,
                    sensors=() if held is None else held.sensors,
                )
                return status
            if time.monotonic() >= deadline:
                return None

    def stop(self, process: ProcessRecord) -> KillReport:
        """End `process`'s group, inside the jail, by request (`SIGTERM`, a grace period,
        `SIGKILL`, a grace period; the supervisor verifies the group empty), and then check the
        group empty from the host: one item, `workload_group` for the jail's first process and
        `exec_sibling` for any other. Its record stays. A process that is PID 1 of a pid
        namespace of its own (decision-195) is sent what ends it where the kernel would drop
        a `SIGTERM`, and its namespace ends with it, a `setsid()` child included. Without
        namespaces a child in a session of its own is outside the group the request signals,
        and the jail's `destroy` is what ends it.

        Raises:
            SupervisorUnresponsive: the supervisor did not answer in time; the jail was destroyed.
        """
        first = self.jail.processes[0].id if self.jail.processes else None
        kind = "workload_group" if process.id == first else "exec_sibling"
        try:
            reply = self.link.request(
                "stop",
                {"process": process.id, "grace": STOP_GRACE_S},
                timeout=2 * STOP_GRACE_S + SLACK_S,
            )
        except (SupervisorGone, SupervisorRefused) as error:
            running = group_alive(process.pgid)
            return KillReport(
                items=(
                    KillItem(
                        kind,
                        str(process.pgid),
                        KillOutcome.FAILED if running else KillOutcome.ALREADY_GONE,
                        f"the supervisor could not be asked ({error}); the host "
                        + (
                            "still finds a member of the group running: destroy the jail"
                            if running
                            else "finds the group empty"
                        ),
                    ),
                )
            )
        outcome = str(reply.fields.get("outcome", "failed"))
        detail = str(reply.fields.get("detail", ""))
        return KillReport(
            items=(stop_item(kind, process, outcome, detail, gone=not group_alive(process.pgid)),)
        )
