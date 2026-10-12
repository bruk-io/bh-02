"""The runtime's vocabulary: which kind of runtime, what it can do, at which scope.

Pure data (SPEC.md section 3, decision-178). `run` defines the `Runtime` and
`Agent` protocols that use these; they live in `core` so that `stack` can read
a runtime's kind and grade it without importing `run` (decision-0001 step 2,
TASK-0079.03). Each enum holds only the members something in brig can produce:
more arrive with the runtimes that need them, the same posture as
`LaunchFeature`.
"""

from enum import Enum


class RuntimeKind(Enum):
    """Which runtime a jail's instance lives in.

    `HOST` is brig's own: host process groups, the exit wrapper, the tether
    (`brig/run/host.py`). A container runtime's kind arrives with it
    (decision-0001 step 5)."""

    HOST = "HOST"


class Capability(Enum):
    """What a runtime can do for the jails it creates.

    Decision-0001 makes `LaunchFeature` the runtime's capabilities. Until
    `Mechanism` names a runtime (step 2, TASK-0079.03) a stack still
    requires `LaunchFeature`s, so these members are `LaunchFeature`'s, value
    for value, and a runtime compares a jail's requirements by value."""

    NEW_PROCESS_GROUP = "NEW_PROCESS_GROUP"
    PTY = "PTY"
    DETACH = "DETACH"


class Scope(Enum):
    """The two scopes control is graded at (decision-0001, "Grades stay in
    the stack, at two scopes"): `JAIL`, whether the jail and everything in it
    can be ended without cooperation, which `Runtime.destroy` delivers; and
    `PROCESS`, whether one process in it can, which `Agent.stop` delivers.
    The grades themselves are step 2's (TASK-0079.03)."""

    JAIL = "JAIL"
    PROCESS = "PROCESS"
