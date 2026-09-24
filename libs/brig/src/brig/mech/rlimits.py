"""`rlimits`: the `limits` axis mechanism, cpu only, via the exec trampoline.

SPEC.md §6 roster row, verbatim:

    | `rlimits` | limits (cpu) | posix | exec-trampoline, no preexec_fn; `SIGXCPU` is real |

**The grade is `best_effort` on the AXIS, not `enforced` -- RULED, decision-061,
operator round 7, A2.** SPEC.md §4 gives `limits` ONE axis covering five
fields (cpu, memory, tasks, wall, output); `Graded` has no sub-field
structure; this mechanism reaches cpu and nothing else. §4's own table says a
grade that resists a hostile process *with a named gap* is `best_effort` --
"limits-cpu `enforced`" (MILESTONES.md M3 EC2's wording) is a statement about
the *field*, and EC2's own trailing clause ("with the uncovered limit fields
named in detail") already spells `best_effort`'s defining signature. Grading
the axis `enforced` here would be CLAUDE.md's never-grade-up trap landing on
M3's golden snapshot artifact (`degraded()`, task-039). `memory`, `tasks`,
`wall` and `output` are named in `detail`, parseable as an exact token set
after the `"uncovered:"` marker (see `_BEST_EFFORT_DETAIL` and
`tests/unit/test_rlimits_compile.py`'s grade test) -- per-field grading is M7's, not
this task's (`RLIMIT_NPROC`/task count is SPEC.md §6's "Deliberately absent",
never attempted by this or any mechanism).

`compile` is a pure `spec -> argv` render, no I/O: it renders `Step.wrap` as
the trampoline invocation task-035 ships, `python -m brig.mech.trampoline
--cpu N -- <argv>` (using `sys.executable` rather than the bare string
`"python"` -- a plain attribute read of an already-resolved interpreter path,
not I/O, and the only invocation that reliably has `brig` importable when run
under `uv run`, matching `tests/integration/test_trampoline.py`'s own
convention). **A zero limit means uncapped** (SPEC.md §5: "0 = uncapped"), so
`cpu_seconds=0` renders NO `--cpu` flag at all -- rendering `--cpu 0` would
trip `RLIMIT_CPU` on the workload's first tick, an instant kill and the exact
opposite of "uncapped."

**`SIGXCPU` is real on BOTH kernels, and that took a second of headroom**
(decision-161, 2026-09-08, SPEC.md §6). The trampoline sets `RLIMIT_CPU` to
`(N, N + 1)`, not `(N, N)`: Linux checks the HARD limit first, so a soft limit
equal to the hard one is delivered as `SIGKILL` and everything below in this
module -- the `signal:SIGXCPU` denial signature, `classify_exit`'s `LIMIT_TRIP`,
the limits battery that reads them -- would simply never fire there. Darwin
signals at the soft limit either way, which is why the pair was fine until the
suite was first run on Linux. `N` is still the cap; the extra second exists so
the signal arrives before the kill does.

**The denial signature's classification subject** (decision-068, folded into
SPEC.md §6/§12 at the M3 gate): not raw stdout, but the workload's stderr
followed by a canonical termination summary line carrying `signal:...` /
`exit:...` tokens. This mechanism's denial IS a signal, not text, so its one
signature matches the canonical token `signal:SIGXCPU` and, per the unit-tier
rules' both-directions requirement, must NOT match a generic failure
("command not found", "No such file or directory") -- the not-match half is
what keeps an M4 probe from passing vacuously.

**`Step.events`** (task-031's `EventSource` shape, decision-060/decision-069):
`_RlimitsEventSource.classify_exit` recognizes a `SIGXCPU` termination
(Python's own subprocess encoding, `returncode == -signal.SIGXCPU`) as this
mechanism's own cpu limit tripping, and returns an `EventPayload` naming the
limit field (`"cpu"`) and the signal -- the first mechanism sensor to
contribute a new `EventKind` member (`LIMIT_TRIP`, `brig/core/events.py`),
per SPEC.md §11's "until a mechanism sensor contributes its own." Pure:
`classify_exit` reads only its own argument, no clock, no I/O, no spawn --
`run` is what stamps `ts`/`jail_id` and appends (decision-069's second
constraint). `known_at_compile` has nothing to report for this mechanism
(no fact is known before the workload runs) and always returns `()`.
"""

from __future__ import annotations

import re
import signal
import sys

from brig.core import Axis, EventKind, Grade, Graded, Spec
from brig.mech import ArgvTransformer, CompileCtx, EventPayload, ExitOutcome, Step

_TRAMPOLINE_MODULE = "brig.mech.trampoline"
_CPU_FLAG = "--cpu"
_SEPARATOR = "--"

#: SPEC.md §6/§12's canonical termination token for a `SIGXCPU` denial.
#: Matched against the probe engine's normalized denial string, never raw
#: stdout (decision-068).
_DENIAL_SIGNATURE: re.Pattern[str] = re.compile(r"signal:SIGXCPU")

#: The four `limits` axis fields this mechanism does not reach (SPEC.md §4:
#: "resource caps (cpu, memory, tasks, wall, output)"). The `"uncovered:"`
#: marker is what `tests/unit/test_rlimits_compile.py`'s grade test parses a token
#: set out of -- keep the marker and the comma-joined list both present if
#: this string is ever reworded.
_BEST_EFFORT_DETAIL = (
    "rlimits enforces the limits axis for cpu only (RLIMIT_CPU, via the exec "
    "trampoline); uncovered: memory, tasks, wall, output"
)

#: Python's own subprocess.returncode encoding for a SIGXCPU termination:
#: negative, magnitude the signal number.
_SIGXCPU_RETURNCODE = -int(signal.SIGXCPU)


def _render_wrap(cpu_seconds: int) -> ArgvTransformer:
    """Build the pure `argv -> argv` transformer for one compiled `cpu_seconds`
    value. A closure, not a method reading `self`, so the render stays a
    plain function of its inputs -- `compile` calls this once per `Spec`."""

    def wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
        cpu_flags: tuple[str, ...] = (_CPU_FLAG, str(cpu_seconds)) if cpu_seconds else ()
        return (
            sys.executable,
            "-m",
            _TRAMPOLINE_MODULE,
            *cpu_flags,
            _SEPARATOR,
            *argv,
        )

    return wrap


class _RlimitsEventSource:
    """`rlimits`' sensor feed: nothing known at compile time, a `SIGXCPU`
    termination recognized at exit. See this module's docstring for the
    purity contract and decision-069's two constraints."""

    def known_at_compile(self) -> tuple[EventPayload, ...]:
        return ()

    def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
        if outcome.returncode != _SIGXCPU_RETURNCODE:
            return None
        return EventPayload(
            kind=EventKind.LIMIT_TRIP,
            data={"field": "cpu", "signal": int(signal.SIGXCPU)},
        )


class Rlimits:
    """SPEC.md §6's `rlimits` mechanism: `limits` (cpu only), posix."""

    name = "rlimits"
    axes: frozenset[Axis] = frozenset({Axis.LIMITS})

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        """Pure `spec -> argv` render; `ctx` is accepted per the `Mechanism`
        protocol but unused -- this mechanism stages nothing and reads
        nothing from the compile context (no I/O in `compile`, SPEC.md §6)."""
        del ctx
        return Step(
            wrap=_render_wrap(spec.limits.cpu_seconds),
            env={},
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades={Axis.LIMITS: Graded(Grade.BEST_EFFORT, _BEST_EFFORT_DETAIL)},
            denial_signatures=(_DENIAL_SIGNATURE,),
            events=_RlimitsEventSource(),
        )


#: The mechanism instance embedders and later stack composition (task-037's
#: matrix, task-039's `degraded()` preset) compose against -- same posture
#: as `brig.mech`'s own `NEW_PROCESS_GROUP`/`JAIL_LIFETIME` module-level
#: constants.
rlimits: Rlimits = Rlimits()
