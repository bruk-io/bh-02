"""The runtime's vocabulary: which kind of runtime, what it can do, at which scope.

Pure data (SPEC.md section 3, decision-178). `run` defines the `Runtime` and
`Supervisor` protocols that use these; they live in `core` so that `mech` can name
the runtime a mechanism needs and `stack` can grade a runtime's axes without
importing `run` (SPEC.md sections 6 and 7, decision-179). Each enum holds only
the members something in brig can produce: more arrive with the runtimes that
need them.

`SupervisorPlan` is what a mechanism hands the runtime when its jail runs brig's
own supervisor as PID 1 (SPEC.md section 6, decision-190): the interpreter the
supervisor runs under inside the jail, and where its source is bound.

`ContainerPlan` is what the `oci` mechanism hands its runtime (SPEC.md section 6,
decision-202): the flags of `docker create`, the image and command, and the environment
the runtime writes to the env file those flags name. It renders that file's text, purely.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final, assert_never

from brig.core.grades import Axis, Grade
from brig.core.report import Graded


class RuntimeKind(Enum):
    """Which runtime a jail's instance lives in.

    `HOST` is brig's own: host process groups, the exit wrapper, the tether
    (`brig/run/host.py`). `FAKE` is `brig.runtime.fake`'s, a test double
    (decision-181): no mechanism names it, so no compiled jail has it, and a
    fake's records say `FAKE` so they never reach a real runtime. `OCI` is a
    container, created and ended through the Docker daemon (`brig/runtime/oci.py`,
    decision-202)."""

    HOST = "HOST"
    OCI = "OCI"
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


#: Where a supervised jail's supervisor program is bound inside it (decision-190): a file at
#: the root of the jail's own tmpfs, which `bwrap` delivers read-only from the host's memory
#: (`--ro-bind-data`), so nothing on the host's disk is its source and nothing the jail can
#: write is.
SUPERVISOR_SOURCE_PATH: Final = "/.brig-supervisor.py"


@dataclass(frozen=True, slots=True)
class SupervisorPlan:
    """A jail whose PID 1 is brig's supervisor (SPEC.md section 6, decision-190).

    `interpreter` is the absolute path, inside the jail, of the Python the supervisor
    runs under (`python -I`); the mechanism has checked that the `Spec` mounts it. The
    program itself is `run`'s, and it is bound at `SUPERVISOR_SOURCE_PATH`."""

    interpreter: str

    def __post_init__(self) -> None:
        """Raises:
        ValueError: `interpreter` is not an absolute path."""
        if not self.interpreter.startswith("/"):
            raise ValueError(
                f"SupervisorPlan.interpreter must be an absolute path inside the jail, got "
                f"{self.interpreter!r}"
            )


#: A name an env file can carry: `NAME=value` is one line of Docker's `--env-file`, and a line
#: with no `=` would forward a variable of the Docker CLI's own environment (decision-202).
_ENV_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class EnvNotRepresentable(ValueError):
    """A variable cannot be written to a container's env file as one `NAME=value` line
    (SPEC.md section 6, decision-202): its name is not `[A-Za-z_][A-Za-z0-9_]*`, or its value holds
    a newline, a carriage return or a NUL. Names the variable, never its value."""


def env_refusal(name: str, value: str | None = None) -> str | None:
    """Why `name` (and `value`, when given) cannot be one line of an env file, or `None`.
    The reason names the variable and never the value. Pure."""
    if _ENV_NAME.fullmatch(name) is None:
        return f"the name {name!r} is not [A-Za-z_][A-Za-z0-9_]*"
    if value is not None and any(char in value for char in "\n\r\0"):
        return f"the value of {name} holds a newline, a carriage return or a NUL"
    return None


@dataclass(frozen=True, slots=True)
class ContainerPlan:
    """A jail whose instance is a container (SPEC.md section 6, decision-202): what the `oci`
    mechanism hands its runtime. `flags` are everything `docker create` takes between its own
    verb and the image, rendered purely from the `Spec`; `image` and `command` follow them (the
    command is the container's idle process until a supervisor replaces it, TASK-0079.10).

    `env_file` is the path `flags` name with `--env-file`, which the runtime writes (mode 0600,
    removed once `docker create` returns) from `env_file_text`: the names of `env_forward`, from
    the environment of the process that creates the jail, and the pairs of `env_set`. The
    environment is a file and never `-e K=V` because argv is visible in `ps` (law 9)."""

    image: str
    flags: tuple[str, ...]
    command: tuple[str, ...]
    env_file: str
    env_forward: tuple[str, ...]
    env_set: tuple[tuple[str, str], ...]

    def env_file_text(self, environ: Mapping[str, str]) -> str:
        """The env file's text for a creating process whose environment is `environ`: a forwarded
        name when `environ` has it set and non-empty (as `env_scrub` forwards, decision-066), then
        each `env_set` pair, which overrides a forwarded name. One `NAME=value` per line, the value
        verbatim (Docker's file takes it so). Pure.

        Raises:
            EnvNotRepresentable: a name or a value cannot be a line (the message names the
                variable, never its value).
        """
        lines: dict[str, str] = {}
        for name in self.env_forward:
            value = environ.get(name)
            if value:
                lines[name] = value
        lines.update(self.env_set)
        for name, value in lines.items():
            reason = env_refusal(name, value)
            if reason is not None:
                raise EnvNotRepresentable(
                    f"cannot write {name} to the container's env file: {reason}"
                )
        return "".join(f"{name}={value}\n" for name, value in lines.items())


#: The two axes a runtime grades rather than a mechanism (SPEC.md section 7,
#: decision-179): `control` at the jail scope, and `channel_exclusivity`.
RUNTIME_AXES: Final[frozenset[Axis]] = frozenset({Axis.CONTROL, Axis.CHANNEL_EXCLUSIVITY})

_HOST_CONTROL_UNSUPERVISED: Final[str] = (
    "graded by the HOST runtime for a jail with no supervisor: it is ended by signalling the "
    "process groups brig started and verifying them gone, and a child that leaves its group "
    "(setsid()) is outside them. The control battery (decision-201, "
    "tests/e2e/test_control_battery.py) plants its survivors in a supervised bwrap jail only, "
    "and has not been run against this jail type (Seatbelt needs macOS), so its control is "
    "unproven, not failed. No grade above unenforced"
)

_HOST_CONTROL_SUPERVISED: Final[str] = (
    "graded by the HOST runtime for a jail whose PID 1 is brig's supervisor: destroy() ends "
    "the jail's pid namespace from the host, which the kernel ends with its PID 1, and "
    "verifies it. Proved from the host by the control battery (decision-201, "
    "tests/e2e/test_control_battery.py): a setsid() child, a process that ignores SIGTERM and "
    "a SIGSTOPped supervisor are each planted beside a plain child the same destroy() ends, "
    "and destroy() ends all of them, whether the jail's processes have namespaces of their "
    "own or not. This is the jail scope; a process's own is Process.control"
)

_OCI_CONTROL: Final[str] = (
    "graded by the OCI runtime for a container jail: destroy() is `docker rm -f` through the "
    "daemon the runtime object names, which SIGKILLs the container's init and with it its pid "
    "namespace, and then asks `docker inspect` whether the container is gone. Proved from the "
    "host by the control battery (decision-202, tests/integration/test_oci_control.py): a "
    "setsid() child, a process that ignores SIGTERM and a SIGSTOPped init are each planted (by "
    "`docker exec`, the test's own door) beside a plain child the same destroy() ends, and "
    "destroy() ends all of them. This is the jail scope; nothing is started in a container "
    "through brig yet, so there is no process scope to grade (TASK-0079.10)"
)

_OCI_CHANNEL_EXCLUSIVITY: Final[str] = (
    "graded by the OCI runtime: nothing establishes that the declared channels and the "
    "enumerated shared media are the only ways in or out of the container, and a Spec that "
    "declares a channel is refused until the channel directory exists (TASK-0079.10)"
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


def runtime_grades(kind: RuntimeKind, *, supervised: bool) -> Mapping[Axis, Graded]:
    """The static grades of `kind` on each of `RUNTIME_AXES`, for a jail with a supervisor
    (`supervised`, bwrap's) or without one.

    Static per jail type, so `Stack.compile` reads them and checks a floor on them at compile
    (decision-0001, "Grades stay in the stack, at two scopes"). Never above what the control
    battery proves (decision-201, law 10): `HOST` grades `control` `enforced` for a supervised
    jail, whose `destroy` the battery ended every planted survivor with, and `unenforced` for
    one with no supervisor, which it has not been run against. `OCI` grades it `enforced`
    whether or not a supervisor runs in the container: the battery for a container
    (decision-202) plants its survivors through `docker exec` and ends them with `destroy`.
    `channel_exclusivity` is `unenforced` for every kind, as every report said before
    decision-179."""
    match kind:
        case RuntimeKind.HOST:
            control = (
                Graded(Grade.ENFORCED, _HOST_CONTROL_SUPERVISED)
                if supervised
                else Graded(Grade.UNENFORCED, _HOST_CONTROL_UNSUPERVISED)
            )
            return {
                Axis.CONTROL: control,
                Axis.CHANNEL_EXCLUSIVITY: Graded(Grade.UNENFORCED, _HOST_CHANNEL_EXCLUSIVITY),
            }
        case RuntimeKind.OCI:
            return {
                Axis.CONTROL: Graded(Grade.ENFORCED, _OCI_CONTROL),
                Axis.CHANNEL_EXCLUSIVITY: Graded(Grade.UNENFORCED, _OCI_CHANNEL_EXCLUSIVITY),
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
#: reach it: the channel directory beside it is every channel's one grant
#: (decision-186).
PROCS_DIRNAME: Final = "procs"

#: `<jail_dir>/chan`: the runtime's channel directory, one per jail
#: (decision-184). A name brig keeps beside `tmp`, `procs` and `jail.json`,
#: never a `Spec` path: each start's socket is reserved there.
CHANNELS_DIRNAME: Final = "chan"


#: `<jail_dir>/tmp`: the jail's scratch, the one part of the jail directory a write
#: root reaching it still grants (decision-173); an embedder points `TMPDIR` there.
#: In a supervised jail whose processes have namespaces of their own, each gets a
#: directory of its own over it (decision-195).
SCRATCH_DIRNAME: Final = "tmp"


def scratch_dir(jail_dir: str) -> str:
    """The scratch directory of the jail in `jail_dir` (decision-173). Pure:
    lexical, so a caller that needs it resolved passes a resolved `jail_dir`."""
    return f"{jail_dir.rstrip('/')}/{SCRATCH_DIRNAME}"


def channel_dir(jail_dir: str) -> str:
    """The channel directory of the jail in `jail_dir` (decision-184). Pure:
    lexical, so a caller that needs it resolved passes a resolved `jail_dir`."""
    return f"{jail_dir.rstrip('/')}/{CHANNELS_DIRNAME}"
