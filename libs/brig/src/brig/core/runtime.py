"""The runtime's vocabulary: which kind of runtime, what it can do, at which scope.

Pure data (SPEC.md section 3, decision-178). `run` defines the `Runtime` and
`Supervisor` protocols that use these; they live in `core` so that `mech` can name
the runtime a mechanism needs and `stack` can grade a runtime's axes without
importing `run` (SPEC.md sections 6 and 7, decision-179). Each enum holds only
the members something in brig can produce: more arrive with the runtimes that
need them.
"""

from collections.abc import Mapping
from enum import Enum
from typing import Final, assert_never

from brig.core.grades import Axis, Grade
from brig.core.report import Graded


class RuntimeKind(Enum):
    """Which runtime a jail's instance lives in.

    `HOST` is brig's own: host process groups, the exit wrapper, the tether
    (`brig/run/host.py`). `FAKE` is `brig.runtime.fake`'s, a test double
    (decision-181): no mechanism names it, so no compiled jail has it, and a
    fake's records say `FAKE` so they never reach a real runtime. A container
    runtime's kind arrives with it (decision-0001 step 5)."""

    HOST = "HOST"
    FAKE = "FAKE"


class Capability(Enum):
    """What a runtime can do for the jails it creates, and what a mechanism's
    `Step.requires` names (decision-179, which retired `LaunchFeature` for
    this, the same three members by value)."""

    NEW_PROCESS_GROUP = "NEW_PROCESS_GROUP"
    PTY = "PTY"
    DETACH = "DETACH"


class Scope(Enum):
    """The two scopes control is graded at (decision-0001, "Grades stay in
    the stack, at two scopes"): `JAIL`, whether the jail and everything in it
    can be ended without cooperation, which `Runtime.destroy` delivers; and
    `PROCESS`, whether one process in it can, which `Supervisor.stop` delivers.
    A report's `control` axis is the `JAIL` scope (`runtime_grades`); the
    `PROCESS` scope travels on each process (decision-0001 step 3)."""

    JAIL = "JAIL"
    PROCESS = "PROCESS"


#: The two axes a runtime grades rather than a mechanism (SPEC.md section 7,
#: decision-179): `control` at the jail scope, and `channel_exclusivity`.
RUNTIME_AXES: Final[frozenset[Axis]] = frozenset({Axis.CONTROL, Axis.CHANNEL_EXCLUSIVITY})

_HOST_CONTROL: Final[str] = (
    "graded by the HOST runtime: a jail is ended by signalling the process "
    "groups brig started and verifying them gone, and nothing yet proves that "
    "reaches every process in the jail (a setsid() child leaves its group). "
    "No grade above unenforced until a control battery driven from the host "
    "plants survivors (decision-0001, TASK-0079.08)"
)

_FAKE_DETAIL: Final[str] = (
    "graded by the FAKE runtime, a test double (brig.runtime.fake): it starts, "
    "signals and ends nothing, so it enforces nothing"
)

_HOST_CHANNEL_EXCLUSIVITY: Final[str] = (
    "graded by the HOST runtime: nothing establishes that the declared "
    "channels and the enumerated shared media are the only ways in or out "
    "of the jail"
)


def runtime_grades(kind: RuntimeKind) -> Mapping[Axis, Graded]:
    """The static grades of `kind` on each of `RUNTIME_AXES`.

    Static per kind, so `Stack.compile` reads them and checks a floor on
    them at compile (decision-0001, "Grades stay in the stack, at two
    scopes"). Never above what a battery proves: `HOST` grades both axes
    `unenforced`, as every report did before decision-179."""
    match kind:
        case RuntimeKind.HOST:
            return {
                Axis.CONTROL: Graded(Grade.UNENFORCED, _HOST_CONTROL),
                Axis.CHANNEL_EXCLUSIVITY: Graded(Grade.UNENFORCED, _HOST_CHANNEL_EXCLUSIVITY),
            }
        case RuntimeKind.FAKE:
            return {
                Axis.CONTROL: Graded(Grade.UNENFORCED, _FAKE_DETAIL),
                Axis.CHANNEL_EXCLUSIVITY: Graded(Grade.UNENFORCED, _FAKE_DETAIL),
            }
        case _ as unreachable:
            assert_never(unreachable)


#: `<jail_dir>/procs`: one directory per process a `HOST` jail starts, holding
#: its record and exit record (decision-181). Kill authority, so no grant may
#: reach it (`refuse_channel_on_records`).
PROCS_DIRNAME: Final = "procs"

#: `<jail_dir>/chan`: the runtime's channel directory, one per jail
#: (decision-184). A name brig keeps beside `tmp`, `procs` and `jail.json`,
#: never a `Spec` path: each start's socket is reserved there.
CHANNELS_DIRNAME: Final = "chan"


def channel_dir(jail_dir: str) -> str:
    """The channel directory of the jail in `jail_dir` (decision-184). Pure:
    lexical, so a caller that needs it resolved passes a resolved `jail_dir`."""
    return f"{jail_dir.rstrip('/')}/{CHANNELS_DIRNAME}"


class ChannelOnRecords(ValueError):
    """A LISTEN channel's endpoint is at or under brig's records
    (`<jail_dir>/procs`), decision-181. (`<jail_dir>/execs` too, until
    decision-183 deleted the code that wrote it.)

    bwrap's grant for a socket is its endpoint's directory, bound read-write, so
    there it would let the jail write the records teardown signals by; seatbelt's
    grant is the socket's own path, and a socket made at a record's path is a
    record the host can't read. Every mechanism that compiles a LISTEN channel
    raises this, naming the endpoint and the records directory, and saying to put
    the endpoint in a subdirectory of its own or outside the jail directory."""


def _at_or_under(path: str, root: str) -> bool:
    """Whether `path` is `root` or lies under it, as strings (no filesystem read)."""
    return path == root or path.startswith(root.rstrip("/") + "/")


def refuse_channel_on_records(
    *, name: str, endpoint: str, resolved_endpoint: str, jail_dir: str
) -> None:
    """Refuse a LISTEN endpoint at or under the records of the jail in `jail_dir`
    (the resolved jail directory), testing the endpoint as declared and as
    resolved, as decision-174's refusal tests both parents (TASK-0079.17). Pure.

    Raises:
        ChannelOnRecords: either form of the endpoint is at or under
            `<jail_dir>/procs`.
    """
    records = f"{jail_dir.rstrip('/')}/{PROCS_DIRNAME}"
    if _at_or_under(endpoint, records) or _at_or_under(resolved_endpoint, records):
        leaf = endpoint.rsplit("/", 1)[-1]
        raise ChannelOnRecords(
            f"LISTEN channel {name!r} endpoint {endpoint!r} (resolved "
            f"{resolved_endpoint!r}) is at or under {records!r}, where brig keeps the "
            "records teardown signals by: a grant there would let the jail write them, "
            "or make one the host can't read. Put the endpoint in a subdirectory of "
            f"its own, for example {jail_dir.rstrip('/')}/chan/{leaf}, or outside the "
            "jail directory"
        )
