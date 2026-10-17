"""The runtime seam: `Runtime`, `Supervisor`, and the records they hand back.

SPEC.md section 3 (decision-178, decision-0001 step 1). A jail's instance is
the runtime's: how it is created, whether it is alive, how it is destroyed and
verified. Inside it, an `Supervisor` starts, signals, waits for and stops processes.
`HostRuntime` (`brig/run/host.py`) is brig's own; `brig.runtime.fake` is the
second implementation, pure, for tests.

**`create` holds no process, and every process is a `start`** (decision-181,
TASK-0079.25). `create` makes the instance; `Supervisor.start` is the only way
a process enters it, the first included, and each start has a record and an
exit record of its own (`brig/run/_records.py`). `Jail` and `Process`
(`brig/run/jail.py`, TASK-0079.26) are the embedder's side of it.

**Reserve, then start** (decision-184, SPEC.md section 10). The runtime owns
one channel directory per jail, `<jail_dir>/chan`; `Runtime.reserve` names a
socket there for a declared channel, the embedder puts its in-jail path in the
argv it starts, and `Supervisor.start(..., channel=reservation)` binds the
process to it, refusing a reservation that is not its own
(`reservation_refusal`). The runtime resolves a process's channel to the
host path to dial (`Runtime.endpoint`) and says whether it accepts a
connection (`Runtime.ready`), through the one verified dial
(`Runtime.connect`, decision-185).

`IoPolicy`, `ExitStatusUnobservable`, `NoSupervisor`, `Reservation` and
`ReservationRefused` live here because both sides of the seam name them;
`brig.run` re-exports them.
"""

import os
import re
import socket
from collections.abc import Sequence
from dataclasses import dataclass, field
from signal import Signals
from typing import Final, Protocol

from brig.core.runtime import Capability, RuntimeKind, channel_dir
from brig.mech import ArgvTransformer, EventSource
from brig.run import _records
from brig.run._records import RESERVED_NAMES
from brig.run._records import ProcessRecord as ProcessRecord
from brig.run._supervisor_link import SupervisorLink
from brig.run._tether import HeldTether
from brig.run.teardown import DEFAULT_GRACE_S, KillReport
from brig.stack import CompiledJail


@dataclass(frozen=True, slots=True)
class IoPolicy:
    """M2's only io policy: stdout/stderr to files under the jail
    directory (filenames configurable; content mode is not), stdin from
    `/dev/null` (fixed, not configurable in M2)."""

    stdout_name: str = "stdout.log"
    stderr_name: str = "stderr.log"

    def __post_init__(self) -> None:
        """Raises:
        ValueError: a name is not one plain file name, is one of the records'
            own (`record.json`, `exit`, their `.partial`), or both are the same.
        """
        for name in (self.stdout_name, self.stderr_name):
            if not name or "/" in name or name in (".", "..") or name in RESERVED_NAMES:
                raise ValueError(
                    f"IoPolicy: {name!r} is not a stdio file name a process can have: it must "
                    "be one plain file name, and not one of its records' own "
                    f"({', '.join(sorted(RESERVED_NAMES))})"
                )
        if self.stdout_name == self.stderr_name:
            raise ValueError(
                f"IoPolicy: stdout and stderr are both {self.stdout_name!r}; name two files"
            )


class ExitStatusUnobservable(RuntimeError):
    """The workload is gone and NOTHING recorded how it ended.

    Raised rather than returning a status, because every stand-in is a lie in
    the dangerous direction. `0` reads as a clean exit -- which in a denial
    test means the jail failed to deny, and in an allowed-case control means
    a write was never observed at all. Five integration helpers made exactly
    that substitution (`except ChildProcessError: return 0`) before the exit
    status was recorded at all.

    **What this no longer means (decision-156, 2026-09-08).** It used to mean
    "you are not the launching process": the status lived only in that
    process's memory, so a rehydrated jail -- the shape an embedder uses
    to clean up after a runtime that died holding a jail -- got this refusal
    every time. It does not any more. The exit wrapper writes the status to
    the process's own exit record (`brig/run/_exit_status.py`; since
    decision-181 `<jail_dir>/procs/<id>/exit`, siblings included), which any
    process holding the handle can read, so a rehydrated handle now answers.

    What is left is exactly the case where **no wrapper ever wrote**:

    - the group was `SIGKILL`ed, which no process can survive long enough to
      record anything -- the killer holds the `KillReport`, which is that
      ending's record;
    - the jail directory has been swept, so the file that existed is gone;
    - the handle names a jail this launcher never wrapped.

    In none of those does a status exist to be read, which is why the answer
    is a refusal and not a number.
    """


@dataclass(frozen=True, slots=True)
class Reservation:
    """A socket reserved in a jail's channel directory for one start
    (decision-184): `channel`, the declared channel it is for; `bound_path`,
    where the process binds it inside the jail, which the embedder puts in the
    argv it starts; `endpoint`, the host path the embedder dials once the
    process listens. The same path for `HostRuntime`; a runtime that shares no
    socket with the host hands out a relay's."""

    channel: str
    bound_path: str
    endpoint: str


class ReservationRefused(ValueError):
    """`start(..., channel=reservation)` was given a reservation that is not
    its runtime's own for this jail (decision-184): its path is not directly
    in the jail's channel directory under a name the runtime reserves, its
    endpoint is not the one the runtime would hand out for it, or a process
    the jail knows already binds it. Nothing was made or spawned. Reserve
    with `jail.channel(name)`, once per start."""


#: The name a reserved socket takes in the channel directory: 16 lowercase
#: hex characters from `secrets`, and `.sock`.
_SOCKET_NAME: Final = re.compile(r"[0-9a-f]{16}\.sock")


def reservation_refusal(
    reservation: Reservation, *, chan: str, endpoint: str, taken: frozenset[str]
) -> str | None:
    """Why `reservation` is not one its runtime would have made in the channel
    directory `chan`, with `endpoint` the host path the runtime resolves its
    `bound_path` to and `taken` the bound paths the jail's known processes
    hold; `None` when it is. Pure and lexical: a path with `..` in it, or a
    link's name, is not directly in `chan`."""
    directory, name = os.path.split(reservation.bound_path)
    if directory != chan:
        return (
            f"its path {reservation.bound_path!r} is not directly in the jail's channel "
            f"directory {chan!r}"
        )
    if _SOCKET_NAME.fullmatch(name) is None:
        return f"its socket name {name!r} is not one the runtime reserves (16 hex and .sock)"
    if reservation.endpoint != endpoint:
        return (
            f"its endpoint {reservation.endpoint!r} is not the host path the runtime "
            f"dials for it, {endpoint!r}"
        )
    if reservation.bound_path in taken:
        return f"a process of the jail already binds {reservation.bound_path!r}"
    return None


def reserved_socket(chan: str, token: str) -> str:
    """The path of the socket `token` (16 lowercase hex) names in the channel
    directory `chan`. Pure."""
    return f"{chan}/{token}.sock"


def socket_endpoint(bound_path: str, *, namespaces: bool) -> str:
    """The host path to dial the socket a process binds at `bound_path` in the channel
    directory (decision-196). The same path where the process shares the directory with the
    jail's others; where it has a mount namespace of its own (decision-195) it sees a
    directory of its own, named for the socket, over the channel directory, so the socket it
    makes at `<chan>/<token>.sock` is at `<chan>/<token>/<token>.sock` for the host. Pure."""
    if not namespaces:
        return bound_path
    directory, name = os.path.split(bound_path)
    return f"{directory}/{name.removesuffix('.sock')}/{name}"


def refuse_foreign_reservation(jail: JailRecord, channel: Reservation) -> None:
    """Refuse a `channel` that is not a socket the runtime would reserve in `jail`'s channel
    directory, or that a process the jail knows (in memory or under `procs/`) already binds
    (decision-184). Reads the filesystem for the records. Nothing is made or spawned.

    Raises:
        ReservationRefused: `channel` is not this jail's, saying why.
    """
    taken = frozenset(
        process.bound_path
        for process in (*jail.processes, *_records.scan(jail.jail_dir).records)
        if process.bound_path is not None
    )
    reason = reservation_refusal(
        channel,
        chan=channel_dir_of(jail),
        endpoint=socket_endpoint(
            channel.bound_path, namespaces=jail.namespaces is not None and jail.namespaces.held
        ),
        taken=taken,
    )
    if reason is not None:
        raise ReservationRefused(
            f"start: the reservation for channel {channel.channel!r} is not this "
            f"jail's: {reason}. Reserve one with jail.channel({channel.channel!r}) "
            "for each start"
        )


def channel_dir_of(jail: JailRecord) -> str:
    """`jail`'s channel directory as a process inside it sees it: under the
    jail directory resolved, as every mechanism grants it
    (`CompileCtx.channel_dir`, decision-184). Reads the filesystem to
    resolve."""
    return channel_dir(os.path.realpath(jail.jail_dir))


class NoSupervisor(RuntimeError):
    """The jail's runtime has no supervisor inside it (`Runtime.supervisor` returned
    `None`), so nothing can be started in it or waited for through it: it can
    only be destroyed. `HostRuntime` always has one; a rehydrated jail whose
    supervisor was a live channel will not (decision-0001, "Records and
    rehydration")."""


@dataclass(frozen=True, slots=True)
class Held:
    """What the process that created a jail holds of it in memory, and nothing
    serialized does (decision-181): the compiled `wrap`, so each start checks
    that `wrap` of its own argv is the jail's prefix followed by the argv; the
    sensors, which the exit waiter asks about each process's ending; the
    jail's hold on its tether, which every start's watcher reads; and, in a
    supervised jail, the link to its supervisor (decision-191), the only way
    anything starts in it: a socket cannot cross `to_dict`, so a record
    rehydrated in another process has none of it, and no supervisor."""

    wrap: ArgvTransformer
    sensors: tuple[EventSource, ...] = ()
    tether: HeldTether | None = None
    link: SupervisorLink | None = None


@dataclass(frozen=True, slots=True)
class SupervisorRecord:
    """The instance of a supervised jail, as `destroy` and `alive` identify it
    (decision-192): the host process that leads the group holding brig's
    supervisor, the jail's PID 1, as `pid` and the moment it started
    (`start_time`, brig/run/_identity.py): an identity, not a number. Never
    a pid the jail named: nothing a jail says is a kill target."""

    pid: int
    start_time: str


@dataclass(frozen=True, slots=True)
class ProcessNamespaces:
    """Whether each process a supervised jail starts has namespaces of its own (decision-195),
    as its supervisor found out before it said it was ready: `held`, and when not, `reason`, the
    line the supervisor gave. What a `Process` reads its `namespaces` and `control` from, and
    the runtime the host paths of the sockets it reserves."""

    held: bool
    reason: str


@dataclass(frozen=True, slots=True)
class JailRecord:
    """A jail's instance, as its runtime identifies it.

    `wrap_prefix` and `jail_env` are what a start needs to place a process
    under the jail's confinement: the compiled wrap's verified argv prefix
    (`None` when it is not a pure prefix, and every start is refused) and the
    jail's own env overlay. `processes` are the processes the holder knows, in
    start order; a runtime finds later ones in its own records (for
    `HostRuntime`, under `<jail_dir>/procs`). `helper_pids` and
    `helper_stamps` are the `JAIL_LIFETIME` helpers `destroy` must end too, one
    stamp per pid. `supervisor` is the instance of a supervised jail
    (decision-192), `None` for a jail whose processes are started by the
    host. `namespaces` is what its supervisor found about the namespaces of
    its processes (decision-195), known to the process that created the jail
    and no other, `None` without a supervisor. `held` is what the creating
    process holds in memory (`Held`), never compared or shown."""

    kind: RuntimeKind
    jail_id: str
    jail_dir: str
    cwd: str
    jail_env: frozendict[str, str]
    wrap_prefix: tuple[str, ...] | None
    processes: tuple[ProcessRecord, ...] = ()
    helper_pids: tuple[int, ...] = ()
    helper_stamps: tuple[str, ...] = ()
    supervisor: SupervisorRecord | None = None
    namespaces: ProcessNamespaces | None = None
    held: Held | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Raises:
        ValueError: `helper_stamps` does not have one entry per helper pid."""
        if len(self.helper_stamps) != len(self.helper_pids):
            raise ValueError(
                "JailRecord: helper_stamps must have one entry per helper pid, got "
                f"{len(self.helper_stamps)} stamp(s) for {len(self.helper_pids)} pid(s)"
            )


class Supervisor(Protocol):
    """Inside a jail's instance: what starts, signals, waits for and stops
    its processes. Bound to one `JailRecord` (`Runtime.supervisor`)."""

    def start(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        io: IoPolicy,
        channel: Reservation | None = None,
    ) -> ProcessRecord:
        """Start `argv` in the jail, under the jail's confinement, never a
        weaker one; raise rather than start it weaker. The only way a process
        enters a jail, the first included (decision-181). `channel` is the
        socket reserved for it (`Runtime.reserve`), recorded on the process;
        one that is not this runtime's own for this jail raises
        `ReservationRefused` before anything is made (decision-184)."""
        ...

    def signal(self, process: ProcessRecord, sig: Signals) -> bool:
        """Deliver `sig` to `process` and everything it started that has not
        left its group. `True` means delivered, not that anything stopped;
        `False` means not delivered (gone, recycled, not permitted)."""
        ...

    def wait(self, process: ProcessRecord, timeout: float | None) -> int | None:
        """`process`'s exit status (`Popen.returncode`'s convention), or
        `None` if it still runs at the deadline (`timeout=None`: no
        deadline). Never invents a status: raises `ExitStatusUnobservable`
        when it is gone and nothing recorded how it ended."""
        ...

    def stop(self, process: ProcessRecord) -> KillReport:
        """End `process` without its cooperation, verified, one item per
        thing ended (SPEC.md section 9's ladder)."""
        ...


class Runtime(Protocol):
    """A jail's instance: created, observed and ended without the jail's
    cooperation (SPEC.md section 3, law 7)."""

    @property
    def kind(self) -> RuntimeKind: ...

    @property
    def capabilities(self) -> frozenset[Capability]: ...

    def create(
        self,
        jail: CompiledJail,
        *,
        cwd: str,
        jail_id: str,
        jail_dir: str,
        tether: int | None,
    ) -> JailRecord:
        """Create the instance, with no process in it (decision-181): every
        process is a `Supervisor.start`. `tether` is the read end of a pipe
        whose write end the caller keeps; when every write end is closed, every
        process the jail started ends. Refuses a jail whose requirements exceed
        `capabilities`."""
        ...

    def alive(self, jail: JailRecord) -> bool:
        """Whether the instance still runs: any process it started, or any
        helper (for `HostRuntime`, each by identity)."""
        ...

    def processes(self, jail: JailRecord) -> tuple[ProcessRecord, ...]:
        """Every process of `jail`, in start order: the ones `jail` holds, by
        the record it holds, then every other one the runtime finds (for
        `HostRuntime`, under `<jail_dir>/procs`). A copy the runtime finds of
        a held process is never used in its place (decision-181)."""
        ...

    def tethered(self, jail: JailRecord) -> bool | None:
        """Whether `create` tethered `jail`, as the runtime recorded it apart
        from any dict (for `HostRuntime`, `<jail_dir>/jail.json`); `None` when
        it can't tell. A rehydrated `Jail` starts only when this and its dict
        both say untethered (decision-181, TASK-0079.26)."""
        ...

    def process_alive(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """Whether `process` of `jail` still runs: its leader holds its
        identity (for `HostRuntime`, decision-155; a zombie is gone,
        decision-171)."""
        ...

    def destroy(self, jail: JailRecord, *, grace: float = DEFAULT_GRACE_S) -> KillReport:
        """End everything the instance holds, verified, one item per thing
        (law 7). `grace` is how long a process has after `SIGTERM`; 0 gives
        none (decision-193): `SIGKILL` at once, the instance first where there
        is one."""
        ...

    def supervisor(self, jail: JailRecord) -> Supervisor | None:
        """The supervisor inside `jail`, or `None` when it can only be destroyed."""
        ...

    def reserve(self, jail: JailRecord, channel: str) -> Reservation:
        """A fresh socket in `jail`'s channel directory for `channel`, which
        the caller has checked the jail declares (decision-184). Makes
        nothing: the process binds it."""
        ...

    def endpoint(self, jail: JailRecord, process: ProcessRecord) -> str | None:
        """The host path to dial `process`'s channel at, or `None` when it was
        started with none (decision-184)."""
        ...

    def ready(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """Whether `process`'s channel accepts a connection now: a connect
        that succeeds, never a path that exists (SPEC.md section 10). `False`
        for a process with no channel. It is `connect`, closed at once
        (decision-185): a refusal raises `EndpointRefused`, never reads as "not
        yet"."""
        ...

    def connect(self, jail: JailRecord, process: ProcessRecord) -> socket.socket:
        """A connected socket to `process`'s channel, once the runtime has
        checked that what answers is that process's own listener
        (decision-185): the one dial of a reserved channel, readiness included.

        Raises:
            ValueError: `process` was started with no channel.
            EndpointRefused: what is at its socket is not its own listener.
            OSError: nothing listens there yet.
        """
        ...
