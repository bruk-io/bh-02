"""The runtime seam: `Runtime`, `Agent`, and the records they hand back.

SPEC.md section 3 (decision-178, decision-0001 step 1). A jail's instance is
the runtime's: how it is created, whether it is alive, how it is destroyed and
verified. Inside it, an `Agent` starts, signals, waits for and stops processes.
`HostRuntime` (`brig/run/host.py`) is brig's own; `brig.runtime.fake` is the
second implementation, pure, for tests.

**Step 1's shape, and what changes later.** A bwrap jail cannot hold an
instance with nothing in it until its supervisor exists (decision-0001 step 4),
so `create` is launch-shaped: it takes the first process's argv and io, and
`JailRecord.first` is that process. `Agent.start` takes no channel yet: a
channel per process needs the channel directory (step 3, TASK-0079.05), and a
parameter only `None` could be passed to would be a raising stub (SPEC.md
section 9). Per-process records and exit records, and `Jail` and `Process` in
place of `Handle`, are step 3 (TASK-0079.04).

`IoPolicy` and `ExitStatusUnobservable` live here because both sides of the
seam name them; `brig.run.launcher` and `brig.run.handle` re-export them, so
every earlier import resolves.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from signal import Signals
from typing import Protocol

from brig.core.runtime import Capability, RuntimeKind
from brig.run.teardown import KillReport
from brig.stack import CompiledJail


@dataclass(frozen=True, slots=True)
class IoPolicy:
    """M2's only io policy: stdout/stderr to files under the jail
    directory (filenames configurable; content mode is not), stdin from
    `/dev/null` (fixed, not configurable in M2)."""

    stdout_name: str = "stdout.log"
    stderr_name: str = "stderr.log"


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
    `<jail_dir>/exit` (`brig/run/_exit_status.py`), which any process holding
    the handle can read, so a rehydrated handle now answers.

    What is left is exactly the case where **no wrapper ever wrote**:

    - the group was `SIGKILL`ed, which no process can survive long enough to
      record anything -- the killer holds the `KillReport`, which is that
      ending's record;
    - the jail directory has been swept, so the file that existed is gone;
    - the handle names a jail this launcher never wrapped.

    In none of those does a status exist to be read, which is why the answer
    is a refusal and not a number.
    """


class NoAgent(RuntimeError):
    """The jail's runtime has no agent inside it (`Runtime.agent` returned
    `None`), so nothing can be started in it or waited for through it: it can
    only be destroyed. `HostRuntime` always has one; a rehydrated jail whose
    agent was a live channel will not (decision-0001, "Records and
    rehydration")."""


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    """One process in a jail, as its runtime identifies it.

    `pid` and `start_time` are an identity, not a number: nothing acts on a
    pid whose current occupant started at another time, and an unknown stamp
    (`brig/run/_identity.py`'s `UNKNOWN`) is acted on by nothing
    (decision-155, decision-172). `argv` is what was spawned (the jail's
    wrap included); `stdout_path` and `stderr_path` are where `IoPolicy`
    sent its output."""

    pid: int
    pgid: int
    start_time: str
    argv: tuple[str, ...]
    stdout_path: str
    stderr_path: str


@dataclass(frozen=True, slots=True)
class JailRecord:
    """A jail's instance, as its runtime identifies it.

    `first` is the process `create` started with the instance (step 1's
    launch-shaped create). `wrap_prefix` and `jail_env` are what a later
    start needs to place a process under the same confinement: the compiled
    wrap's verified argv prefix (`None` when it is not a pure prefix, and a
    start is refused) and the jail's own env overlay. `helper_pids` and
    `helper_stamps` are the `JAIL_LIFETIME` helpers `destroy` must end too,
    one stamp per pid."""

    kind: RuntimeKind
    jail_id: str
    jail_dir: str
    cwd: str
    jail_env: frozendict[str, str]
    wrap_prefix: tuple[str, ...] | None
    first: ProcessRecord
    helper_pids: tuple[int, ...] = ()
    helper_stamps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Raises:
        ValueError: `helper_stamps` does not have one entry per helper pid."""
        if len(self.helper_stamps) != len(self.helper_pids):
            raise ValueError(
                "JailRecord: helper_stamps must have one entry per helper pid, got "
                f"{len(self.helper_stamps)} stamp(s) for {len(self.helper_pids)} pid(s)"
            )


class Agent(Protocol):
    """Inside a jail's instance: what starts, signals, waits for and stops
    its processes. Bound to one `JailRecord` (`Runtime.agent`)."""

    def start(self, argv: Sequence[str], *, cwd: str, io: IoPolicy) -> ProcessRecord:
        """Start `argv` in the jail, under the same confinement as its first
        process, never a weaker one; raise rather than start it weaker."""
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
        argv: Sequence[str],
        cwd: str,
        io: IoPolicy,
        jail_id: str,
        jail_dir: str,
        tether: int | None,
    ) -> JailRecord:
        """Create the instance and start its first process, `argv`
        (launch-shaped until decision-0001 step 4). `tether` is the read end
        of a pipe whose write end the caller keeps; when every write end is
        closed the jail ends. Refuses a jail whose requirements exceed
        `capabilities`."""
        ...

    def alive(self, jail: JailRecord) -> bool:
        """Whether the instance still runs (for `HostRuntime`, its first
        process, by identity)."""
        ...

    def destroy(self, jail: JailRecord) -> KillReport:
        """End everything the instance holds, verified, one item per thing
        (law 7)."""
        ...

    def agent(self, jail: JailRecord) -> Agent | None:
        """The agent inside `jail`, or `None` when it can only be destroyed."""
        ...
