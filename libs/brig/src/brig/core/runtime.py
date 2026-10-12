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
    (`brig/run/host.py`). A container runtime's kind arrives with it
    (decision-0001 step 5)."""

    HOST = "HOST"


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
        case _ as unreachable:
            assert_never(unreachable)
