"""`env_scrub`: the `env` axis mechanism -- allow-list model, argv wrapping.

SPEC.md §6 roster row, verbatim:

    | `env_scrub` | env | all | `enforced` -- the child never receives scrubbed vars |

**Delivery mechanism -- RULED, decision-066 (operator round 7, A7 accepted).**
SPEC.md §6 types `Step.env` as `Mapping[str, str]` (additions only) and §7
merges env with later-wins declared conflicts as errors -- a mapping of
additions cannot express *removal*. So `env_scrub` does not ask the launcher
to replace the environment; it delivers by **argv wrapping**: `Step.wrap`
renders an argv that starts the workload under a constructed environment,
`/usr/bin/env -i` plus explicit `NAME=value` assignments for the allow-listed
names it forwards and for the policy's `set` pairs. Grounds (decision-066):
this keeps `Step.env` additive exactly as §6 specifies; it keeps enforcement
IN ARGV, which is the bet §8 says tmux composability rests on; and it makes
`spec -> argv` a pure render function -- the unit-tier rules' goldmine.

**Why a shell, not a bare `env` invocation.** `compile()` is a pure render:
no I/O, no clock, no environment read (`os` is not importable here --
`tests/unit/test_mech_events_purity.py` pins this file's import set). So the
ACTUAL VALUE of an allow-listed name -- e.g. what `HOME` currently is -- is
not knowable at compile time; only its NAME is (from `EnvPolicy.allow_names`).
`/usr/bin/env` itself has no "forward this one name from whatever I
inherited" flag (BSD/darwin `env(1)`: `-i` clears everything, `-u name`
removes one name from what's kept, `name=value` sets a literal -- confirmed
by reading this host's own `env(1)` manual page, not assumed); an allow-list
of unknown-in-advance values cannot be expressed with only those primitives.
So the render targets `/bin/sh -c '...'`: the SCRIPT TEXT is pure, compile-
time-constructed data (POSIX shell syntax, built from names and literal
`set` values only -- no substitution happens at compile time), and shell
variable expansion (`"$NAME"`) happens only when the shell actually RUNS,
inheriting the real process environment normally at that point (nothing has
scrubbed `/bin/sh`'s OWN environment -- only what it hands to the exec'd
child via `env -i` is restricted). The `set` pairs need no runtime
substitution (their values are literal spec data); they are still embedded
in the same script text, single-quoted, so both kinds of assignment sit on
one `env` command line.

**Trust boundary named, not enforced here.** `allow_names` entries and
`set` KEYS are embedded into the script text UNQUOTED (only `set` VALUES
pass through `_shquote`), and `EnvPolicy` (`brig/core/spec.py`, task-033's
file, not this task's) validates nothing about their shape. Today's model
is "the spec author is trusted" -- a name containing a shell metacharacter
would corrupt the render, not merely fail to forward. This surface is named
here for whichever later task decides whether `EnvPolicy` should refuse a
malformed name at construction, rather than left for a reader to discover
unnamed.

**Portability is not assumed (decision-066's named risk).** `env -i`'s
handling of a `--` separator differs between the darwin and GNU
implementations. The render never emits `--`: the assignment tokens always
precede the workload's own argv, so `env` needs no `--` to tell them apart
UNDER THE CALLER PRECONDITION documented below, and there is nothing for a
`--`-handling divergence to bite once that precondition holds.
`tests/integration/test_env_scrub.py` demonstrates the rendered argv
actually running on this platform (AC #8), not just reasoned about --
decision-066: "The named risk must be RUN, not reasoned about."

**Caller precondition this render does NOT enforce (named, not assumed
away).** `env`'s own parsing scans tokens for a `NAME=value` shape and
takes the first token that does NOT match as "the utility" -- this
project's own reading of this host's `env(1)` manual page names the
consequence directly: "The env utility does not handle values of utility
which have an equals sign in their name... This can easily be worked
around by interposing the `command(1)` utility." So if the WORKLOAD's own
`argv[0]` itself happened to be shaped like `NAME=value` (a program path
containing a literal `=`, which no test here constructs and no code here
forbids), `env` would misparse it as one more assignment and treat the
workload's OWN `argv[1]` as the utility instead -- silently wrong, no
denial, no signature (this mechanism declares none, see below). Avoiding
`--` (decision-066's ruling) trades this edge case for sidestepping the
darwin/GNU `--`-handling divergence entirely; every realistic workload
argv[0] this project launches (an interpreter path, a shell, a compiled
binary's path) does not have this shape, so the trade is accepted, but it
is a caller precondition, not a property this render's code establishes
or checks -- a claim this docstring is deliberately not overstating.

**PASS mode (task-033's ruling).** A `PASS` policy confers everything, so
there is nothing to scrub: `wrap` is the identity transform (argv passes
through unmodified -- no `env -i`, no shell). `set` pairs still apply, via
`Step.env` (additive is exactly right here: PASS's baseline is full
inheritance, and `set` only needs to add/override on top of it -- unlike
SCRUB, where `-i` would erase anything handed through `Step.env` before the
child ever sees it, which is why SCRUB's `set` pairs travel in the SAME
argv-embedded `env` command line as the allow-listed names instead).
`EnvPolicy(mode=PASS, allow_names=(...))` does not construct (task-033), so
PASS's compiled `Step` never needs to render an allow-list at all.

**PASS mode claims nothing on the env axis (SPEC.md §6, decision-092, P-12,
task-044): `Step.grades` is the empty mapping under `PASS`, because forwarding
everything untouched is byte-identical to what the empty stack already does,
so there is no policy being enforced for `ENFORCED` to describe, and the axis
falls through to §7's coverage fill as `unenforced` -- `Step.grades` carries
`{Axis.ENV: Graded(Grade.ENFORCED, "")}` only under `SCRUB`, where a policy is
actually being applied.**

**`denial_signatures` is the empty tuple, and this is why (SPEC.md §6,
decision-068/decision-067).** Scrubbing produces ABSENCE, not a denial: a
program that fails because a variable it wanted is simply not there emits
whatever generic text ITS OWN missing-variable handling produces (e.g. "unbound
variable", or nothing at all) -- exactly the kind of text the unit-tier
rules forbid a signature from matching, because a signature that matched it
would convert an M4 probe's honest absence-check into a false PASS on an
unrelated failure. So this mechanism declares no signature at all, rather
than inventing one that would be vacuous by construction.

**Grade scope: `Graded(Grade.ENFORCED, "")` is scoped to the CHILD, per
task-034's own AC #5 wording ("any path by which the CHILD recovers a
scrubbed value").** It is not a claim about the wider system. Both a
forwarded value (after `${NAME:+...}` expansion) and a `set` value transit
through the ARGV of an intermediate process on this box: `/bin/sh`'s own
`argv[2]` carries the `set` pairs' literal text, and `/usr/bin/env`'s own
argv, once the shell expands `${NAME:+...}`, carries the forwarded value in
the clear -- both visible to any other process on the host reading the
process table (`ps -Ao command=`) during that brief window, the same
mechanism `tests/conftest.py`'s own leak sweep relies on to find things.
The jailed CHILD genuinely cannot recover a scrubbed value (task-034's own
AC #5 evidence: no `/proc` on darwin, `ps eww` prints no env data on this
host, and a re-exec'd shell only ever inherits what it was already given),
so `ENFORCED` stands under the grade's own stated scope -- but this argv-
transit property is real, matters most for `set` (whose entire purpose is
injecting a value the embedder chose, which may be a credential), and is
named here rather than left for a reader to discover the hard way.

**`Step.events`** (task-031's `EventSource` shape, decision-060/decision-069):
`_EnvScrubEventSource.known_at_compile` reports the ONE fact this mechanism
actually knows the instant `compile()` returns -- which names it is
FORWARDING (`EnvPolicy.allow_names`) and which literal names it is SETTING
(`EnvPolicy.set`'s keys) -- not which names get scrubbed AWAY, because a pure
compile with no environment read cannot enumerate a vocabulary it never
looked at (claiming to name "scrubbed" variables would be exactly the
CLAUDE.md "true-as-tested but weaker than it reads" trap: sounding like a
census of what was removed while only ever having seen what was kept).
`classify_exit` always returns `None`: scrubbing is a compile-time decision,
not something a mechanism recognizes retroactively from how the workload
exited (the mirror image of `rlimits`, whose interesting case is
`classify_exit` and whose `known_at_compile` is always `()`).

**This payload reuses `EventKind.SPAWN` rather than contributing a new
kind, a DELIBERATE in-layer choice, named here so M3's closeout can rule on
it rather than discover it.** `brig/run/launcher.py` already appends its
own `SPAWN` record (`argv`/`pid`/`pgid`/`cwd`) for every launch; this
mechanism's `known_at_compile` payload is a SECOND, disjoint-schema
`SPAWN`-kind payload, whereas `core/events.py`'s own precedent for a
mechanism sensor with something new to say is to CONTRIBUTE a kind
(`LIMIT_TRIP`, task-036) rather than overload an existing one. Staying
in-layer (`mech` may not touch `brig/core/events.py`'s `EventKind`
vocabulary -- that is `core`, and this task's own scope is `layer:mech`) was
the right call for THIS task; a dedicated kind is a call for whichever task
next touches `core/events.py`'s vocabulary, not this one. Also worth
stating plainly: as of this task, nothing in `brig/run` calls
`EventSource.known_at_compile()` at all -- this payload is reachable and
tested (`tests/unit/test_env_scrub_compile.py`), but does not yet reach any
jail's actual event log.
"""

from __future__ import annotations

from typing import Final

from brig.core import Axis, EnvMode, EnvPolicy, EventKind, Grade, Graded, Spec
from brig.mech.contract import ArgvTransformer, CompileCtx, EventPayload, ExitOutcome, Step

_ENV_UTILITY = "/usr/bin/env"
#: decision-143 (2): the ENV grade's detail used to be the empty string, so a
#: report reader saw ENFORCED with no scope and no caveat while the caveat sat
#: in this module's docstring, where a report reader never looks. The grade is
#: correct and stays; the detail now says what it is scoped to.
_SCRUB_DETAIL: Final[str] = (
    "enforced AGAINST THE CHILD: a jailed process cannot recover a scrubbed "
    "value by any means. Host-side, values are PLACED IN AN ARGV -- /bin/sh's "
    "-c script and /usr/bin/env's assignment tokens -- and are exposed to "
    "anything able to read that argv during the exec chain. This applies to "
    "forwarded values and, notably, to EnvPolicy.set, whose purpose is "
    "injecting an embedder-chosen value that may be a credential "
    "(decision-093, decision-143). The window is SHORT, and measured: both "
    "execs collapse the chain in microseconds, and 25 spawns raced by a tight "
    "ps poll caught it 0 times -- so ps is the wrong instrument, while execve "
    "auditing or a debugger are unaffected by brevity. It is host visibility "
    "either way, not a gap in the child's confinement, which is what this "
    "axis grades."
)

_SHELL = "/bin/sh"
_SCRUB_FLAG = "-i"
_POSITIONAL_ARGS = '"$@"'


def _shquote(value: str) -> str:
    """Single-quote `value` for embedding in a POSIX shell script's text,
    escaping any embedded single quote the standard `'\\''` way (close the
    quote, emit an escaped quote, reopen). Used only for `EnvPolicy.set`'s
    literal VALUES -- `allow_names` (and `set`'s own KEYS) never go
    through this: their NAMES are still written into the script text
    unquoted (see this module's "Trust boundary" paragraph), but what they
    stand for -- the forwarded VALUE -- is never known at compile time and
    is expanded by the shell itself at run time (`${NAME:+"NAME=$NAME"}`),
    never written as literal text the way a `set` VALUE is."""
    return "'" + value.replace("'", "'\\''") + "'"


def _assignment_tokens(policy: EnvPolicy) -> tuple[str, ...]:
    """The `NAME=value`-shaped tokens `env` receives, in order: forwarded
    names first, then literal `set` pairs (`NAME='value'`, known already
    at compile time). Both `allow_names` and `set` arrive pre-sorted by
    `EnvPolicy.__post_init__`, so this ordering is deterministic without
    this function sorting anything itself.

    **Forwarding is CONDITIONAL, not unconditional.** A forwarded name
    renders as `${NAME:+"NAME=$NAME"}`, not the simpler `NAME="$NAME"`:
    the simpler form still creates the binding (`NAME=`) even when `/bin/sh`
    never inherited `NAME` at all -- observed directly on this host before
    this shape was chosen -- which would hand the workload a DEFINED-BUT-
    EMPTY variable in place of an ABSENT one, a real semantic difference
    (`[ -v NAME ]` vs `[ -z "$NAME" ]`) that "forwards" does not license.
    `${NAME:+word}` is POSIX parameter expansion: if `NAME` is unset or
    empty, the WHOLE expansion (including the embedded `"NAME=$NAME"`) is
    the empty string, and being unquoted at the top level it then
    word-splits to ZERO argv elements -- no binding at all, not an empty
    one. If `NAME` is set and non-empty, the quotes written INSIDE the
    `:+` alternative are honored for word-splitting, so a value containing
    spaces still lands in `env`'s argv as ONE token. Verified empirically
    on this host for all three cases (unset, set-with-a-space, set-empty),
    not merely reasoned from the POSIX grammar -- see task-034's notes.

    **`set` does NOT get this same absent-if-empty treatment, deliberately
    -- `KEY=''` (an EMPTY value) still DEFINES `KEY` in the child.** The
    asymmetry with `allow_names` above is intentional, not an
    inconsistency: `allow_names` is a FILTER over the parent's own state
    (there IS no meaningful value to set when the parent never had the
    name, so "absent" is the only honest rendering), while `set` is an
    INSTRUCTION carrying a literal value the spec author chose -- an empty
    string is a value they chose, same as `HTTP_PROXY=""` is a real,
    distinct-from-unset idiom elsewhere. `tests/unit/test_env_scrub_compile.py`
    pins this asymmetry directly (`set=(("KEY", ""),)` renders `KEY=''`,
    present and empty) so a later refactor toward symmetry cannot flip
    this silently."""
    forwarded = tuple(f'${{{name}:+"{name}=${name}"}}' for name in policy.allow_names)
    literal = tuple(f"{key}={_shquote(value)}" for key, value in policy.set)
    return forwarded + literal


def _render_scrub_script(policy: EnvPolicy) -> str:
    """The POSIX `/bin/sh -c` script text for SCRUB mode: `exec` (so no
    shell process lingers behind the workload) `/usr/bin/env -i`, the
    assignment tokens, then `"$@"` -- the workload's own argv, passed
    through `sh -c '...' sh <argv...>` positional parameters, so it is
    never re-parsed as shell syntax, and no `--` separator is used at all
    (decision-066's named portability risk, sidestepped rather than
    reasoned about) -- SUBJECT TO the caller precondition this module's
    own docstring names: `argv[0]` must not itself be `NAME=value`-shaped,
    or `env` misparses it as one more assignment rather than the utility.
    This function does not check that precondition; it only renders."""
    tokens = _assignment_tokens(policy)
    return " ".join(("exec", _ENV_UTILITY, _SCRUB_FLAG, *tokens, _POSITIONAL_ARGS))


def _render_wrap(policy: EnvPolicy) -> ArgvTransformer:
    """Build the pure `argv -> argv` transformer for one compiled
    `EnvPolicy`. A closure, not a method reading `self`, matching
    `rlimits._render_wrap`'s own posture: `compile` calls this once per
    `Spec`, and the closure itself touches nothing but its captured
    `policy`."""
    if policy.mode is EnvMode.PASS:

        def identity(argv: tuple[str, ...]) -> tuple[str, ...]:
            return argv

        return identity

    script = _render_scrub_script(policy)

    def wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
        return (_SHELL, "-c", script, "sh", *argv)

    return wrap


class _EnvScrubEventSource:
    """`env_scrub`'s sensor feed: the applied allow-list/set policy is
    known at compile time (nothing to classify at exit). See this module's
    docstring for the purity contract, decision-069's two constraints, and
    why the reported fact is "what was forwarded/set", never "what was
    scrubbed"."""

    def __init__(self, policy: EnvPolicy) -> None:
        self._policy = policy

    def known_at_compile(self) -> tuple[EventPayload, ...]:
        if self._policy.mode is EnvMode.PASS:
            return (EventPayload(kind=EventKind.SPAWN, data={"env_policy": "pass"}),)
        return (
            EventPayload(
                kind=EventKind.SPAWN,
                data={
                    "env_policy": "scrub",
                    "allowed_names": ",".join(self._policy.allow_names),
                    "set_names": ",".join(key for key, _value in self._policy.set),
                },
            ),
        )

    def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
        del outcome
        return None


class EnvScrub:
    """SPEC.md §6's `env_scrub` mechanism: `env` (allow-list model), all
    platforms this shell-based render targets (posix; see this module's
    docstring for why a shell is required at all)."""

    name = "env_scrub"
    axes: frozenset[Axis] = frozenset({Axis.ENV})

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        """Pure `spec -> argv` render; `ctx` is accepted per the
        `Mechanism` protocol but unused -- this mechanism stages nothing
        and reads nothing from the compile context (no I/O in `compile`,
        SPEC.md §6)."""
        del ctx
        policy = spec.env
        env: dict[str, str] = dict(policy.set) if policy.mode is EnvMode.PASS else {}
        # SPEC.md §6 / decision-092, P-12: PASS forwards the parent
        # environment untouched -- byte-identical to what the empty stack
        # does -- so there is nothing this mechanism is enforcing on the env
        # axis for THIS spec, and it claims nothing (`grades == {}`). Only
        # SCRUB is a real policy being applied, so only SCRUB grades
        # `Axis.ENV: ENFORCED`.
        grades: dict[Axis, Graded] = (
            {} if policy.mode is EnvMode.PASS else {Axis.ENV: Graded(Grade.ENFORCED, _SCRUB_DETAIL)}
        )
        return Step(
            wrap=_render_wrap(policy),
            env=env,
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades=grades,
            denial_signatures=(),
            events=_EnvScrubEventSource(policy),
        )


#: The mechanism instance embedders and later stack composition compose
#: against -- same posture as `brig.mech.rlimits`'s own module-level
#: `rlimits` instance.
env_scrub: EnvScrub = EnvScrub()
