"""`brig.mech.seatbelt.profile`: the pure `Spec -> SBPL text` render.

SPEC.md §6 roster row, verbatim:

    | `seatbelt` | fs_read (denylist), fs_write, network (deny-all), channel binds | darwin | SBPL; empirical dialect knowledge carried as tested facts |

**This module is `render_sbpl` and nothing else -- task-058's Deliverable,
not task-059's.** The `Seatbelt` mechanism class (`Mechanism.compile`,
`Step`, grades, denial signatures, staged files, the argv prefix, the
compatibility-matrix rows) is task-059's, and lands in this same file
later. Everything here is a pure function of `(spec, resolved, jail_dir)`:
no I/O, no clock, no randomness, no subprocess -- `tests/unit/
test_seatbelt_profile.py`'s own purity test ASTs this file's top-level
imports and fails the build the instant that stops being true (AC #4).

**`resolved_paths` / `jail_dir` -- SPEC.md §6, decision-115.** Some kernels
(seatbelt is the first) match paths after symlink resolution, so an SBPL
rule written against darwin's `/tmp/bgNNN` -- itself a symlink to
`/private/tmp/bgNNN` -- silently matches nothing. `realpath` is I/O, and a
render that performs it stops being a pure function of `(spec, ctx)` with a
filesystem-independent golden -- so BOTH halves of the resolution live
outside this module: `resolved` is built by a `run`-layer helper (task-059's
plumbing) mapping each `Spec` path, EXACTLY as the `Spec` carries it, to its
realpath'd form; `jail_dir` similarly arrives pre-resolved from that same
caller. This render resolves NOTHING itself. A path it needs and cannot
find in `resolved` raises `UnresolvedPath`, naming the path -- never
falling back to the lexical form, which is the exact `/tmp` vs
`/private/tmp` bug this whole arrangement exists to prevent (law 2's
refusal-not-downgrade posture). The keys this render requires: every
`spec.fs.write_allows`, every `spec.fs.write_denies`, every
`spec.fs.read_denies`, and every LISTEN `Channel.endpoint`.

**The `jail_dir` guard is LEXICAL, not a proof of resolution.** A pure
render cannot `lstat` to prove a path is actually resolved. So
`render_sbpl` refuses (`UnresolvedPath`) a `jail_dir` whose leading path
component is one of darwin's known symlinked roots -- `/tmp`, `/var`,
`/etc` -- and nothing more. `/private/tmp/bg1` is NOT refused: the guard
discriminates the documented trap shape, it does not decide "is this
actually a realpath" in general (that criterion is unsatisfiable for a pure
function -- decision-122(4)'s in-flight repair of this task's own AC #6,
recorded in this task's ORCHESTRATOR note).

**Emission order -- TRANSCRIBED from the parent project's own PROBED
emission, not derived from a precedence argument, extended only where brig
has a feature the parent does not:**

    (version 1)
    (deny default)
    (import "system.sb")
    (allow process-exec*)
    (allow process-fork)
    (allow signal (target self))
    (allow file-read* (subpath "/"))
      [per read_denies entry, spec order]   (deny file-read* (subpath "RESOLVED"))
    (deny file-write* (subpath "/"))
      [per write_allows entry, spec order]  (allow file-write* (subpath "RESOLVED"))
      [per write_denies entry, spec order]  (deny file-write* (subpath "RESOLVED"))
      [per LISTEN channel, spec order]      (allow file-write* (literal "RESOLVED"))
    (allow network-bind)                    [ONLY when at least one LISTEN channel]
    (deny network* (with no-log))

"Spec order" needs no separate sort here: `FsPolicy.__post_init__` already
normalizes `write_allows`/`write_denies`/`read_denies` to a sorted tuple,
and `Spec.__post_init__` already sorts `channels` by name -- this render
just iterates what the `Spec` already carries.

The write_denies DENY lines come AFTER the write_allows ALLOW lines --
that is the deny-over-allow precedence SPEC.md §5 requires (`write_denies`
is a carve-out INSIDE `write_allows`), and it is the one line of this
render `tests/unit/test_seatbelt_profile.py`'s mutation check (AC #8) is
about: move the write_denies loop above the write_allows loop and both the
ORDERING test and the GOLDEN test go red.

**Two dialect facts, carried because the parent PROBED them -- do not "fix"
these into something that reads better and enforces less:**

- **`network-bind` must be UNSCOPED.** A `(literal ...)` or `(subpath ...)`
  filter on `network-bind` denies the bind outright on this dialect no
  matter how permissive the surrounding rules are. The socket path is
  confined by the `(allow file-write* (literal ...))` rule instead, which
  the kernel DOES check for the path a new AF_UNIX socket file is created
  at.
- **`(import "system.sb")` comes first**, right after `(deny default)`.
  `(deny default)` alone SIGABRTs even `/bin/echo`; basic process startup
  needs Apple's shipped baseline. Note this means `(deny default)` itself
  sits BEFORE the import line -- it is the one line this module emits
  that is neither a policy rule nor governed by the import-precedes-rules
  ordering `tests/unit/test_seatbelt_profile.py`'s AC #3 test asserts;
  that test names the exception explicitly rather than silently special-
  casing it.

**One conditionality that is brig's own call, not the parent's (plan
ambiguity A2).** The parent project emits `(allow network-bind)`
unconditionally. This render emits it ONLY when the spec declares at least
one LISTEN channel -- a jail that can bind sockets while its report says
`network: enforced` is a grade-up, and task-061 owns the observed control
for it. A spec with no channels renders zero `network-bind` lines. The
condition used to be spelled as a filter on `Channel.kind`, because a
`MAILBOX` is not "channel binds" in seatbelt's roster-row sense; `LISTEN`
is the only kind there is since decision-153, so the filter is gone and
the condition is simply "does this spec declare a channel".

**`ReadModelUnsupported`.** SPEC.md §6's roster row spells seatbelt's
`fs_read` axis "(denylist)": the two read models are declared, not layered
(SPEC.md §5), and compiling `ReadModel.ALLOW_LIST` through a denylist-only
mechanism is a refusal here, never a silent, wrong-shaped denylist render.

**`ChannelInsideWriteDeny`.** `write_denies` is a carve-out INSIDE
`write_allows` for the self-escalation threat (SPEC.md §5): if a LISTEN
channel's own resolved endpoint fell under a resolved `write_denies`
subpath, the deny-over-allow ordering above would make the DENY win for
that exact path, and the channel's own `(allow file-write* (literal ...))`
rule would compile as text but the child could never actually create its
socket file there -- a rule that is present and matches nothing is the
exact failure this library exists to refuse (SPEC.md §6). Refused here by
name, both paths, rather than left to a silent, confusing runtime bind
failure.

**String escaping and the `"*"`-means-everywhere wildcard are carried from
the parent's `_sbpl_str` / `_sbpl_subpath`.** `_sbpl_str` escapes a
backslash first, then a double-quote (order matters: escaping the quote
first would double-escape a backslash the first pass introduces).
`_sbpl_subpath` treats the internal sentinel `"*"` as "the SBPL root" and
renders it as `(subpath "/")` -- used ONLY for this render's own two
whole-tree default rules (`(allow file-read* (subpath "/"))` and
`(deny file-write* (subpath "/"))`), never for a `Spec`-supplied path:
every `Spec` path goes through `resolved` unconditionally, with no
wildcard bypass -- an entry that skipped `resolved` would be exactly the
silent fallback law 1 forbids.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from brig.core import ReadModel, Spec

#: darwin's known symlinked roots (SPEC.md §6). A `jail_dir` whose leading
#: path component is one of these is almost certainly the UNRESOLVED
#: (symlinked) form -- e.g. `/tmp/bgNNN` is a symlink to
#: `/private/tmp/bgNNN`. LEXICAL guard only: it discriminates the
#: documented trap shape, it is not (and cannot be, from a pure render) a
#: proof that a given path really is a realpath.
_SYMLINKED_ROOTS: tuple[str, ...] = ("/tmp", "/var", "/etc")

#: Internal sentinel meaning "the whole filesystem tree" -- never a value
#: that comes from a `Spec` or from `resolved`. Passed to `_sbpl_subpath`
#: for this render's own two whole-tree default rules only.
_WHOLE_TREE = "*"


class UnresolvedPath(ValueError):
    """Raised when a path this render needs is missing from `resolved` --
    a `write_allows`/`write_denies`/`read_denies` entry or a LISTEN
    `Channel.endpoint` -- or when `jail_dir` itself is lexically one of
    darwin's known symlinked roots. Names the offending path in every
    case; this render never falls back to the lexical form (SPEC.md §6,
    law 2's refusal-not-downgrade posture)."""


class ReadModelUnsupported(ValueError):
    """Raised when `spec.fs.read_model` is `ReadModel.ALLOW_LIST`: seatbelt
    is a denylist-only mechanism (SPEC.md §6's roster row: "fs_read
    (denylist)"), and compiling the other model through it is a refusal,
    never a silent downgrade (SPEC.md §5's two-read-models bullet). Names
    the model it was asked to compile."""


class ChannelInsideWriteDeny(ValueError):
    """Raised when a LISTEN `Channel`'s resolved endpoint falls under a
    resolved `write_denies` subpath: the deny-over-allow ordering this
    render emits would make the DENY win for that exact path, so the
    channel's own bind rule would compile as text but the child could
    never actually create its socket file there. Names both the channel's
    resolved endpoint and the write_denies subpath it falls under."""


#: The `remote ip` filter for the loopback allowance decision-136 (4)
#: requires. `localhost:*` covers both v4 and v6 loopback on this dialect.
_LOOPBACK_REMOTE: Final[str] = "localhost:*"


def _sbpl_str(value: str) -> str:
    """Escape a raw string for embedding in an SBPL string literal:
    backslash first, then double-quote -- order matters, escaping the
    quote first would double-escape any backslash the first pass
    introduces. Carried from the parent project's own `_sbpl_str`."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _sbpl_subpath(path: str) -> str:
    """Render an SBPL `(subpath "...")` clause. The internal sentinel
    `"*"` -- used only by this module's own two whole-tree default rules,
    never for a `Spec`-supplied path -- renders as the SBPL root `"/"`.
    Carried from the parent project's own `_sbpl_subpath`."""
    rendered = "/" if path == _WHOLE_TREE else path
    return f'(subpath "{_sbpl_str(rendered)}")'


def _sbpl_literal(path: str) -> str:
    """Render an SBPL `(literal "...")` clause -- a LISTEN channel's exact
    socket path is one file, not a tree, so it is a literal, never a
    subpath."""
    return f'(literal "{_sbpl_str(path)}")'


def _resolve(path: str, resolved: Mapping[str, str]) -> str:
    """Look up `path`'s realpath'd form in `resolved`; refuse
    (`UnresolvedPath`, naming `path`) rather than fall back to the lexical
    form -- SPEC.md §6's refusal-not-downgrade posture, and the exact
    `/tmp` vs `/private/tmp` bug this whole arrangement exists to
    prevent."""
    try:
        return resolved[path]
    except KeyError:
        raise UnresolvedPath(f"no resolved form for path {path!r} in `resolved`") from None


def _is_subpath(candidate: str, root: str) -> bool:
    """True if the already-resolved `candidate` path is `root` itself, or
    lies under it. A plain string containment check on already-resolved
    forms -- no filesystem read on either side; `root == "/"` is treated
    as covering everything, matching what `(subpath "/")` itself would
    match."""
    if root == "/":
        return True
    return candidate == root or candidate.startswith(root + "/")


def _jail_dir_is_unresolved(jail_dir: str) -> bool:
    """The LEXICAL guard named in this module's docstring: true when
    `jail_dir`'s leading path component is one of darwin's known
    symlinked roots. Never a realpath comparison -- a pure render cannot
    perform one."""
    return any(jail_dir == root or jail_dir.startswith(root + "/") for root in _SYMLINKED_ROOTS)


def render_sbpl(
    spec: Spec, *, resolved: Mapping[str, str], jail_dir: str, cedes_network: bool = False
) -> str:
    """Render `spec` into SBPL text. Pure: no I/O, no clock, no randomness.

    Args:
        spec: The full `Spec` to render seatbelt's slice of. Must have
              `spec.fs.read_model is ReadModel.DENY_LIST` (seatbelt is a
              denylist-only mechanism).
        resolved: Maps each `Spec` path this render needs -- every
              `write_allows`/`write_denies`/`read_denies` entry, every
              LISTEN `Channel.endpoint` -- to its realpath'd form, exactly
              as the `Spec` carries the key. Built by a `run`-layer
              helper; this render performs no resolution of its own.
        jail_dir: The jail directory, already realpath'd by the caller
              (see `CompileCtx`'s own docstring for the invariant). This
              render only LEXICALLY guards it (see module docstring); it
              never resolves it and never proves resolution.

    Returns:
        The full SBPL profile text, newline-terminated.

    Raises:
        ReadModelUnsupported: `spec.fs.read_model` is not `DENY_LIST`.
        UnresolvedPath: a needed `Spec` path is absent from `resolved`, or
              `jail_dir` is lexically one of darwin's known symlinked
              roots.
        ChannelInsideWriteDeny: a LISTEN channel's resolved endpoint falls
              under a resolved `write_denies` subpath.
    """
    if spec.fs.read_model is not ReadModel.DENY_LIST:
        raise ReadModelUnsupported(
            f"seatbelt only compiles ReadModel.DENY_LIST specs, got {spec.fs.read_model!r}"
        )

    if _jail_dir_is_unresolved(jail_dir):
        raise UnresolvedPath(
            f"jail_dir {jail_dir!r} has a leading component among darwin's known "
            f"symlinked roots {_SYMLINKED_ROOTS!r} -- the caller must supply a "
            "realpath'd jail_dir (see CompileCtx's own docstring)"
        )

    lines: list[str] = [
        "(version 1)",
        "(deny default)",
        '(import "system.sb")',
        "(allow process-exec*)",
        "(allow process-fork)",
        "(allow signal (target self))",
        f"(allow file-read* {_sbpl_subpath(_WHOLE_TREE)})",
    ]

    for path in spec.fs.read_denies:
        lines.append(f"(deny file-read* {_sbpl_subpath(_resolve(path, resolved))})")

    lines.append(f"(deny file-write* {_sbpl_subpath(_WHOLE_TREE)})")

    for path in spec.fs.write_allows:
        lines.append(f"(allow file-write* {_sbpl_subpath(_resolve(path, resolved))})")

    # write_denies is a carve-out INSIDE write_allows (SPEC.md §5): these
    # DENY lines must be emitted AFTER every write_allows ALLOW line above
    # -- deny-over-allow precedence. This loop is deliberately its own
    # pass, not fused with the write_allows loop above, so the two are
    # independently movable (see this module's docstring's mutation-check
    # paragraph, AC #8: moving this loop above the write_allows loop must
    # be a clean, single-line-range edit).
    resolved_write_denies: list[str] = []
    for path in spec.fs.write_denies:
        resolved_deny = _resolve(path, resolved)
        resolved_write_denies.append(resolved_deny)
        lines.append(f"(deny file-write* {_sbpl_subpath(resolved_deny)})")

    listen_channels = spec.channels
    for channel in listen_channels:
        resolved_endpoint = _resolve(channel.endpoint, resolved)
        for deny_root in resolved_write_denies:
            if _is_subpath(resolved_endpoint, deny_root):
                raise ChannelInsideWriteDeny(
                    f"LISTEN channel {channel.name!r} resolved endpoint "
                    f"{resolved_endpoint!r} falls under write_denies subpath "
                    f"{deny_root!r}"
                )
        lines.append(f"(allow file-write* {_sbpl_literal(resolved_endpoint)})")

    # Brig's own call, not the parent's (plan ambiguity A2, this module's
    # docstring): network-bind is emitted ONLY when the spec declares at
    # least one LISTEN channel, never unconditionally.
    if listen_channels:
        lines.append("(allow network-bind)")

    lines.append("(deny network* (with no-log))")

    # decision-136 (3)+(4): a seatbelt that has CEDED the network axis to
    # connect_proxy must not deny the loopback hop, or every ALLOWED request
    # fails too -- the workload reaches its permitted hosts THROUGH the proxy
    # on 127.0.0.1. The allowance is loopback-WIDE, not port-scoped, and that
    # is forced rather than lazy: the proxy binds port 0 so two jails cannot
    # collide, so the number does not exist when this pure render runs.
    #
    # Empirical dialect facts, verified on darwin with both controls (this
    # module's standing posture -- see the module docstring):
    #   1. the specific `network-outbound` allow beats the `network*` deny
    #      REGARDLESS of which is emitted first, so this line's position
    #      relative to the deny above is not load-bearing;
    #   2. with this line present, loopback connects and a non-loopback
    #      address is still refused by the sandbox. Pinned by
    #      `tests/integration/test_seatbelt_cedes_network.py`, which asserts
    #      BOTH halves -- an allow that quietly opened all egress would
    #      otherwise pass a loopback-only assertion.
    #
    # The cost is named where it is paid: the workload can reach ANY loopback
    # service on the host, not only its own proxy. That is one of the two
    # reasons the paired grade stays best_effort (the other is decision-134's
    # SNI co-hosting gap).
    if cedes_network:
        lines.append(f'(allow network-outbound (remote ip "{_sbpl_str(_LOOPBACK_REMOTE)}"))')

    return "\n".join(lines) + "\n"
