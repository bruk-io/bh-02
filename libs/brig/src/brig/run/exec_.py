"""`exec_in_jail`: a sibling process inside the jail's confinement.

SPEC.md §9: `exec` runs "the `docker exec -it` experience, for every
stack" -- "the exec'd process is subject to the same Spec as the workload".
MILESTONES.md M2 scope: "exec (plain sibling process, cwd + env of the
jail)". Named `exec_` (trailing underscore, not `exec`) because `exec` is a
Python keyword/builtin.

**Why `handle` is typed `Any`, not `brig.run.handle.Handle`.** `handle.py`
imports this module at module level
(`from brig.run.exec_ import exec_in_jail as _exec_in_jail`). Importing
`Handle` back from `handle.py` here -- even guarded by `TYPE_CHECKING` --
would close a cycle: pypeeker's `no-import-cycles` rule explicitly counts
`TYPE_CHECKING`-guarded imports (only a *function-local* import is exempt,
since that runs at call time, not module-load time). The same reasoning
rules out importing `LaunchRefused` from `launcher.py`: `launcher.py`
imports `handle.py`, so `exec_ -> launcher -> handle -> exec_` is a cycle
too. A local structural `Protocol` was tried instead and rejected: mypy
models a frozen dataclass's fields as read-only, so `Handle` (frozen)
fails a `Protocol`'s default read-write attribute check, and
`test_launcher.py`'s existing `exec_in_jail(None, ["argv"], False)` call
(task-019's AC #11, a file this task does not own and does not touch)
stops type-checking either way once the parameter is anything narrower
than `Any`. `handle: Any` is the same choice `handle.py` itself already
made for `Handle.kill`'s and `Handle.exec`'s return types, for the same
forward-reference reason -- this module inherits it rather than fighting
it. `ExecRefused` is `LaunchRefused`'s shape (a typed `missing` field, not
a `str(exc)` parse) reproduced locally for the same import-cycle reason.

**`wrap_prefix`, not `jail.wrap` (task-046).** `Handle` still does not carry
the `CompiledJail.wrap` callable -- only `handle.wrap_prefix`,
`launcher.py`'s DERIVED-and-VERIFIED tuple of argv tokens the compiled
stack's `wrap` prepended ahead of the launched `argv` (`None` when that
verification found the wrap is not a pure prefix). This module reproduces
`jail.wrap`'s effect on an EXEC's own argv by literally prepending that
same prefix -- `(*wrap_prefix, *argv)` -- rather than re-invoking `wrap`
itself, which `Handle` has no way to carry across `to_dict`/`from_dict`'s
process boundary anyway (a callable is not serializable). Three cases,
per SPEC.md §9's "same Spec, never a weaker one" and "a mechanism that
cannot guarantee this refuses exec":

- `wrap_prefix is None` -- the compiled wrap was NOT verified as a pure
  prefix for this handle's own `argv`. Refuse (`ExecWrapNotAPrefix`)
  before anything is spawned or any file opened, rather than fall back to
  a bare, unconfined spawn.
- `wrap_prefix == ()` -- the empty stack (or any stack whose wrap happens
  to be the identity transform). Spawn `argv` bare and report
  `ExecFidelity.PLAIN` (SPEC.md §9: "The empty stack execs a plain
  process, graded accordingly").
- non-empty `wrap_prefix` -- spawn `(*wrap_prefix, *argv)` and report
  `ExecFidelity.EQUIVALENT_PROFILE`: an identical wrapper, spawned as a
  different instance, which is exactly what that member means.

**The env is `{**os.environ, **handle.jail_env}` in BOTH cases**, and that
is decision-152's change (2026-09-08). It was already the composition the
non-empty-prefix case used -- `launcher.py`'s own `full_env`, re-evaluated
at exec time so the sibling starts from the workload's declared overlay
rather than merely whatever this calling process inherited. The empty-prefix
case used to read a `Handle.env` field instead: a launch-time snapshot of
the launching process's WHOLE environment, serialized onto every handle.
That field is gone (see `handle.py`), because a serialized handle carrying
the operator's environment is a handle no embedder can put in its own log.
The two cases now compose the env identically, which is also one fewer way
for them to differ.

**Why the sibling's `pgid` is RECORDED, not inferred (task-027,
decision-042).** "An exec sibling is the handle's to reap" (SPEC.md §9)
requires a handle rehydrated in a LATER process to find and tear down a
sibling it never itself started -- `teardown.kill_jail` does this by
listing the records under `<jail_dir>/procs` (`brig/run/_records.py`)
rather than reading any in-memory state on `Handle` (which is frozen and
carries none). The medium changed twice (the event stream until
decision-152, `execs/` until decision-181); the binding clause --
durability outside the live object -- did not.

**A sibling is a start like the first process** (decision-181): its own
exit wrapper, its own records directory, its own tether watcher when the
jail is tethered, and a record that outlives its `wait`. A teardown after
the wait still runs the ladder for its group: `ALREADY_GONE` when empty, and
anything the sibling left running there is ended.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brig.core import Spec
from brig.core.runtime import Capability
from brig.run.runtime import IoPolicy, NoSupervisor, ProcessRecord, Supervisor


class ExecRefused(ValueError):
    """`interactive=True` requires the `PTY` launch feature. M2's only
    launcher (`SubprocessLauncher`) does not claim it -- the pty launcher
    arrives at M8 -- so every interactive exec refuses in M2. Same posture
    as `launcher.LaunchRefused`: a typed `missing` field, not `str(exc)`.
    """

    def __init__(self, missing: frozenset[Capability]) -> None:
        self.missing = missing
        super().__init__(str(self))

    def __str__(self) -> str:
        names = ", ".join(sorted(feature.value for feature in self.missing))
        return f"exec(interactive=True) requires launch feature(s) not available: {names}"


class ExecWrapNotAPrefix(ValueError):
    """SPEC.md §9: "The exec'd process is subject to the same Spec as the
    workload -- never a weaker one. A mechanism that cannot guarantee this
    refuses exec." Raised by every start in a jail whose `wrap_prefix` is
    `None` -- `create` verified that the compiled stack's `wrap` is NOT a
    pure argv prefix (a rewritten element, an appended trailing token, or a
    wrap that returns fewer tokens than it was given) -- and, in the process
    that created the jail, by a start whose own argv the compiled `wrap` does
    not map to `(*wrap_prefix, *argv)` (decision-181). Nothing is spawned
    rather than a process under a weaker confinement than the jail's. Typed
    fields (`wrap_prefix`, `requested_argv`), never a `str(exc)` parse --
    same posture as `ExecRefused` above and `launcher.LaunchRefused`.
    """

    def __init__(
        self, wrap_prefix: tuple[str, ...] | None, requested_argv: tuple[str, ...]
    ) -> None:
        self.wrap_prefix = wrap_prefix
        self.requested_argv = requested_argv
        super().__init__(str(self))

    def __str__(self) -> str:
        found = (
            "no prefix was found"
            if self.wrap_prefix is None
            else f"it does not map this argv to the jail's prefix {self.wrap_prefix!r} followed by it"
        )
        return (
            "start refused: the compiled stack's wrap is not a pure argv prefix "
            f"for this jail ({found}), so {self.requested_argv!r} cannot be "
            "guaranteed the same Spec as the jail's other processes -- refusing "
            "rather than starting it under a weaker confinement"
        )


class ExecFidelity(Enum):
    """SPEC.md §9 names all three in prose and never names the type
    (ambiguity A13 in the M2 plan). `oci_container`/`bwrap` place the exec
    inside the *same boundary instance* (`SAME_INSTANCE`, no M4 mechanism
    can deliver this -- out of scope, task-046); `seatbelt` and any other
    argv-wrap mechanism (`env_scrub`, `rlimits`, and their composition) can
    only start a sibling under an *identical, re-derived* wrapper --
    `EQUIVALENT_PROFILE`, first reachable at task-046, whenever
    `handle.wrap_prefix` is a non-empty, verified prefix; a stack with no
    mechanisms (or an identity wrap) execs a plain process (`PLAIN`) --
    M2's only member, still the empty-stack case as of this task."""

    SAME_INSTANCE = "SAME_INSTANCE"
    EQUIVALENT_PROFILE = "EQUIVALENT_PROFILE"
    PLAIN = "PLAIN"


@dataclass(frozen=True, slots=True)
class ExecHandle:
    """SPEC.md §9's per-exec handle. `_supervisor`/`_process` are this
    module's own bookkeeping for `wait()` -- not part of the SPEC-named
    shape (`pid`, `argv`, `interactive`, `fidelity`, `spec`, `stdout_path`,
    `stderr_path`, `wait`) -- so they are excluded from `repr`/`__eq__`
    (`compare=False`). `_supervisor` is the runtime's supervisor that started this
    sibling (decision-178); it holds the sibling's `Popen` for as long as
    this handle holds it."""

    pid: int
    argv: tuple[str, ...]
    interactive: bool
    fidelity: ExecFidelity
    spec: Spec
    stdout_path: str
    stderr_path: str
    _supervisor: Supervisor = field(repr=False, compare=False)
    _process: ProcessRecord = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))

    def wait(self, timeout: float | None = None) -> int:
        """Block for the exec'd process's exit status, through the supervisor
        that started it. Deletes nothing: the sibling's record outlives its
        `wait` (decision-181), so a later teardown still ends anything it left
        running in its group, and reports its group `ALREADY_GONE` when empty.
        Idempotent: a second `wait()` returns the same status.

        Raises:
            subprocess.TimeoutExpired: still running after `timeout` seconds.
            ExitStatusUnobservable: gone, and nothing recorded how it ended.
        """
        status = self._supervisor.wait(self._process, timeout)
        if status is None:
            raise subprocess.TimeoutExpired(self._process.argv, timeout or 0.0)
        return status


def exec_in_jail(handle: Any, argv: Sequence[str], interactive: bool = False) -> ExecHandle:
    """Run `argv` as a sibling process inside `handle`'s confinement.

    `interactive` is deliberately NOT keyword-only here even though
    `Handle.exec`'s public signature (SPEC.md §9) marks it `*,
    interactive=False` -- `handle.py` is frozen (task-019) and calls this
    function positionally (`_exec_in_jail(self, argv, interactive)`); a
    keyword-only parameter here would make every `handle.exec(...)` call
    raise `TypeError`. The public method's signature is unaffected; only
    this private delegate's is looser.

    cwd always comes from `handle`, never from this process's own
    `os.getcwd()`. The sibling is started by `handle.runtime`'s supervisor
    (`Supervisor.start`, decision-178): for `HostRuntime`, `(*wrap_prefix,
    *argv)` with env `{**os.environ, **jail_env}` (see this module's
    docstring's three-case list) -- in every case SPEC.md §9's "subject to
    the same Spec as the workload, never a weaker one" holds: an exec that
    inherited only the *caller's* raw environment would be a weaker
    confinement than the workload's own.

    **The refusal (`wrap_prefix is None`) is raised BEFORE anything is
    opened or spawned** -- checked first, ahead of the supervisor, so a refused
    exec creates no artifacts on disk (SPEC.md §9: "A mechanism that cannot
    guarantee this refuses exec" -- a refusal that still half-runs is not a
    refusal).

    Raises:
        ExecRefused: `interactive=True`; no launcher here has `PTY`.
        ExecWrapNotAPrefix: the jail's wrap is not a pure argv prefix.
        NoSupervisor: the jail's runtime has no supervisor to start a sibling with.
    """
    if interactive:
        raise ExecRefused(frozenset({Capability.PTY}))

    argv_t = tuple(argv)
    wrap_prefix: tuple[str, ...] | None = handle.wrap_prefix
    if wrap_prefix is None:
        raise ExecWrapNotAPrefix(wrap_prefix, argv_t)
    fidelity = ExecFidelity.EQUIVALENT_PROFILE if wrap_prefix else ExecFidelity.PLAIN

    supervisor = handle.runtime.supervisor(handle.record())
    if supervisor is None:
        raise NoSupervisor(f"jail {handle.jail_id!r} has no supervisor to start {argv_t!r} with")

    # Each process has a records directory of its own (decision-181), so its
    # stdio needs no name of its own any more.
    process = supervisor.start(argv_t, cwd=handle.cwd, io=IoPolicy())

    return ExecHandle(
        pid=process.pid,
        argv=argv_t,
        interactive=interactive,
        fidelity=fidelity,
        spec=handle.spec,
        stdout_path=process.stdout_path,
        stderr_path=process.stderr_path,
        _supervisor=supervisor,
        _process=process,
    )
