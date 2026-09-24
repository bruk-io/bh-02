"""`stack`: composes Mechanisms into a validated, launchable jail.

Implements SPEC.md §7 in full: `Stack(mechanisms).compile(spec, floors) ->
CompiledJail`, and the four-step validation order it names verbatim --
claims, coverage, compatibility, floors -- plus the Composition rules
(argv wrappers compose inside-out per the matrix ordering; env merges with
later-wins declared conflicts as errors; helpers and staged files union;
`requires` union).

Pure module: no I/O, no clock, no randomness, no subprocess. May import
`brig.core` and `brig.mech`, and nothing else (SPEC.md §13 layering).

**The compatibility matrix ships as literal, versioned data.** M2 shipped it
with zero pairs: with zero pairs, *every* pair drawn from a stack of
two-or-more mechanisms was unknown, and SPEC.md §7 step 3 says unknown pairs
are refused. M3 ships the first real pair, `{env_scrub, rlimits}`, carrying
an ordering rationale (task-037). The pair key stays an unordered
`frozenset[str]` -- M2's own docstring already anticipated this: "once real
ordering-sensitive pairs land, the directional rationale string is what
distinguishes them, not the key shape." What changed is the *value* shape:
each entry is now a `MatrixEntry`, carrying both the free-text rationale a
reviewer reads and a structured `outer` field naming which mechanism's
`Step.wrap` composes outermost -- `Stack.compile` reads `outer`
programmatically to decide application order (SPEC.md §7 Composition:
"argv wrappers compose inside-out per the matrix ordering"), so ordering
never depends on parsing prose.

**Presets.** `strict()` is still out of scope: SPEC.md §7 defines it as
linux `[bwrap, systemd_scope, pasta]`, and neither `systemd_scope` nor
`pasta` exists. `strict_linux()` (decision-159) is what linux gets instead
-- `[bwrap, rlimits, env_scrub]`, the linux sibling of `scratch_darwin()`
-- under a different name precisely so it cannot be mistaken for the
stronger stack it is not; see its own docstring for what it gives up. `degraded()` ships as of M3 (task-039) as the
two mechanisms that exist -- `rlimits` and `env_scrub` -- of SPEC.md §7's
three-mechanism `[env_scrub, rlimits, connect_proxy(env-routed)]`;
`connect_proxy` is M6 (RULED by decision-062: operator round 7, A3
accepted, and no stub proxy per SPEC.md §2 law 2), so this preset's
`network` axis grades honestly `unenforced` until then. See `degraded()`'s
own docstring for the detail, and `tests/unit/test_stack_degraded_preset.py`
for the golden report this preset compiles to today.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from types import MappingProxyType
from typing import Final

from brig.core import (
    AXES,
    Axis,
    AxisClaim,
    EnforcementReport,
    Floors,
    Grade,
    Graded,
    SignatureBook,
    Spec,
    unenforced_report,
)
from brig.mech import (
    ArgvTransformer,
    CompileCtx,
    EventSource,
    Helper,
    LaunchFeature,
    Mechanism,
    StagedFile,
    Step,
)
from brig.mech.bwrap import bwrap
from brig.mech.connect_proxy import ConnectProxy
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits
from brig.mech.seatbelt import Seatbelt, seatbelt


@dataclass(frozen=True, slots=True)
class MatrixEntry:
    """One compatibility-matrix pair's ordering (SPEC.md §7 step 3): which
    of the two mechanisms named by the matrix key composes outermost, and
    the prose rationale for that ordering.

    Attributes:
        outer: The `Mechanism.name` of whichever of the pair's two
               mechanisms `Stack.compile` applies LAST when composing argv
               wrappers -- per `_compose`'s own docstring, applying a
               Step's `wrap` last makes it the OUTERMOST layer of the
               composed argv (its own prefix tokens end up at the front of
               the tuple, everything else nested inside as trailing args).
               `Stack.compile` reads this field to order composition; it
               never infers ordering by parsing `rationale`.
        rationale: SPEC.md §7's "ordering rationale string": why `outer`
                   belongs outermost for THIS pair, in prose a reviewer
                   checks. Non-empty by construction.
    """

    outer: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError("MatrixEntry.rationale must be non-empty")


#: SPEC.md §7's own reason ("the limiter wraps outermost so it also bounds
#: the other mechanisms' helper processes"), made concrete for THIS pair --
#: precisely, since SPEC.md §7's canonical case is a real, persistent
#: `Step.helpers` process (e.g. `connect_proxy`'s proxy), and `env_scrub`
#: declares `helpers=()`: it has none. What `env_scrub` DOES contribute is
#: the degenerate form of the same hazard -- not a separate process, but
#: further SAME-PID pre-exec images, cpu-cheap and short-lived, sitting
#: between the trampoline's own image and the workload's. `rlimits` sets
#: `RLIMIT_CPU` on ITSELF (the trampoline, `python -m brig.mech.trampoline`)
#: before it `os.execvp`s whatever argv it was handed -- a POSIX rlimit is
#: inherited across `exec`, so once set it stays in force for every process
#: image that pid becomes next, no matter how many more `exec`s follow.
#: `env_scrub`'s own wrap is exactly two such further exec's-worth of
#: script: `/bin/sh -c 'exec /usr/bin/env -i ... "$@"'`. With `rlimits`
#: outermost, the composed argv is
#: `python -m brig.mech.trampoline --cpu N -- /bin/sh -c '...' sh <argv>`:
#: the trampoline sets the cpu cap, then execs into `env_scrub`'s `/bin/sh`
#: image (still capped, same pid), which execs into the `/usr/bin/env -i`
#: image (still capped, same pid), which execs the workload (still capped,
#: same pid). Reversing the order -- `env_scrub` outermost -- would cap
#: only what is left AFTER those two pre-exec images have already run, not
#: the cpu time they themselves spend: real, though narrow (microseconds
#: of shell/env-argv-building work, not a lingering process), and named
#: here rather than glossed over.
#:
#: The consequence a reviewer must check, named so it is checked rather
#: than assumed: with `rlimits` outermost, the trampoline briefly holds
#: the UNSCRUBBED parent environment (it has not exec'd into
#: `env_scrub`'s wrapper yet) before it execs into that wrapper, which is
#: the process that actually builds the scrubbed environment. That window
#: is acceptable ONLY because both intermediate process images --
#: the trampoline itself and `env_scrub`'s `/bin/sh` -- are brig's own
#: trusted code, never the caller's workload, and both `exec` away in
#: turn (never fork, per `brig/mech/trampoline/__init__.py`'s own pinned
#: property) rather than lingering: the workload itself never runs until
#: `env -i` has already replaced the process image with the scrubbed one.
#: `tests/integration/test_stack_matrix_ordering.py` runs this composed
#: stack for real: one test confirms the FINAL workload's environ is
#: scrubbed (task-037 AC #7's own env claim), and a second launches a real
#: `cpu_seconds=1` spin loop through the SAME composed stack and confirms
#: it still dies on `SIGXCPU` (the cpu claim above -- the limit really does
#: reach through env_scrub's pre-exec images to the workload). Neither half
#: of this rationale is asserted on faith.
_ENV_SCRUB_RLIMITS_RATIONALE: Final[str] = (
    "rlimits composes outermost, env_scrub inner. SPEC.md §7's own reason, "
    "made concrete: the limiter wraps outermost so the cpu cap also bounds "
    "the OTHER mechanism's own pre-exec work, not only the final workload "
    "-- here, env_scrub's own '/bin/sh -c exec env -i ...' wrapper. Because "
    "RLIMIT_CPU is set by the trampoline on itself and a POSIX rlimit is "
    "inherited across exec, one setrlimit before the first exec stays in "
    "force through every later exec in the same pid: trampoline (sets the "
    "limit) -> exec into env_scrub's /bin/sh image (still capped) -> exec "
    "into the /usr/bin/env -i image (still capped) -> exec into the "
    "workload (still capped). Reversing the order would leave env_scrub's "
    "own /bin/sh and /usr/bin/env pre-exec images -- same-pid, cpu-cheap, "
    "short-lived, not persistent Step.helpers processes -- uncapped. "
    "Consequence to verify, not assume: with rlimits outermost the "
    "trampoline briefly holds the unscrubbed parent environment before it "
    "execs into env_scrub's wrapper. That is acceptable only because both "
    "intermediate images -- the trampoline and env_scrub's /bin/sh -- are "
    "brig's own trusted code, never the workload, and both exec away in "
    "turn rather than lingering, so the workload itself never runs until "
    "/usr/bin/env has already replaced the process image with the "
    "scrubbed one."
)

#: task-059 (M5-lite): `seatbelt` joins the stack, giving a three-mechanism
#: triangle -- `{rlimits, seatbelt}` and `{seatbelt, env_scrub}`, added
#: below alongside M3's existing `{env_scrub, rlimits}` row (unchanged).
#: Outermost to innermost across all three: `rlimits`, `seatbelt`,
#: `env_scrub` (task-059's Deliverable, ratified ordering rationale below).
#:
#: **`{rlimits, seatbelt}` -- `rlimits` outermost.** SPEC.md §7's own
#: reason, made concrete for this pair: the limiter wraps outermost so the
#: cpu cap also bounds the OTHER mechanism's own subprocess, not only the
#: final workload -- here, seatbelt's `/usr/bin/sandbox-exec` itself, and
#: everything it in turn execs inside the jail. `RLIMIT_CPU` is set by the
#: trampoline on itself and a POSIX rlimit is inherited across `exec`, so
#: one `setrlimit` before the first exec stays in force through every
#: later exec in the same pid: trampoline (sets the limit) -> exec into
#: `sandbox-exec` (still capped) -> `sandbox-exec` execs into the
#: seatbelt-confined workload (still capped). Reversing the order would
#: leave `sandbox-exec` itself -- and any of its own pre-workload setup --
#: uncapped.
_RLIMITS_SEATBELT_RATIONALE: Final[str] = (
    "rlimits composes outermost, seatbelt inner. SPEC.md §7's own reason, "
    "made concrete: the limiter wraps outermost so the cpu cap also bounds "
    "the OTHER mechanism's own subprocess, not only the final workload -- "
    "here, seatbelt's own /usr/bin/sandbox-exec invocation, and everything "
    "it in turn execs inside the jail. Because RLIMIT_CPU is set by the "
    "trampoline on itself and a POSIX rlimit is inherited across exec, one "
    "setrlimit before the first exec stays in force through every later "
    "exec in the same pid: trampoline (sets the limit) -> exec into "
    "sandbox-exec (still capped) -> sandbox-exec execs into the "
    "seatbelt-confined workload (still capped). Reversing the order would "
    "leave sandbox-exec itself, and any of its own pre-workload setup, "
    "uncapped."
)

#: **`{seatbelt, env_scrub}` -- `seatbelt` outermost.** So that the
#: env-constructing `/bin/sh -c 'exec env -i ...'` and `/usr/bin/env`
#: processes THEMSELVES run INSIDE the seatbelt jail, not unconfined
#: outside it: `sandbox-exec` wraps the whole exec chain, so env_scrub's
#: own pre-exec images are confined by the SBPL profile the same as the
#: final workload is. Reversing the order -- env_scrub outermost -- would
#: exec `/bin/sh`/`/usr/bin/env` UNCONFINED first and only later exec into
#: `sandbox-exec`, so those two pre-exec images would run outside the jail
#: entirely (no SBPL confinement whatsoever, not merely uncapped as in the
#: rlimits/seatbelt pair above) and only the FINAL workload image would end
#: up confined. `env_scrub` innermost is also what makes its `env -i`
#: reach the workload, per that mechanism's own module docstring.
_SEATBELT_ENV_SCRUB_RATIONALE: Final[str] = (
    "seatbelt composes outermost, env_scrub inner. So that the "
    "env-constructing /bin/sh -c 'exec env -i ...' and /usr/bin/env "
    "processes themselves run INSIDE the seatbelt jail, not unconfined "
    "outside it: sandbox-exec wraps the whole exec chain, so env_scrub's "
    "own pre-exec images are confined by the SBPL profile the same as the "
    "final workload is. Reversing the order -- env_scrub outermost -- "
    "would exec /bin/sh and /usr/bin/env UNCONFINED first and only later "
    "exec into sandbox-exec: those two pre-exec images would run outside "
    "the jail entirely, with no SBPL confinement at all, and only the "
    "final workload image would end up confined. env_scrub inner is also "
    "what makes its env -i actually reach the workload -- though env_scrub "
    "is no longer INNERMOST once connect_proxy is in the stack: see "
    "_CONNECT_PROXY_ENV_SCRUB_RATIONALE and decision-135 for the one "
    "mechanism allowed to sit between env_scrub and the workload, and why "
    "it must."
)

_CONNECT_PROXY_ENV_SCRUB_RATIONALE: Final[str] = (
    "env_scrub composes outer, connect_proxy INNERMOST. Forced, not "
    "chosen: env_scrub's SCRUB render is 'exec /usr/bin/env -i "
    '<assignments> "$@"\', so if env_scrub were inner its env -i would '
    "run closer to the workload than connect_proxy's export and would "
    "wipe HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy outright. The "
    "workload would then start with the proxy variables unset and reach "
    "the network directly -- the same silent, total loss of policy that "
    "connect_proxy's own wrap refuses when the port file is missing. "
    "There is no symmetric cost in the other direction. This NARROWS "
    "env_scrub's innermost law to: nothing may sit between env_scrub and "
    "the workload that re-adds what it removed, EXCEPT a mechanism whose "
    "declared purpose is to add a bounded, audited, named set of "
    "variables -- connect_proxy adds exactly four. Carrying the proxy "
    "variables in EnvPolicy.allow_names or .set instead is IMPOSSIBLE, "
    "not merely worse: the proxy binds port 0 so the number does not "
    "exist at compile time, and compile() may not perform I/O. "
    "(decision-135)"
)

_CONNECT_PROXY_SEATBELT_RATIONALE: Final[str] = (
    "seatbelt composes outer, connect_proxy inner. The same reason "
    "seatbelt is outer of env_scrub: the /bin/sh -c the wrap spawns to "
    "wait for the port file and export the proxy variables must run "
    "INSIDE the SBPL profile, not unconfined outside it. This is also "
    "what makes a transport-confinement pairing coherent -- a seatbelt "
    "rule that denies outbound except the proxy's loopback port can only "
    "bind a workload whose whole exec chain is already inside the "
    "profile. Note the asymmetry that makes the pairing work at all: the "
    "proxy HELPER is not wrapped by anything (see "
    "_CONNECT_PROXY_HELPER_NOTE), so it reaches upstream while the "
    "workload it filters for cannot. (decision-135)"
)

_CONNECT_PROXY_RLIMITS_RATIONALE: Final[str] = (
    "rlimits composes outermost, connect_proxy inner -- rlimits is "
    "outermost against every mechanism, so that its caps bound the other "
    "mechanisms' own pre-exec images rather than only the final workload. "
    "connect_proxy adds a /bin/sh that polls for a port file, which is "
    "exactly the kind of pre-exec image an unbounded stack would leave "
    "uncapped. (decision-135)"
)

#: decision-135 (4): a `Step.helpers` process is spawned by
#: `run.launcher._start_helpers` as `list(helper.argv)` directly, while only
#: the workload is spawned as `wrapped_argv`. A helper therefore passes
#: through NO mechanism's wrap, whatever this matrix says -- which is what
#: lets connect_proxy's proxy reach upstream while seatbelt denies the
#: workload's network. No matrix entry can protect that property, because it
#: belongs to the launcher and not to the ordering; it is pinned by
#: `tests/unit/test_connect_proxy_helper_unwrapped.py` instead.
_CONNECT_PROXY_HELPER_NOTE: Final[str] = (
    "helpers are launched unwrapped by run.launcher._start_helpers; "
    "composition order does not reach them (decision-135)"
)

#: SPEC.md §7 step 3: "a literal, versioned matrix of (mechanism, mechanism)
#: pairs with an *ordering rationale* string per pair... Unknown pairs are
#: refused." M3 shipped the first real pair, `{env_scrub, rlimits}`, ordered
#: `rlimits` outermost. task-059 (M5-lite) adds `seatbelt`'s two pairs,
#: completing the triangle across all three mechanisms that exist as of this
#: milestone. Keyed by an unordered frozenset of the two mechanism names --
#: the directional information (which one is `outer`) lives in the
#: `MatrixEntry` value, not the key, per this module's docstring.
#: bwrap's four rows (2026-09-08, decision-159). Two of them order a
#: pairing that composes -- `strict_linux()`'s own -- and two record a
#: pairing that CANNOT, which the matrix must still carry because
#: `Stack.compile` refuses an unknown pair and `tests/unit/test_m6_shape.py`
#: pins the square across every mechanism that exists as total.
#:
#: **`{bwrap, rlimits}` -- `rlimits` outermost.** SPEC.md sec 7's own reason,
#: made concrete for this pair, and the same one every other `rlimits` row
#: carries: the limiter wraps outermost so the cpu cap also bounds the
#: OTHER mechanism's own process -- here `bwrap` itself, which does real
#: work (unsharing namespaces, building a mount tree) before the workload
#: exists at all. `RLIMIT_CPU` is set by the trampoline on itself and a
#: POSIX rlimit is inherited across `exec` AND across the namespaces bwrap
#: then creates, so one `setrlimit` before the first exec stays in force
#: through every later image in that pid: trampoline (sets the limit) ->
#: exec into `bwrap` (still capped) -> bwrap execs the jailed workload
#: (still capped). Reversing the order would leave bwrap's own mount setup
#: uncapped.
_BWRAP_RLIMITS_RATIONALE: Final[str] = (
    "rlimits composes outermost, bwrap inner. SPEC.md sec 7's own reason, "
    "made concrete: the limiter wraps outermost so the cpu cap also bounds "
    "the OTHER mechanism's own process -- here bwrap itself, which unshares "
    "namespaces and builds a whole mount tree before the workload exists. "
    "Because RLIMIT_CPU is set by the trampoline on itself and a POSIX "
    "rlimit is inherited across exec, and across the namespaces bwrap then "
    "creates, one setrlimit before the first exec stays in force through "
    "every later image in the same pid: trampoline (sets the limit) -> exec "
    "into bwrap (still capped) -> bwrap execs the jailed workload (still "
    "capped). Reversing the order would leave bwrap's own mount setup "
    "uncapped."
)

#: **`{bwrap, env_scrub}` -- `bwrap` outermost.** The identical shape as
#: `{seatbelt, env_scrub}`, and it bites harder here: env_scrub's wrap is
#: `/bin/sh -c 'exec /usr/bin/env -i ... "$@"'`, so with bwrap outer those
#: two pre-exec images run INSIDE the jail's mount namespace, confined the
#: same as the workload. Reversing the order would exec `/bin/sh` and
#: `/usr/bin/env` on the HOST, unconfined, before bwrap ever ran -- not
#: merely uncapped, as in the rlimits pair, but outside the jail entirely.
#: The consequence a reader must check rather than assume: with bwrap
#: outer, `/bin/sh` and `/usr/bin/env` must EXIST INSIDE the jail, which
#: under an allowlist read model means the spec has to grant them (see
#: `strict_linux`'s own docstring, which states this as a precondition of
#: the preset rather than leaving it to be discovered at launch).
_BWRAP_ENV_SCRUB_RATIONALE: Final[str] = (
    "bwrap composes outer, env_scrub inner. So that the env-constructing "
    "/bin/sh -c 'exec env -i ...' and /usr/bin/env processes themselves run "
    "INSIDE the jail's mount and network namespaces, not unconfined outside "
    "them: bwrap wraps the whole exec chain. Reversing the order would exec "
    "/bin/sh and /usr/bin/env on the host, before bwrap ran at all, so "
    "those two images would be outside the jail entirely and only the final "
    "workload image would be confined. env_scrub inner is also what makes "
    "its env -i reach the workload with nothing between them to re-add what "
    "it removed. The precondition this ordering creates, named rather than "
    "assumed: /bin/sh and /usr/bin/env must exist inside the jail, which "
    "under bwrap's allowlist read model means the spec must grant them."
)

#: **`{bwrap, seatbelt}` -- unreachable, recorded for totality.** The two
#: claim the SAME three axes (`fs_read`, `fs_write`, `network`), so
#: `Stack.compile` step 1 raises `AxisClaimConflict` on any stack holding
#: both, BEFORE the matrix is consulted; and they target different
#: platforms, each refusing the other's (`PlatformUnsupported`). `outer`
#: cannot be empty, and it names `bwrap` because a mount-namespace creator
#: is the only one of the two that could meaningfully contain the other --
#: but that is a note on an ordering nothing can reach, not a plan.
_BWRAP_SEATBELT_RATIONALE: Final[str] = (
    "UNREACHABLE PAIR, recorded so the matrix stays total. bwrap and "
    "seatbelt claim the same three axes (fs_read, fs_write, network), so "
    "Stack.compile's claim step raises AxisClaimConflict on any stack "
    "holding both, before this row is ever read; and they refuse each "
    "other's platform besides. outer names bwrap because a mount-namespace "
    "creator is the only one of the two that could contain the other, not "
    "because any stack will ever compose them."
)

#: **`{bwrap, connect_proxy}` -- unreachable today, recorded for totality
#: and for the mechanism that would change it.** Same claim conflict:
#: `bwrap` claims `network` outright (deny-all by netns) and so does
#: `connect_proxy`. A ceding `bwrap` -- the linux analogue of
#: `Seatbelt(cedes_network=True)` -- is not enough on its own either: an
#: unshared netns has no route to a proxy listening on the host's loopback,
#: which is why SPEC.md sec 6's roster pairs bwrap with `connect_proxy`
#: *in-netns* or with `pasta`. The ordering recorded is the one that would
#: hold then, for the same reason as `{bwrap, env_scrub}`: the `/bin/sh`
#: connect_proxy's wrap spawns must run inside the jail.
_BWRAP_CONNECT_PROXY_RATIONALE: Final[str] = (
    "UNREACHABLE PAIR today, recorded so the matrix stays total. bwrap "
    "claims network (deny-all by unshared netns) and so does connect_proxy, "
    "so Stack.compile's claim step raises AxisClaimConflict before this row "
    "is read. A ceding bwrap would not be enough by itself: a workload in "
    "an unshared network namespace has no route to a proxy on the host's "
    "loopback, so the pairing needs a mechanism that puts networking back "
    "inside the namespace (pasta or slirp4netns, SPEC.md sec 6's roster). "
    "The ordering recorded -- bwrap outer, connect_proxy inner -- is the "
    "one that would hold then, for the same reason as {bwrap, env_scrub}: "
    "the /bin/sh connect_proxy's wrap spawns to wait for the port file must "
    "run inside the jail."
)

#: Mechanism names the stack layer reasons about by name. Written as
#: constants because `_raise_network_for_observed_pairing` matches on them
#: and a typo there would silently stop raising the grade.
_CONNECT_PROXY_NAME: Final[str] = "connect_proxy"
_SEATBELT_NAME: Final[str] = "seatbelt"

MATRIX_VERSION: Final[int] = 5
COMPATIBILITY_MATRIX: Mapping[frozenset[str], MatrixEntry] = MappingProxyType(
    {
        frozenset({"bwrap", "rlimits"}): MatrixEntry(
            outer="rlimits", rationale=_BWRAP_RLIMITS_RATIONALE
        ),
        frozenset({"bwrap", "env_scrub"}): MatrixEntry(
            outer="bwrap", rationale=_BWRAP_ENV_SCRUB_RATIONALE
        ),
        frozenset({"bwrap", "seatbelt"}): MatrixEntry(
            outer="bwrap", rationale=_BWRAP_SEATBELT_RATIONALE
        ),
        frozenset({"bwrap", "connect_proxy"}): MatrixEntry(
            outer="bwrap", rationale=_BWRAP_CONNECT_PROXY_RATIONALE
        ),
        frozenset({"env_scrub", "rlimits"}): MatrixEntry(
            outer="rlimits", rationale=_ENV_SCRUB_RLIMITS_RATIONALE
        ),
        frozenset({"rlimits", "seatbelt"}): MatrixEntry(
            outer="rlimits", rationale=_RLIMITS_SEATBELT_RATIONALE
        ),
        frozenset({"seatbelt", "env_scrub"}): MatrixEntry(
            outer="seatbelt", rationale=_SEATBELT_ENV_SCRUB_RATIONALE
        ),
        frozenset({"connect_proxy", "env_scrub"}): MatrixEntry(
            outer="env_scrub", rationale=_CONNECT_PROXY_ENV_SCRUB_RATIONALE
        ),
        frozenset({"connect_proxy", "seatbelt"}): MatrixEntry(
            outer="seatbelt", rationale=_CONNECT_PROXY_SEATBELT_RATIONALE
        ),
        frozenset({"connect_proxy", "rlimits"}): MatrixEntry(
            outer="rlimits", rationale=_CONNECT_PROXY_RLIMITS_RATIONALE
        ),
    }
)


class AxisClaimConflict(ValueError):
    """Two mechanisms in a Stack claim the same axis.

    SPEC.md §7 step 1: "every axis claimed by at most one mechanism. Overlap
    is a compile error, not a grading question."
    """

    def __init__(self, axis: Axis, mechanism_a: str, mechanism_b: str) -> None:
        self.axis = axis
        self.mechanism_a = mechanism_a
        self.mechanism_b = mechanism_b
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"axis {self.axis.value!r} is claimed by both mechanisms "
            f"{self.mechanism_a!r} and {self.mechanism_b!r}"
        )


class CompatibilityRefused(ValueError):
    """A Stack contains a mechanism pair absent from the compatibility matrix.

    SPEC.md §7 step 3: "Unknown pairs are refused."
    """

    def __init__(self, mechanism_a: str, mechanism_b: str, matrix_version: int) -> None:
        self.mechanism_a = mechanism_a
        self.mechanism_b = mechanism_b
        self.matrix_version = matrix_version
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"no compatibility matrix entry (v{self.matrix_version}) for the "
            f"pair ({self.mechanism_a!r}, {self.mechanism_b!r}); unknown "
            "pairs are refused"
        )


class EnvConflict(ValueError):
    """Two mechanisms declared different values for the same env variable.

    SPEC.md §7 Composition: "env merges with later-wins declared conflicts
    as errors."
    """

    def __init__(
        self,
        name: str,
        mechanism_a: str,
        value_a: str,
        mechanism_b: str,
        value_b: str,
    ) -> None:
        self.name = name
        self.mechanism_a = mechanism_a
        self.value_a = value_a
        self.mechanism_b = mechanism_b
        self.value_b = value_b
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"env var {self.name!r} is set to conflicting values by "
            f"{self.mechanism_a!r} ({self.value_a!r}) and "
            f"{self.mechanism_b!r} ({self.value_b!r})"
        )


@dataclass(frozen=True, slots=True)
class CompiledJail:
    """The output of `Stack.compile`.

    SPEC.md §7 names this type in `Stack(mechanisms).compile(spec, floors)
    -> CompiledJail` but never defines it (ambiguity A4 in the M2 plan).
    Ships exactly the fields the launcher and the report need, no more.

    `signatures` (task-047) is the `SignatureBook` assembled alongside
    `report` in the SAME pass over `steps` -- one `AxisClaim` per axis in
    a mechanism's compiled `Step.grades` (task-044's key set, NOT
    `mechanism.axes`), carrying that mechanism's `name` and its `Step`'s
    `denial_signatures`. An axis no mechanism claims for this spec has no
    claim in the book at all (`for_axis` returns `None`), the same way it
    has no overlay in `report` and falls to `unenforced_report()`'s fill.
    Defaults to the empty book (no construction site outside `Stack.compile`
    populates one) so a pre-task-047 `CompiledJail(...)` call site --
    several exist across `tests/integration/`, none of them this task's
    Deliverable -- keeps compiling unchanged, same idiom as `mech.Step`'s
    own `events: EventSource | None = None`.

    `sensors` (decision-152, 2026-09-08) is every non-`None` `Step.events`
    from this compile, in `steps` order. It exists because `run` is the only
    layer permitted to CALL a sensor (SPEC.md §6) and, until this ruling,
    had no way to reach one: `Step.events` was assembled by every mechanism
    that had a sensor and then dropped on the floor here -- the
    declared-but-never-used shape this library refuses, hiding in the
    library's own composition step. A `Launcher` now stamps
    `known_at_compile()` from this tuple and hands the same tuple to the
    exit waiter for `classify_exit()`. Defaults to the empty tuple, same
    reason `signatures` defaults to the empty book."""

    spec: Spec
    report: EnforcementReport
    wrap: ArgvTransformer
    env: Mapping[str, str]
    staged: tuple[StagedFile, ...]
    helpers: tuple[Helper, ...]
    requires: frozenset[LaunchFeature]
    mechanism_names: tuple[str, ...]
    matrix_version: int
    signatures: SignatureBook = field(default_factory=lambda: SignatureBook(claims=()))
    sensors: tuple[EventSource, ...] = ()

    def __post_init__(self) -> None:
        # Defensive copy: prevent caller mutation of the source mapping from
        # affecting this CompiledJail (same idiom as mech.Step.env).
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


def _identity(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


@dataclass(frozen=True, slots=True)
class Stack:
    """An ordered composition of mechanisms (SPEC.md §3, §7).

    Frozen and validated at construction: a duplicate mechanism *name*
    raises ValueError immediately, before `compile` is ever called.

    >>> Stack([])  # the empty stack is always valid (SPEC.md §3)
    """

    mechanisms: tuple[Mechanism, ...]

    def __init__(self, mechanisms: Sequence[Mechanism]) -> None:
        object.__setattr__(self, "mechanisms", tuple(mechanisms))
        seen: set[str] = set()
        for mechanism in self.mechanisms:
            if mechanism.name in seen:
                raise ValueError(
                    f"duplicate mechanism name {mechanism.name!r} in Stack; "
                    "every mechanism in a Stack must have a distinct name"
                )
            seen.add(mechanism.name)

    def compile(
        self,
        spec: Spec,
        floors: Floors | None = None,
        *,
        ctx: CompileCtx | None = None,
    ) -> CompiledJail:
        """Compile `spec` through this stack's mechanisms.

        SPEC.md §7, validation in order:

        1. Claims -- every axis claimed by at most one mechanism.
        2. Coverage -- every axis either claimed or `unenforced`.
        3. Compatibility & ordering -- every mechanism pair known to the
           compatibility matrix; unknown pairs are refused.
        4. Floors -- the aggregate report meets `floors` or the compile
           refuses, naming the axis and the shortfall.

        `floors` is optional and defaults to no floors (SPEC.md §7 writes
        `compile(spec, floors)`; MILESTONES.md M2's goal writes
        `Stack([]).compile(spec)` -- ambiguity A6 in the M2 plan, resolved
        by making `floors` optional so both spellings are true).
        """
        if floors is None:
            floors = Floors()

        # --- 1. Claims -----------------------------------------------
        # Every axis claimed by at most one mechanism. This uses only each
        # mechanism's declared `axes`, never its compiled Step -- so claims
        # can be, and is, checked before any mechanism.compile() runs and
        # before compatibility or floors are evaluated.
        axis_owner: dict[Axis, str] = {}
        for mechanism in self.mechanisms:
            for axis in mechanism.axes:
                owner = axis_owner.get(axis)
                if owner is not None:
                    raise AxisClaimConflict(
                        axis=axis, mechanism_a=owner, mechanism_b=mechanism.name
                    )
                axis_owner[axis] = mechanism.name

        # --- 2. Coverage -----------------------------------------------
        # SPEC.md §7: "Coverage is a construction-time invariant, not a step
        # anyone can forget." EnforcementReport refuses to construct with a
        # missing axis, so there is nothing further to check here: every
        # axis in AXES is either in axis_owner (claimed, step 1 above) or is
        # filled from core.unenforced_report() below. Axis is a closed Enum,
        # so this is always true; the assertion documents the invariant
        # rather than guarding against a real failure mode.
        assert frozenset(axis_owner) <= frozenset(AXES)

        # --- 3. Compatibility & ordering ---------------------------------
        # A literal, versioned matrix of (mechanism, mechanism) pairs.
        # Unknown pairs are refused -- with M2's zero-pair matrix, EVERY
        # stack of two or more mechanisms was refused here; M3's one real
        # pair ({env_scrub, rlimits}) is the first that can compile. Read
        # COMPATIBILITY_MATRIX as a module global (not a default argument or
        # a value captured at import time) so it reflects the matrix in
        # force at call time. Every known pair's MatrixEntry is collected
        # into `pair_entries` here, in the SAME pass, for `_ordered_for_
        # composition` below -- so a pair looked up once as "known" is
        # never looked up a second time to learn its ordering.
        names = tuple(mechanism.name for mechanism in self.mechanisms)
        pair_entries: dict[frozenset[str], MatrixEntry] = {}
        for i in range(len(self.mechanisms)):
            for j in range(i + 1, len(self.mechanisms)):
                a, b = self.mechanisms[i], self.mechanisms[j]
                pair = frozenset((a.name, b.name))
                entry = COMPATIBILITY_MATRIX.get(pair)
                if entry is None:
                    raise CompatibilityRefused(a.name, b.name, MATRIX_VERSION)
                pair_entries[pair] = entry

        # --- Compile each mechanism's Step, then compose ----------------
        if ctx is None:
            # M2 has zero real mechanisms; this placeholder is never
            # inspected by anything shipping in this milestone. A real
            # jail_dir/platform arrives with the launcher that needs one.
            ctx = CompileCtx(jail_dir="", platform="")
        steps: list[tuple[Mechanism, Step]] = [
            (mechanism, mechanism.compile(spec, ctx)) for mechanism in self.mechanisms
        ]

        # Composition order is decided by the matrix's `outer` field, never
        # by `self.mechanisms`' own construction order (SPEC.md §7
        # Composition: "argv wrappers compose inside-out per the matrix
        # ordering") -- task-037 AC #2. Only wrap composition needs this
        # reordering; env/staged/helpers/requires/grades below are
        # commutative (union, or an explicit conflict check) so they use
        # `steps` in `self.mechanisms`' own order, unchanged.
        wrap = _compose(_ordered_for_composition(steps, pair_entries))

        env: dict[str, str] = {}
        env_owner: dict[str, str] = {}
        for mechanism, step in steps:
            for name, value in step.env.items():
                existing = env.get(name)
                if existing is not None and existing != value:
                    raise EnvConflict(
                        name=name,
                        mechanism_a=env_owner[name],
                        value_a=existing,
                        mechanism_b=mechanism.name,
                        value_b=value,
                    )
                env[name] = value
                env_owner[name] = mechanism.name

        staged = tuple(sf for _, step in steps for sf in step.staged)
        helpers = tuple(h for _, step in steps for h in step.helpers)
        requires: frozenset[LaunchFeature] = frozenset()
        for _, step in steps:
            requires = requires | step.requires

        # Build the aggregate report: start from core.unenforced_report()'s
        # all-seven-axes-UNENFORCED fill (SPEC.md §3: "the empty stack ...
        # grades every axis unenforced") rather than re-deriving it, then
        # overlay each mechanism's OWN claimed axes -- the key set of its
        # compiled Step.grades, per SPEC.md §6 / decision-092 (P-12): "what
        # [a mechanism] DOES claim for a given Spec is the key set of its
        # compiled Step.grades, and the two need not be equal" to `axes`.
        # A mechanism with nothing to grade for this spec (env_scrub under
        # PASS is the motivating case) simply contributes no overlay, and
        # the axis stays UNENFORCED from the fill above -- exactly like an
        # axis no mechanism declared at all.
        #
        # The ceiling still holds, checked here rather than left implicit:
        # SPEC.md §6 says "a Step may not grade an axis outside its
        # mechanism's declared axes (the declaration is a ceiling, not a
        # hint)". `axes` is a static declaration and stays the input to
        # step 1's claim-conflict check above; this is the second half of
        # the same sentence, enforced against what the Step actually
        # grades.
        # The signature book is assembled in the SAME pass, over the SAME
        # key set, as the aggregate report just below -- one `AxisClaim`
        # per axis actually present in a mechanism's compiled
        # `step.grades` (task-044's key set), never from `mechanism.axes`
        # (SPEC.md §12: the probe engine matches the CLAIMING mechanism's
        # `denial_signatures`, and a mechanism that claims nothing for this
        # spec -- env_scrub under PASS -- has nothing to claim here either).
        # `denial_signatures` is carried through UNCHANGED, including the
        # empty tuple `env_scrub` declares under SCRUB: an empty signatures
        # tuple on a present claim is a routing fact for task-050
        # (decision-067), not a gap this task papers over with a generic
        # pattern.
        grades: dict[Axis, Graded] = dict(unenforced_report().axes)
        claims: list[AxisClaim] = []
        for mechanism, step in steps:
            for axis, graded in step.grades.items():
                if axis not in mechanism.axes:
                    declared = sorted(a.value for a in mechanism.axes)
                    raise ValueError(
                        f"mechanism {mechanism.name!r} graded axis "
                        f"{axis.value!r}, which is outside its declared "
                        f"axes {declared!r} (SPEC.md §6: the declaration "
                        "is a ceiling, not a hint)"
                    )
                grades[axis] = graded
                claims.append(
                    AxisClaim(
                        axis=axis,
                        mechanism=mechanism.name,
                        signatures=step.denial_signatures,
                    )
                )
        # --- 3b. The observed pairing ----------------------------------
        # task-079 / decision-136. The ONE place that may raise the network
        # grade, because it is the only one that can see the pairing:
        # `connect_proxy.compile()` is a pure function of one Spec and
        # decision-134's first sub-ruling forbids it grading from a hope
        # about composition. `Stack.compile` is not guessing -- it holds
        # both mechanisms.
        claims = _raise_network_for_observed_pairing(grades, claims, steps)

        report = EnforcementReport(axes=grades)
        signatures = SignatureBook(claims=tuple(claims))

        # --- 4. Floors -----------------------------------------------
        report.check_floors(floors)  # raises FloorViolation naming shortfalls

        return CompiledJail(
            spec=spec,
            report=report,
            wrap=wrap,
            env=env,
            staged=staged,
            helpers=helpers,
            requires=requires,
            mechanism_names=names,
            matrix_version=MATRIX_VERSION,
            signatures=signatures,
            sensors=tuple(step.events for _, step in steps if step.events is not None),
        )


#: The grade a confined `connect_proxy` reaches, and no further. `ENFORCED`
#: is unreachable for this pairing by construction, for two independent
#: reasons named in the detail below; the ceiling is written as a constant so
#: that raising it takes an edit here rather than a plausible-looking
#: argument at a call site.
_PAIRED_NETWORK_CEILING: Final[Grade] = Grade.BEST_EFFORT

_PAIRED_NETWORK_DETAIL: Final[str] = (
    "egress filtered by connect_proxy AND the workload's transport confined "
    "by a ceding seatbelt, observed together by Stack.compile -- so ignoring "
    "HTTP_PROXY no longer reaches the network. Two gaps keep this off "
    "enforced, and both are real: (1) the filter binds the host the client "
    "ASKED for, so a permitted host co-hosted with a forbidden one on the "
    "same address is reachable inside an opened tunnel (SNI co-hosting, "
    "decision-134); (2) the seatbelt allowance is loopback-WIDE and not "
    "port-scoped -- the proxy binds port 0, so no port is knowable when the "
    "profile is rendered -- so the workload can reach ANY loopback service "
    "on the host, not only its own proxy (decision-136)."
)


def _raise_network_for_observed_pairing(
    grades: dict[Axis, Graded],
    claims: list[AxisClaim],
    steps: Sequence[tuple[Mechanism, Step]],
) -> list[AxisClaim]:
    """Raise `network` to `best_effort` when the confinement pairing is
    actually present. Mutates `grades` in place; a no-op otherwise.

    task-079 AC#4, and the reason this lives at the stack layer at all: the
    roster row offers `best_effort` "when paired with an enforced transport
    confinement", and only something holding every mechanism can tell whether
    such a pairing exists. decision-134 sub-ruling 1 stands untouched --
    `connect_proxy` still self-grades `cooperative`, and this never reaches
    back into that mechanism to change what it said.

    **Three conditions, all required, and each is load-bearing:**

    1. `network` is currently graded `cooperative`. Anything else is either
       an axis nobody claimed (nothing to raise) or a grade some other
       mechanism owns (not ours to touch). This is also what makes the
       function idempotent.
    2. A `seatbelt` is present that has CEDED the network axis. Per
       decision-136 a ceding seatbelt is exactly the one that emitted the
       loopback-only allowance, so its presence IS the confinement -- while a
       seatbelt still claiming `network` would have denied the proxy hop and
       could not have composed with `connect_proxy` at all.
    3. The mechanism actually claiming `network` is `connect_proxy`. Raising
       some future mechanism's grade on its behalf, using an argument written
       for this one, is the grade-up this codebase keeps catching.

    **Never reaches `enforced`** (`_PAIRED_NETWORK_CEILING`), and the detail
    names BOTH gaps rather than only the SNI one, because the loopback-wide
    allowance decision-136 (4) forced is a second, independent hole.
    """
    graded = grades.get(Axis.NETWORK)
    if graded is None or graded.grade is not Grade.COOPERATIVE:
        return claims

    mechanisms = [mechanism for mechanism, _ in steps]
    claimant = next((m.name for m in mechanisms if Axis.NETWORK in m.axes), None)
    if claimant != _CONNECT_PROXY_NAME:
        return claims

    ceding = next(
        (
            step
            for mechanism, step in steps
            if mechanism.name == _SEATBELT_NAME and Axis.NETWORK not in mechanism.axes
        ),
        None,
    )
    if ceding is None:
        return claims

    grades[Axis.NETWORK] = Graded(_PAIRED_NETWORK_CEILING, _PAIRED_NETWORK_DETAIL)

    # decision-142: the ceding mechanism SIGNS the axis it does not claim.
    # The two deny different things and both are real -- connect_proxy
    # refuses a host off the allow list (its own 403 prefix), seatbelt
    # refuses any direct connection that bypasses the proxy at all. A DENIAL
    # probe deliberately takes the unsanctioned path (decision-141), so it
    # meets SEATBELT's refusal, never connect_proxy's. Without this merge the
    # engine reports VACUOUS -- "failed, but no signature declared by
    # 'connect_proxy' matched" -- in exactly the configuration where the
    # denial is strongest.
    #
    # Claiming and signing are separated on purpose: SPEC.md §7 step 1's
    # one-claimant rule is about GRADES, and a signature set is not a grade.
    # Scoped hard -- only a mechanism that ceded THIS axis, only when the
    # pairing is observed -- so it cannot become a way for any mechanism to
    # inject signatures into any axis.
    return [
        AxisClaim(
            axis=claim.axis,
            mechanism=claim.mechanism,
            signatures=(*claim.signatures, *ceding.denial_signatures),
        )
        if claim.axis is Axis.NETWORK and claim.mechanism == _CONNECT_PROXY_NAME
        else claim
        for claim in claims
    ]


def _ordered_for_composition(
    steps: Sequence[tuple[Mechanism, Step]],
    pair_entries: Mapping[frozenset[str], MatrixEntry],
) -> tuple[tuple[Mechanism, Step], ...]:
    """Reorder `steps` inner-to-outer per the compatibility matrix's
    per-pair `MatrixEntry.outer`, so feeding this order to `_compose`
    below composes argv wrappers outside-in the way SPEC.md §7 Composition
    requires -- REGARDLESS of the order mechanisms were passed to
    `Stack(...)` (task-037 AC #2: "the matrix decides ordering, not the
    list order"). Every pair among `steps` is already validated present in
    `pair_entries` by `Stack.compile`'s compatibility step, run
    immediately before this is called, so this never raises.

    Built as a plain directed graph plus topological sort
    (`graphlib.TopologicalSorter`, stdlib -- pure, no I/O): each known pair
    contributes one edge, `outer -> inner`, meaning "outer must be applied
    AFTER inner". `TopologicalSorter.static_order()` yields a node only
    after every one of its graph-predecessors, so an inner mechanism
    always surfaces before the outer one that depends on it -- exactly the
    application order `_compose` needs, per its own docstring: applying a
    Step's `wrap` LAST makes it the OUTERMOST layer of the composed argv.
    Generalizes past two mechanisms on purpose (a third mechanism's pairs
    would contribute more edges to the same graph) even though M3 ships
    exactly one pair; the empty-stack and single-mechanism cases fall out
    of the same code with zero edges, needing no separate branch.
    """
    by_name = {mechanism.name: (mechanism, step) for mechanism, step in steps}
    graph: dict[str, set[str]] = {name: set() for name in by_name}
    names = tuple(by_name)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            entry = pair_entries[frozenset((names[i], names[j]))]
            inner = names[j] if entry.outer == names[i] else names[i]
            graph[entry.outer].add(inner)
    order = tuple(TopologicalSorter(graph).static_order())
    return tuple(by_name[name] for name in order)


def _compose(steps: Sequence[tuple[Mechanism, Step]]) -> ArgvTransformer:
    """Compose the mechanisms' argv wrappers, inside-out, in EXACTLY the
    order `steps` is given.

    SPEC.md §7 Composition: "argv wrappers compose inside-out per the
    matrix ordering." This function itself only ever applies `steps` in
    the order it receives them -- `Stack.compile` is what makes that order
    matrix-derived, by calling `_ordered_for_composition` before handing
    `steps` here, never `self.mechanisms`' own construction order. With
    zero mechanisms this is the identity transform (needed for AC#8); with
    exactly one it is that mechanism's `wrap` unchanged.
    """
    if not steps:
        return _identity

    def composed(argv: tuple[str, ...]) -> tuple[str, ...]:
        result = argv
        for _, step in steps:
            result = step.wrap(result)
        return result

    return composed


def degraded() -> Stack:
    """The `degraded()` preset (SPEC.md §7, task-039): "the no-jail-tech
    jail, honestly graded."

    SPEC.md §7 defines `degraded()` as three mechanisms, verbatim:
    `[env_scrub, rlimits, connect_proxy(env-routed)]`. `connect_proxy` does
    not exist until M6 -- RULED by decision-062 (operator round 7, A3
    accepted): no stub proxy, per SPEC.md §2 law 2 (a mechanism that
    cannot deliver refuses; it does not pretend). So as of M3 this preset
    ships the **two** mechanisms that exist, `rlimits` and `env_scrub`, in
    the compatibility matrix's own ordering (`COMPATIBILITY_MATRIX`'s
    `{env_scrub, rlimits}` entry, task-037: `rlimits` outermost) -- written
    in that order here for a reader's benefit only, since `Stack.compile`
    derives composition order from the matrix's `outer` field, never from
    this list's order (this module's own docstring).

    **This preset's `network` axis grades honestly `unenforced` until
    M6.** Neither mechanism here claims `Axis.NETWORK`, so it enters the
    compiled report the same way every unclaimed axis does -- via
    `unenforced_report()`'s fill in `Stack.compile`, never asserted here.
    When M6 adds `connect_proxy` to this preset, the network axis moves
    off `unenforced` and the golden report in
    `tests/unit/test_stack_degraded_preset.py` changes with it -- that
    golden is versioned specifically so that change is a visible, reviewed
    diff at M6, not a silent one (decision-062's second half).

    Data, not a factory with logic: this function applies no conditional
    and computes no ordering -- it is a two-element list literal.
    Everything that makes the report and the composed argv what they are
    (which axes are covered, what `limits` and `network` grade, which
    mechanism wraps outermost) lives in `rlimits`/`env_scrub` themselves
    and in `COMPATIBILITY_MATRIX`, not here.
    """
    return Stack([rlimits, env_scrub])


def scratch_darwin() -> Stack:
    """The `scratch_darwin()` preset (SPEC.md §7, task-064): "a kernel-enforced
    scratch jail on darwin, the smallest stack that reaches `enforced` on
    `fs_read`, `fs_write`, `network` and `env` while `limits` stays `best_effort`."

    SPEC.md §7 defines `scratch_darwin()` as three mechanisms, verbatim:
    `[rlimits, seatbelt, env_scrub]`. The composition order is fixed by
    SPEC.md's security reasoning (RULED by decision-119 from doc-017's
    ambiguity A4): `rlimits` outermost so it bounds the other mechanisms'
    helper processes, `seatbelt` next so the `/bin/sh` and `/usr/bin/env`
    that `env_scrub`'s wrap spawns run inside the profile, and `env_scrub`
    innermost so its `env -i` reaches the workload with nothing between them
    to re-add what it removed. This ordering is enforced in the
    compatibility matrix (`COMPATIBILITY_MATRIX`'s entries for
    `{rlimits, seatbelt}`, `{seatbelt, env_scrub}`, and `{env_scrub, rlimits}`),
    so `Stack.compile` derives the order from the matrix's `outer` field,
    never from this list's order (this module's own docstring).

    **This preset reaches `enforced` on four axes:** `fs_read` and `fs_write`
    from `seatbelt` (SPEC.md §6's kernel-enforced sandbox), `network` from
    `seatbelt` (which denies all network by default), and `env` from
    `env_scrub` (which removes all vars except the allowlist under SCRUB
    mode). `limits` stays `best_effort` because `rlimits` reaches only cpu
    (RLIMIT_CPU) and cannot enforce memory, tasks, wall-clock or output
    limits (M3's EC2, decision-061). `channel_exclusivity` and `control`
    are unclaimed and grade `unenforced` via `unenforced_report()`'s fill
    in `Stack.compile`.

    Data, not a factory with logic: this function applies no conditional
    and computes no ordering -- it is a three-element list literal.
    Everything that makes the report and the composed argv what they are
    (which axes are covered, which mechanism wraps outermost) lives in
    `rlimits`, `seatbelt`, and `env_scrub` themselves and in
    `COMPATIBILITY_MATRIX`, not here.
    """
    return Stack([rlimits, seatbelt, env_scrub])


def strict_linux() -> Stack:
    """The `strict_linux()` preset (SPEC.md sec 7, decision-159): a
    kernel-enforced jail on linux -- the smallest stack that reaches
    `enforced` on `fs_read`, `fs_write` and `network` there, and the linux
    sibling of `scratch_darwin()`.

    Three mechanisms: `[bwrap, rlimits, env_scrub]`. The composition order
    is the matrix's, not this list's (this module's own docstring):
    outermost to innermost, `rlimits`, `bwrap`, `env_scrub` -- `rlimits`
    outermost so its cpu cap bounds bwrap's own namespace and mount setup,
    `bwrap` next so the `/bin/sh` and `/usr/bin/env` that `env_scrub`'s wrap
    spawns run INSIDE the jail rather than unconfined on the host, and
    `env_scrub` innermost so its `env -i` reaches the workload with nothing
    between them to re-add what it removed. All three orderings are the
    compatibility matrix's `{bwrap, rlimits}`, `{bwrap, env_scrub}` and
    `{env_scrub, rlimits}` rows, each with its own rationale.

    **It is NOT SPEC.md sec 7's `strict()`, and the name says so
    deliberately.** `strict()` is defined there as linux `[bwrap,
    systemd_scope, pasta]`; neither `systemd_scope` nor `pasta` exists, and
    shipping a two-mechanism stack under that name would be the silent
    substitution law 2 forbids. What this preset gives up against `strict()`
    is exactly those two mechanisms' axes: `limits` stays `best_effort`
    (`rlimits` reaches cpu only -- memory, tasks, wall and output are
    `systemd_scope`'s, decision-061), and `network` is deny-ALL rather than
    filtered (`pasta` plus `connect_proxy` is what would grant a domain).
    `channel_exclusivity` and `control` are unclaimed and grade
    `unenforced` via `unenforced_report()`'s fill in `Stack.compile`.

    **Two preconditions this preset does not enforce and will not hide.**
    `bwrap` is an ALLOWLIST mechanism (SPEC.md sec 5), so:

    1. The Spec must be `ReadModel.ALLOW_LIST`. A denylist Spec compiled
       through this preset is refused by name (`ReadModelUnsupported`),
       never quietly translated.
    2. Its `read_allows` must cover `/bin/sh` and `/usr/bin/env`, because
       `env_scrub` composes INSIDE the jail and those two images are what
       its wrap execs. A Spec that grants a workspace and nothing else
       compiles cleanly here and produces a jail whose workload cannot
       start -- so this sentence is the warning, and the preset does not
       fabricate mounts nobody asked for to paper over it.

    Data, not a factory with logic: a three-element list literal, like
    every other preset here. Everything that decides the report and the
    composed argv lives in the mechanisms and in `COMPATIBILITY_MATRIX`.

    Linux only: it composes `bwrap`, which refuses any other platform.
    """
    return Stack([bwrap, rlimits, env_scrub])


def confined_egress_darwin(python: str) -> Stack:
    """The `confined_egress_darwin(python)` preset (decision-137): filtered
    egress whose transport is actually confined.

    Four mechanisms: `[rlimits, Seatbelt(cedes_network=True), env_scrub,
    connect_proxy]`. It exists as its OWN preset rather than as a flag on
    `scratch_darwin()` because the two differ in which mechanisms they
    contain and in which one owns `Axis.NETWORK` -- a different stack, not a
    parameterised one -- and because presets here are data, not factories
    with logic (decision-137 (3)).

    **`network` grades `best_effort`, raised by the observer, never by a
    mechanism.** `connect_proxy` self-grades `cooperative` (decision-134);
    `Stack.compile`'s `_raise_network_for_observed_pairing` sees the ceding
    seatbelt alongside it and raises. It never reaches `enforced`, and the
    detail names both gaps: SNI co-hosting (decision-134) and the
    loopback-WIDE seatbelt allowance (decision-136 (4)).

    **Why the seatbelt cedes.** A seatbelt still claiming `network` would
    both conflict on the axis and deny the loopback hop the workload needs to
    reach its own proxy. `cedes_network=True` is what makes the pair
    composable AND functional; see decision-136.

    `python` is the interpreter `connect_proxy`'s helper is spawned with --
    an argument because `compile()` may not read `sys.executable` any more
    than it may read a clock (decision-137 (4)).

    Darwin only: it composes seatbelt, which is `sandbox-exec`.
    """
    return Stack([rlimits, Seatbelt(cedes_network=True), env_scrub, ConnectProxy(python)])


__all__ = (  # noqa: RUF022
    "AxisClaimConflict",
    "COMPATIBILITY_MATRIX",
    "CompatibilityRefused",
    "CompiledJail",
    "EnvConflict",
    "MATRIX_VERSION",
    "MatrixEntry",
    "Stack",
    "degraded",
    "confined_egress_darwin",
    "scratch_darwin",
    "strict_linux",
)
