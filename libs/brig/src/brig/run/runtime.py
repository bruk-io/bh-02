"""The runtime seam: `Runtime`, `Supervisor`, and the records they hand back.

SPEC.md section 3 (decision-178, decision-0001 step 1). A jail's instance is
the runtime's: how it is created, whether it is alive, how it is destroyed and
verified. Inside it, an `Supervisor` starts, signals, waits for and stops processes.
`HostRuntime` (`brig/run/host.py`) is brig's own; `brig.runtime.fake` is the
second implementation, pure, for tests.

**`create` holds no process, and every process is a `start`** (decision-181,
TASK-0079.25). `create` makes the instance; `Supervisor.start` is the only way
a process enters it, the first included, and each start has a record and an
exit record of its own (`brig/run/_records.py`). `Supervisor.start` takes no
channel yet: a channel per process needs the channel directory
(TASK-0079.05), and a parameter only `None` could be passed to would be a
raising stub (SPEC.md section 9). `Jail` and `Process` (`brig/run/jail.py`,
TASK-0079.26) are the embedder's side of it; `Handle` stays beside them until
TASK-0079.28.

`IoPolicy` and `ExitStatusUnobservable` live here because both sides of the
seam name them; `brig.run.launcher` and `brig.run.handle` re-export them, so
every earlier import resolves.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from signal import Signals
from typing import Protocol

from brig.core.runtime import Capability, RuntimeKind
from brig.mech import ArgvTransformer, EventSource
from brig.run._records import RESERVED_NAMES
from brig.run._records import ProcessRecord as ProcessRecord
from brig.run._tether import HeldTether
from brig.run.teardown import KillReport
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
    process's memory, so a rehydrated `Handle` -- the shape an embedder uses
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
    sensors, which the exit waiter asks about each process's ending; and the
    jail's hold on its tether, which every start's watcher reads. A record
    rehydrated in another process has none of it."""

    wrap: ArgvTransformer
    sensors: tuple[EventSource, ...] = ()
    tether: HeldTether | None = None


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
    stamp per pid. `held` is what the creating process holds in memory (`Held`),
    never compared or shown."""

    kind: RuntimeKind
    jail_id: str
    jail_dir: str
    cwd: str
    jail_env: frozendict[str, str]
    wrap_prefix: tuple[str, ...] | None
    processes: tuple[ProcessRecord, ...] = ()
    helper_pids: tuple[int, ...] = ()
    helper_stamps: tuple[str, ...] = ()
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

    def start(self, argv: Sequence[str], *, cwd: str, io: IoPolicy) -> ProcessRecord:
        """Start `argv` in the jail, under the jail's confinement, never a
        weaker one; raise rather than start it weaker. The only way a process
        enters a jail, the first included (decision-181)."""
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

    def destroy(self, jail: JailRecord) -> KillReport:
        """End everything the instance holds, verified, one item per thing
        (law 7)."""
        ...

    def supervisor(self, jail: JailRecord) -> Supervisor | None:
        """The supervisor inside `jail`, or `None` when it can only be destroyed."""
        ...
