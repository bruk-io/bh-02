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

**Why the sibling's `pgid` is REGISTERED, not inferred (task-027,
decision-042).** "An exec sibling is the handle's to reap" (SPEC.md §9)
requires a handle rehydrated in a LATER process to find and tear down a
sibling it never itself started -- `teardown.kill_jail` does this by
listing `brig/run/_execs.py`'s registration directory under
`handle.jail_dir` rather than reading any in-memory registration on
`Handle` (which is frozen and carries none). Until decision-152
(2026-09-08) the registration was an `EXEC` record in the per-jail event
stream with no matching `EXEC_END`; the stream is gone and the directory
replaced it, but the binding clause -- durability outside the live object
-- is unchanged, and so is the pid-reuse limit SPEC.md §9 names.

**The registration is created BEFORE the sibling can matter and removed
the moment its exit status is observed** (`ExecHandle.wait`). A sibling
whose `wait()` is never called stays registered, which is the safe
direction: teardown then runs the ladder against a group that is already
gone and reports `ALREADY_GONE`, rather than skipping a group that is not.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brig.core import Spec
from brig.mech import LaunchFeature
from brig.run import _execs, _identity
from brig.run._spawn_pgid import spawn_pgid


class ExecRefused(ValueError):
    """`interactive=True` requires the `PTY` launch feature. M2's only
    launcher (`SubprocessLauncher`) does not claim it -- the pty launcher
    arrives at M8 -- so every interactive exec refuses in M2. Same posture
    as `launcher.LaunchRefused`: a typed `missing` field, not `str(exc)`.
    """

    def __init__(self, missing: frozenset[LaunchFeature]) -> None:
        self.missing = missing
        super().__init__(str(self))

    def __str__(self) -> str:
        names = ", ".join(sorted(feature.value for feature in self.missing))
        return f"exec(interactive=True) requires launch feature(s) not available: {names}"


class ExecWrapNotAPrefix(ValueError):
    """SPEC.md §9: "The exec'd process is subject to the same Spec as the
    workload -- never a weaker one. A mechanism that cannot guarantee this
    refuses exec." Raised when `handle.wrap_prefix` is `None` --
    `launcher.py`'s own `_derive_wrap_prefix` verified, at launch time,
    that the compiled stack's `wrap` is NOT a pure argv prefix for this
    handle's own `argv` (a rewritten element, an appended trailing token,
    or a wrap that returns fewer tokens than it was given), so this module
    cannot reproduce that wrap's effect on an exec's argv by prepending a
    fixed prefix and refuses rather than spawn a sibling under a weaker
    confinement than the workload's own. Typed fields (`handle_argv`,
    `requested_argv`), never a `str(exc)` parse -- same posture as
    `ExecRefused` above and `launcher.LaunchRefused`.
    """

    def __init__(self, handle_argv: tuple[str, ...], requested_argv: tuple[str, ...]) -> None:
        self.handle_argv = handle_argv
        self.requested_argv = requested_argv
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            "exec refused: the compiled stack's wrap is not a pure argv prefix "
            f"for this jail (handle.argv={self.handle_argv!r}), so a sibling "
            f"exec of {self.requested_argv!r} cannot be guaranteed the same "
            "Spec as the workload -- refusing rather than spawning a weaker "
            "sibling"
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
    """SPEC.md §9's per-exec handle. `_proc`/`_jail_dir`/`_ended` are this
    module's own bookkeeping for `wait()` -- not part of the SPEC-named
    shape (`pid`, `argv`, `interactive`, `fidelity`, `spec`, `stdout_path`,
    `stderr_path`, `wait`) -- so they are excluded from `repr`/`__eq__`
    (`compare=False`)."""

    pid: int
    argv: tuple[str, ...]
    interactive: bool
    fidelity: ExecFidelity
    spec: Spec
    stdout_path: str
    stderr_path: str
    _proc: subprocess.Popen[bytes] = field(repr=False, compare=False)
    _jail_dir: str = field(repr=False, compare=False)
    _ended: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))

    def wait(self, timeout: float | None = None) -> int:
        """Block for the exec'd process's exit status, then DEREGISTER this
        sibling (`brig/run/_execs.py`) -- the first `wait()` that observes a
        status is what makes it no longer a thing teardown must reap.
        Idempotent: a second `wait()` returns the same status and
        deregisters nothing twice."""
        status = self._proc.wait(timeout=timeout)
        if not self._ended:
            _execs.deregister(self._jail_dir, self.pid)
            object.__setattr__(self, "_ended", True)
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
    `os.getcwd()`. `env` is chosen per `handle.wrap_prefix` (see this
    module's docstring's three-case list) -- in every case SPEC.md §9's
    "subject to the same Spec as the workload, never a weaker one" holds:
    an exec that inherited only the *caller's* raw environment would be a
    weaker confinement than the workload's own.

    **The refusal (`wrap_prefix is None`) is raised BEFORE anything is
    opened or spawned** -- checked first, ahead of the stdout/stderr file
    opens below, so a refused exec creates no artifacts on disk (SPEC.md
    §9: "A mechanism that cannot guarantee this refuses exec" -- a refusal
    that still half-runs is not a refusal).
    """
    if interactive:
        raise ExecRefused(frozenset({LaunchFeature.PTY}))

    argv_t = tuple(argv)
    wrap_prefix: tuple[str, ...] | None = handle.wrap_prefix
    if wrap_prefix is None:
        raise ExecWrapNotAPrefix(tuple(handle.argv), argv_t)

    spawned_argv = (*wrap_prefix, *argv_t)
    # The launcher's OWN env composition (`launcher.py`'s `full_env`),
    # evaluated fresh at exec time -- the sibling's starting environment is
    # the workload's declared overlay over this process's environment, in
    # both fidelity cases (decision-152; see this module's docstring).
    spawn_env: dict[str, str] = {**os.environ, **handle.jail_env}
    fidelity = ExecFidelity.EQUIVALENT_PROFILE if wrap_prefix else ExecFidelity.PLAIN

    token = uuid.uuid4().hex[:12]
    stdout_path = os.path.join(handle.jail_dir, f"exec-{token}-stdout.log")
    stderr_path = os.path.join(handle.jail_dir, f"exec-{token}-stderr.log")

    with (
        open(stdout_path, "wb") as stdout_f,
        open(stderr_path, "wb") as stderr_f,
        open(os.devnull, "rb") as stdin_f,
    ):
        proc = subprocess.Popen(
            spawned_argv,
            cwd=handle.cwd,
            env=spawn_env,
            stdin=stdin_f,
            stdout=stdout_f,
            stderr=stderr_f,
            start_new_session=True,
        )

    pid = proc.pid
    # SPEC.md §9 / decision-042 (task-027): the EXEC record carries the
    # sibling's pgid EXPLICITLY, read fresh via `os.getpgid` -- never
    # inferred from `pid`. `start_new_session=True` makes them equal
    # today, but an inferred identity would be a claim about a launcher
    # detail, not a recorded fact; `teardown.kill_jail` (task-027) reads
    # this field back from a REHYDRATED handle in a separate process, so
    # the fact has to be on disk, not reconstructed.
    # task-075: the read goes through `spawn_pgid`, because darwin's
    # `getpgid()` raises ESRCH for a sibling that has ALREADY EXITED (a
    # fast command like `/usr/bin/true` under any scheduling delay) -- a
    # bare call here crashed `exec_in_jail` after the spawn but before the
    # registration, leaving the sibling unregistered and its zombie to the
    # GC. The fallback records the same fact (setsid-before-exec makes the
    # group the pid from birth); see `brig/run/_spawn_pgid.py`.
    pgid = spawn_pgid(proc)
    # decision-155: the registration carries WHEN this sibling started as
    # well as its number, so a teardown running later -- possibly in another
    # process -- can tell it from whatever the OS handed that pid to next.
    # Read here, while the sibling is as young as it will ever be.
    _execs.register(handle.jail_dir, pid, pgid, _identity.start_stamp(pid))

    return ExecHandle(
        pid=pid,
        argv=argv_t,
        interactive=interactive,
        fidelity=fidelity,
        spec=handle.spec,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        _proc=proc,
        _jail_dir=handle.jail_dir,
    )
