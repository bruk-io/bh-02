"""`mech.contract`: the mechanism contract, re-exported by `brig.mech`.

This module defines the contract that all mechanisms must implement:
`Mechanism` (a protocol), `Step` (a mechanism's compiled output), and the
supporting types: `LaunchFeature`, `HelperLifetime`, `Helper`, `StagedFile`,
`CompileCtx`, and `ArgvTransformer`.

Pure module: no I/O, no clock, no randomness, no subprocess. The layer gate
enforces the import side of that; convention enforces the rest.
(`brig/mech/trampoline/` is a separate program, not part of this claim --
see its own module docstring, and `tests/unit/test_mech_events_purity.py`'s
module docstring for why an ast-level purity scan of `brig/mech/` treats it
as a documented carve-out rather than silently exempting it.)

`Step.events` (an `EventSource | None` field from SPEC.md §6) carries a
mechanism's optional sensor feed, as of M3 (decision-060, decision-069;
formerly deferred by decision-037, discharged by these). `EventSource`,
defined below, is a `Protocol` and it is **pure**: none of its methods may
open a file, read a clock, read the environment, or spawn a process --
they return event *payloads* (`EventPayload`) as plain data. `run` is the
only layer permitted to write: for every `EventPayload` a `Step.events`'
methods return, `run` builds a real `brig.core.Event` by stamping the two
fields only `run` may supply, `ts` and `jail_id` (SPEC.md §6's
`EventSource` paragraph; decision-069's two binding constraints). The
Protocol has two methods, one per M3's two known cases: `known_at_compile()`
for a fact already known once `Mechanism.compile()` has run (e.g. which env
names `env_scrub` decided to scrub), and `classify_exit(outcome)` for a
classification of how the workload ended (e.g. `rlimits` recognizing its
own `SIGXCPU` trip) -- see each method's own docstring for the full
contract. `EventSource`'s method surface is implementation-defined per
decision-069 and is folded into SPEC.md §6 at the M3 closeout.

`Mechanism` is decorated with `@runtime_checkable` (from `typing`): this
allows `isinstance()` checks against it to work on concrete mechanism
implementations, which stack composition validation needs. `Mechanism` itself
carries no `@dataclass` decorator — it is a bare `Protocol`, per SPEC.md §6;
only `Step` and the other concrete value types below are dataclasses. This
choice means "duck typing with verification" over "no verification", which
helps catch mechanism-implementation mistakes early.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from brig.core import Axis, DataValue, EventKind, Graded, Spec

# Type aliases
ArgvTransformer = Callable[[tuple[str, ...]], tuple[str, ...]]
"""A function that transforms an argv tuple: (str, ...) -> (str, ...)."""


class LaunchFeature(Enum):
    """Features a launcher may support and a stack may require.

    Per SPEC.md §8: "NEW_PROCESS_GROUP, PTY, DETACH, ..."
    The trailing "..." in the spec is a promise of growth, not a licence to
    invent members now; more arrive with the launchers that need them.
    """

    NEW_PROCESS_GROUP = "NEW_PROCESS_GROUP"
    PTY = "PTY"
    DETACH = "DETACH"


class HelperLifetime(Enum):
    """When a helper process exits, relative to the jailed workload.

    Per SPEC.md §6:
    - JAIL_LIFETIME: dies when the jailed tree dies (via pipe-EOF or pid-watch)
    - LAUNCH_SCOPED: gone before the workload runs
    """

    JAIL_LIFETIME = "JAIL_LIFETIME"
    LAUNCH_SCOPED = "LAUNCH_SCOPED"


@dataclass(frozen=True, slots=True)
class StagedFile:
    """A file to be written into the jail before launch.

    Per SPEC.md §6: "profiles, scripts — written pre-launch".

    Attributes:
        relpath: Path relative to the jail directory. Absolute paths are
                 forbidden (ValueError on construction).
        content: The file content (plain text).
        mode: Unix file mode (default 0o600).
    """

    relpath: str
    content: str
    mode: int = 0o600

    def __post_init__(self) -> None:
        # A plain str.startswith check, not os.path.isabs: brig/mech/contract.py
        # imports no os (tests/unit/test_mech_events_purity.py pins the set),
        # and on the POSIX platforms this project targets (darwin, linux)
        # os.path.isabs(p) is exactly `p.startswith("/")` -- same semantics,
        # zero import.
        if self.relpath.startswith("/"):
            raise ValueError(
                f"StagedFile.relpath must be relative, got absolute path: {self.relpath!r}"
            )


@dataclass(frozen=True, slots=True)
class Helper:
    """A helper process run alongside the jailed workload.

    Per SPEC.md §6: "e.g. egress proxy; declared lifetime".

    Attributes:
        name: A short name for this helper (e.g. "proxy", "logger").
        argv: The command line (tuple of strings, first is program name).
        lifetime: When this process exits relative to the workload.
    """

    name: str
    argv: tuple[str, ...]
    lifetime: HelperLifetime


@dataclass(frozen=True, slots=True)
class CompileCtx:
    """Context passed to Mechanism.compile().

    Per SPEC.md §6: a minimum context carrying only what the M2 stack needs.
    Section 6 names this type in `Mechanism.compile`'s signature but never
    defines it; this is the minimum the M2 stack needs to construct one.
    It is *data given to* a mechanism, never something a mechanism goes and
    finds -- `mech` performs no I/O of its own during compile, which is what
    keeps `Mechanism.compile` a pure function of `(spec, ctx)`.

    **`jail_dir` arrives already resolved -- THE CALLER SUPPLIES A
    REALPATH'D `jail_dir`.** It is not a `Spec` path, so `resolved_paths`
    below cannot cover it, yet the staged profile and, usually, a LISTEN
    endpoint live under it. On darwin, `jail_dir` given as e.g. `/tmp/bgNNN`
    is the SYMLINKED form (`/tmp` -> `/private/tmp`), and a mechanism that
    writes a rule against the symlinked form silently matches nothing --
    the parent project's own documented `/tmp` vs `/private/tmp` lesson.
    Establishing this invariant (i.e. calling `realpath`) is `run`'s job,
    not `mech`'s (SPEC.md §6, decision-115); this docstring states the
    invariant because a caller constructing a `CompileCtx` by hand needs to
    know it, and a mechanism's own render is expected to hold a LEXICAL
    guard against the documented trap shape (never a realpath comparison,
    which would be I/O a pure render may not perform) -- see
    `brig.mech.seatbelt.profile.render_sbpl`'s own `UnresolvedPath` guard
    for the first mechanism that needs one.

    Attributes:
        jail_dir: Path to the jail directory where staged files will land.
                  Already realpath'd by the caller (see above) -- `mech`
                  never resolves it itself.
        platform: sys.platform as passed in (e.g. "linux", "darwin").
                  mech performs no I/O of its own during compile.
        resolved_paths: Mapping from a `Spec` path (exactly as the `Spec`
                  carries it) to its realpath'd form, built by a `run`-layer
                  helper -- `run` being the layer permitted to touch a
                  filesystem. Defaults to the empty mapping so a spec
                  needing no resolution constructs a context unchanged (the
                  ~15 pre-existing `CompileCtx(...)` call sites keep
                  compiling with this field entirely unset). A mechanism
                  that needs a path absent from this mapping refuses,
                  naming the path -- it never falls back to the lexical
                  form (SPEC.md §6, law 2's refusal-not-downgrade posture).
                  Defensively copied at construction, the same posture as
                  `Step.env` below. (Added 2026-08-24, decision-115.)
        path_exists: Mapping from a `Spec` path (exactly as the `Spec`
                  carries it, the same key shape as `resolved_paths`) to
                  whether that path EXISTED when the `run`-layer helper
                  built this context. The second fact `mech` cannot go and
                  get for itself, added 2026-09-08 by decision-159 for the
                  same reason and on the same terms as `resolved_paths`:
                  some mechanisms' primitives are shaped differently
                  depending on whether the path is already there, and
                  `os.path.exists` is I/O a pure `compile` may not perform.
                  `bwrap` is the first (and today only) consumer -- a bind
                  mount needs an existing source, while a tmpfs mount needs
                  an absent one, and picking the wrong form is either a
                  launch that fails or a `write_denies` carve-out that
                  silently does not hold. Defaults to the empty mapping so
                  every existing `CompileCtx(...)` call site constructs
                  unchanged, and a mechanism that needs a path absent from
                  this mapping REFUSES, naming the path -- it never guesses
                  a default, which would put the guess in the one place law
                  2 forbids one. Defensively copied at construction.
    """

    jail_dir: str
    platform: str
    resolved_paths: Mapping[str, str] = field(default_factory=dict)
    path_exists: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Defensive copy: prevent caller mutations from affecting this ctx,
        # same posture as Step.env's own __post_init__ below.
        resolved_copy = dict(self.resolved_paths)
        object.__setattr__(self, "resolved_paths", MappingProxyType(resolved_copy))
        exists_copy = dict(self.path_exists)
        object.__setattr__(self, "path_exists", MappingProxyType(exists_copy))


@dataclass(frozen=True, slots=True)
class EventPayload:
    """One event's kind and data, before `run` stamps `ts`/`jail_id`.

    Everything `EventSource`'s methods return -- never a `brig.core.Event`
    itself, because constructing one needs `ts`, and only `run` supplies a
    clock (SPEC.md §6's `EventSource` paragraph; decision-069's second
    binding constraint). `run` turns each `EventPayload` into a real
    `Event` by adding the two fields only it is allowed to stamp.

    Attributes:
        kind: Which of `core`'s `EventKind` members this event is. (A
              mechanism sensor contributing a *new* kind -- SPEC.md §11's
              "until a mechanism sensor contributes its own" -- is a
              decision for the mechanism that first needs one; this
              contract type does not pin `EventKind`'s vocabulary, `core`
              does.)
        data: Free-form kind-specific payload, same shape as
              `brig.core.Event.data`: `Mapping[str, DataValue]`.
              Defensively copied at construction (same posture as
              `Step.env` below and `core`'s own `Event.data`).
    """

    kind: EventKind
    data: Mapping[str, DataValue]

    def __post_init__(self) -> None:
        # `ts` and `jail_id` are `run`'s to stamp, never a mechanism's to
        # guess (decision-069's second binding constraint) -- refused here,
        # at construction, rather than left to be silently overwritten or
        # silently trusted later.
        reserved_present = [key for key in ("ts", "jail_id") if key in self.data]
        if reserved_present:
            raise ValueError(
                f"EventPayload.data must not carry {reserved_present!r} -- "
                "only brig.run stamps those"
            )
        # Defensive copy: prevent caller mutations from affecting this payload.
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


@dataclass(frozen=True, slots=True)
class ExitOutcome:
    """How a workload ended, exactly as `run` already knows it once the
    workload's process has exited -- handed to `EventSource.classify_exit`
    so a mechanism's sensor can recognize its own signature (e.g. `rlimits`
    recognizing `SIGXCPU`) without any I/O of its own to go find it.

    Attributes:
        returncode: Python's own subprocess encoding: zero or positive is
                    an exit code, negative is `-signal_number` (e.g. `-24`
                    for `SIGXCPU`) -- the same convention
                    `subprocess.Popen.returncode` uses, which is what
                    `brig/run` is already built on.
    """

    returncode: int


@runtime_checkable
class EventSource(Protocol):
    """SPEC.md §6's optional sensor feed a mechanism's `Step` may carry.

    A pure `Protocol`, `@runtime_checkable` for the same reason `Mechanism`
    below is: it lets `isinstance()` verify a concrete mechanism's sensor
    structurally. Every method returns data and only data -- no method
    here may open a file, read a clock, read the environment, or spawn a
    process (decision-069's first binding constraint; SPEC.md §6's
    `EventSource` paragraph). `run` is the only layer that writes: it
    calls these methods, then stamps `ts` and `jail_id` on every
    `EventPayload` returned, before appending (decision-069's second
    constraint).

    Two methods, one per M3's two known cases:

    - `known_at_compile()`: zero or more facts already available the
      instant `Mechanism.compile()` returns, before the workload is ever
      launched -- e.g. which env names `env_scrub` decided to scrub. `run`
      may call this once, immediately after compile, and append one
      `Event` per payload returned.
    - `classify_exit(outcome)`: given how the workload ended (already
      known to `run` -- no I/O needed here to obtain it), returns a
      payload naming what this mechanism's sensor makes of that ending
      (e.g. `rlimits` recognizing a `SIGXCPU` termination as its own cpu
      limit tripping), or `None` if this sensor has nothing to say about
      this particular ending.

    Ships no implementation here, the same way `Mechanism` ships no
    mechanism: the roster in SPEC.md §6 is a plan until each mechanism's
    own task. The method surface is implementation-defined per
    decision-069 and is folded into SPEC.md §6 at the M3 closeout.
    """

    def known_at_compile(self) -> tuple[EventPayload, ...]:
        """Facts already known once `compile()` has run. Pure: reads only
        this object's own already-computed state, nothing external."""
        ...

    def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
        """Classify `outcome` from this mechanism's point of view, or
        return `None` if this sensor recognizes nothing about it. Pure:
        a function of `outcome` and this object's own state only."""
        ...


@dataclass(frozen=True, slots=True)
class Step:
    """A mechanism's compiled output: how to enforce one slice of a Spec.

    Per SPEC.md §6, a Step is the compiled form of a Mechanism's slice of the
    Spec. It carries everything needed for a Stack to compose mechanisms,
    aggregate requirements, and produce an EnforcementReport.

    Attributes:
        wrap: An argv transformer that wraps the workload command line.
              Pure: argv -> argv, applied in stack composition order.
        env: Environment variables to add/override. Defensively copied at
             construction so caller mutations don't affect the Step.
        staged: Files to write into the jail before launch (relative paths only).
        helpers: Helper processes to run, each with a declared lifetime.
        requires: Features the launcher must provide (NEW_PROCESS_GROUP, PTY, etc).
        grades: Per-axis enforcement grades from this mechanism, keyed by Axis.
                Defensively copied at construction.
        denial_signatures: Regex patterns that identify this mechanism's denials
                          (e.g., "Read-only file system" for bwrap mounts).
        events: This mechanism's optional sensor feed (SPEC.md §6, §11), or
                `None` for a mechanism that has nothing to sense. Defaults
                to `None` so no pre-M3 construction site breaks.
    """

    wrap: ArgvTransformer
    env: Mapping[str, str]
    staged: tuple[StagedFile, ...]
    helpers: tuple[Helper, ...]
    requires: frozenset[LaunchFeature]
    grades: Mapping[Axis, Graded]
    denial_signatures: tuple[re.Pattern[str], ...]
    events: EventSource | None = None

    def __post_init__(self) -> None:
        # Defensive copy for env: prevent caller mutations from affecting this Step
        env_copy = dict(self.env)
        object.__setattr__(self, "env", MappingProxyType(env_copy))

        # Defensive copy for grades: prevent caller mutations from affecting this Step
        grades_copy = dict(self.grades)
        object.__setattr__(self, "grades", MappingProxyType(grades_copy))


@runtime_checkable
class Mechanism(Protocol):
    """A contract for compiling a slice of a Spec into enforcement (Step).

    Per SPEC.md §6, a Mechanism claims one or more axes and produces a Step
    when asked to compile a Spec in context. Multiple mechanisms compose to
    form a Stack.

    Attributes:
        name: A short identifier for this mechanism (e.g., "bwrap", "seatbelt").
        axes: Frozenset of Axis values this mechanism claims to enforce.
              Coverage and overlap are validated by Stack during composition.
        compile: Compile this mechanism's slice of spec into a Step, in the
                 given context (jail directory, platform).
    """

    name: str
    axes: frozenset[Axis]

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        """Compile this mechanism's constraints into enforcement (Step).

        Args:
            spec: The full Spec to compile this mechanism's slice of.
            ctx: Compile context (jail_dir, platform).

        Returns:
            A Step: argv wrapper, env vars, staged files, helpers, requirements,
            per-axis grades, and denial signatures.

        Raises:
            ValueError or similar if compilation fails (incompatible spec,
            missing platform support, etc).
        """
        ...


# Module-level constants for common enum values (optional ergonomics, like
# brig.core's ENFORCED, BEST_EFFORT pattern)
NEW_PROCESS_GROUP = LaunchFeature.NEW_PROCESS_GROUP
PTY = LaunchFeature.PTY
DETACH = LaunchFeature.DETACH
JAIL_LIFETIME = HelperLifetime.JAIL_LIFETIME
LAUNCH_SCOPED = HelperLifetime.LAUNCH_SCOPED

__all__ = (  # noqa: RUF022
    "ArgvTransformer",
    "CompileCtx",
    "DETACH",
    "EventPayload",
    "EventSource",
    "ExitOutcome",
    "Helper",
    "HelperLifetime",
    "JAIL_LIFETIME",
    "LAUNCH_SCOPED",
    "LaunchFeature",
    "Mechanism",
    "NEW_PROCESS_GROUP",
    "PTY",
    "StagedFile",
    "Step",
)
