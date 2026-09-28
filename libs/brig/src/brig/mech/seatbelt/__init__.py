"""`brig.mech.seatbelt`: SPEC.md §6's `seatbelt` mechanism -- darwin SBPL.

This package re-exports `brig.mech.seatbelt.profile`'s public names
(task-058) and now ALSO carries the `Seatbelt` mechanism class and the
module-level `seatbelt` instance (task-059) -- same posture as
`brig.mech.env_scrub`: one file holding both the caller-facing wrapper
(`Mechanism.compile`, `Step`, grades, denial signatures, staged files, the
argv prefix) and the instance embedders and `Stack` compose against. The
pure `spec -> SBPL text` render itself stays in `profile.py`, UNCHANGED by
this task (task-058's own file, mutation-proven and pinned by sha256 in
that task's notes -- not touched here): `Seatbelt.compile` calls
`profile.render_sbpl` and adds nothing that render could not already do
itself.

**Discrepancy noted, not corrected.** `profile.py`'s own module docstring
says the `Seatbelt` class "lands in this same file later" (i.e. in
`profile.py`). This task's Deliverable says otherwise, explicitly and by
path: "`brig/mech/seatbelt/__init__.py` -- the `Seatbelt` mechanism class
and the module-level `seatbelt` instance, same posture as
`brig.mech.env_scrub`." The Deliverable is this task's authoritative
instruction and is followed here; `profile.py`'s sentence is a prior
implementer's forecast, not a spec, and is left as-is (this task does not
own `profile.py` and does not edit it) -- flagged here for the
orchestrator rather than silently reconciled.

SPEC.md §6 roster row, verbatim:

    | `seatbelt` | fs_read (denylist), fs_write, network (deny-all), channel binds | darwin | SBPL; empirical dialect knowledge carried as tested facts |

**`axes` deliberately does NOT include `Axis.CHANNEL_EXCLUSIVITY`** -- plan
ambiguity A5, RULED and folded at operator round 17 (decision-118; SPEC.md
§6 now carries this as a roster note, settled law rather than a proposal).
The roster row's "channel binds" names WORK this mechanism does (compiling
the LISTEN bind rules into the profile), not an AXIS it claims:
`channel_exclusivity` is about SPEC.md §10's enumerated shared media, which
seatbelt does not restrict, and the operator's own golden for
`scratch_darwin()` (task-064) grades it `unenforced`. Declaring it here
would be a grade-up.

**Four refusals, never a silent downgrade (SPEC.md §2 law 2), each naming
its subject:**

1. `ctx.platform != "darwin"` -- `PlatformUnsupported`, naming the
   platform, raised by `Seatbelt.compile` itself.
2. `spec.fs.read_model is ReadModel.ALLOW_LIST` -- `profile.py`'s own
   `ReadModelUnsupported`, propagated UNCHANGED from `render_sbpl` (this
   mechanism implements the denylist model only; nothing here re-checks or
   re-raises it).
3. `spec.network.allowed_domains` non-empty -- `NetworkUnsupported`, naming
   the domain(s), raised by `Seatbelt.compile` itself: seatbelt has no DNS
   awareness and cannot filter egress by domain. Per-domain egress is
   `connect_proxy`, M6 (plan ambiguity A7); grading `best_effort` here
   would be claiming that mechanism's work before it exists.
4. Any path `render_sbpl` needs that `ctx.resolved_paths` does not carry --
   `profile.py`'s own `UnresolvedPath`, propagated UNCHANGED, never
   swallowed.

**`wrap` is a PURE argv prefix**: `("/usr/bin/sandbox-exec", "-f",
f"{ctx.jail_dir}/seatbelt.sb", *argv)` -- absolute path, never the bare
name (decision-026 rule 1's family). It MUST stay a pure prefix:
`brig/run/launcher.py`'s `_derive_wrap_prefix` refuses `handle.exec` for a
wrap that turns out not to be one, and every probe in this milestone runs
through `handle.exec`.

**Grade details are load-bearing text, not free prose** -- see
`_FS_READ_DETAIL` / `_FS_WRITE_DETAIL` / `_network_detail` below for the
exact sentences and why each contains the token this task's own ACs pin
(`denylist`, `write_denies`, `unscoped`).
"""

from __future__ import annotations

import re
from typing import Final

from brig.core import Axis, Grade, Graded, Spec
from brig.mech.contract import ArgvTransformer, CompileCtx, StagedFile, Step
from brig.mech.seatbelt.profile import ChannelInsideWriteDeny as ChannelInsideWriteDeny
from brig.mech.seatbelt.profile import ReadModelUnsupported as ReadModelUnsupported
from brig.mech.seatbelt.profile import UnresolvedPath as UnresolvedPath
from brig.mech.seatbelt.profile import render_sbpl as render_sbpl

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
_SANDBOX_EXEC_FLAG = "-f"
_STAGED_PROFILE_RELPATH = "seatbelt.sb"
_DARWIN = "darwin"

#: SPEC.md §6's own quoted denial signature for this mechanism: "Operation
#: not permitted" -- the darwin SBPL kernel's own denial text. Tested in
#: both directions in `tests/unit/test_seatbelt_compile.py`, per the
#: unit-tier rules: it must match this text and must NOT match a generic
#: failure ("command not found", "No such file or directory").
_DENIAL_SIGNATURE: re.Pattern[str] = re.compile(r"Operation not permitted")

#: Must contain the literal token "denylist" (this task's AC #6): reads are
#: default-ALLOW with explicit per-path denies, never an allow-list.
_FS_READ_DETAIL = (
    "seatbelt enforces fs_read as a denylist: reads are default-allow "
    '(allow file-read* (subpath "/")), with spec.fs.read_denies compiled '
    "as explicit per-path denies layered on top of that default-allow."
)

#: Must contain the literal token "write_denies" (this task's AC #6): the
#: carve-out precedence is deny-over-allow, and it is INSIDE the granted
#: write_allows, never a separate policy.
_FS_WRITE_DETAIL = (
    "seatbelt enforces fs_write by denying by default and allowing only "
    "spec.fs.write_allows; write_denies carve-outs are compiled deny-over-"
    "allow -- inside the granted write_allows, never as a separate policy."
)

_NETWORK_DETAIL_BASE = (
    "seatbelt denies all network traffic by default (deny network* (with no-log))."
)


class PlatformUnsupported(ValueError):
    """Raised when `Seatbelt.compile` is asked to compile for
    `ctx.platform != 'darwin'`: SBPL and `sandbox-exec` are darwin-only.
    Names the offending platform string."""


class NetworkUnsupported(ValueError):
    """Raised when `spec.network.allowed_domains` is non-empty: seatbelt
    has no DNS awareness and cannot filter egress by domain -- per-domain
    egress is `connect_proxy`'s job (M6), and grading `best_effort` here
    would be claiming that mechanism's work before it exists (plan
    ambiguity A7). Names the offending domain(s)."""


def _network_detail(*, has_listen_channel: bool) -> str:
    """The `Axis.NETWORK` grade detail. Must contain the literal token
    "unscoped" (this task's AC #6) whenever `has_listen_channel` is true:
    `network-bind` is allowed UNSCOPED by dialect necessity -- a `(literal
    ...)` or `(subpath ...)` filter on `network-bind` denies the bind
    outright on this dialect, no matter how permissive the surrounding
    rules are -- and the LISTEN endpoint's own socket path is instead
    confined by the `(allow file-write* (literal ...))` rule
    (`profile.py`'s own module docstring names both dialect facts)."""
    if not has_listen_channel:
        return (
            f"{_NETWORK_DETAIL_BASE} No LISTEN channel is declared, so no "
            "network-bind rule is emitted at all."
        )
    return (
        f"{_NETWORK_DETAIL_BASE} Because at least one LISTEN channel is "
        "declared, network-bind is allowed unscoped by dialect necessity: "
        "this dialect denies the bind outright if the allow rule carries a "
        "(literal ...) or (subpath ...) filter, no matter how permissive "
        "the surrounding rules are -- so the LISTEN endpoint's own socket "
        "path is confined instead by the (allow file-write* (literal ...)) "
        "rule, not by network-bind itself."
    )


#: The axes seatbelt claims when it owns the network axis, and when it has
#: ceded it. decision-136 (1): `connect_proxy` is the sole claimant of
#: `Axis.NETWORK` in any stack containing both, because egress filtering by
#: domain has never been seatbelt's work -- it has no DNS awareness, which is
#: exactly why it refused `allowed_domains` in the first place.
_AXES_OWNING_NETWORK: Final = frozenset({Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK})
_AXES_CEDING_NETWORK: Final = frozenset({Axis.FS_READ, Axis.FS_WRITE})


class Seatbelt:
    """SPEC.md §6's `seatbelt` mechanism: darwin SBPL via `sandbox-exec`.

    **`cedes_network` hands `Axis.NETWORK` to `connect_proxy`**
    (decision-136). Without it, `Stack([Seatbelt(), ConnectProxy(...)])`
    raises `AxisClaimConflict` -- SPEC.md §7 step 1 makes overlap an error,
    deliberately -- and the whole M6 pairing is uncomposable.

    It is a CONSTRUCTOR argument and not a function of the `Spec` because
    `Stack.compile`'s claim check reads `mechanism.axes` and is documented as
    running BEFORE any `mechanism.compile()`, precisely so claims are
    checkable without compiling. A spec-dependent claim would either move
    that check after compile or make it lie. It also reads better at the call
    site: the preset that pairs the two says which mechanism owns the axis,
    in the same place a reader sees them composed -- the same posture
    `ConnectProxy(python=...)` takes.

    Defaults to `False`, so every existing caller and `scratch_darwin()`
    itself keep claiming `network` and keep refusing `allowed_domains`
    unchanged. A seatbelt that cedes is opted into, never inferred.
    """

    name = "seatbelt"

    def __init__(self, *, cedes_network: bool = False) -> None:
        self._cedes_network = cedes_network
        #: Instance-level, not class-level, since `cedes_network` decides it.
        self.axes: frozenset[Axis] = _AXES_CEDING_NETWORK if cedes_network else _AXES_OWNING_NETWORK

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        """Refuses in four cases (this module's own docstring); cases 2
        and 4 are `profile.render_sbpl`'s own refusals, propagated here
        UNCHANGED -- this method never catches and re-raises them, and
        never swallows them."""
        if ctx.platform != _DARWIN:
            raise PlatformUnsupported(
                f"seatbelt only compiles for ctx.platform == {_DARWIN!r}, got {ctx.platform!r}"
            )
        # decision-136 (3): the refusal exists so a net-granted spec cannot run
        # believing seatbelt filters by domain. A CEDING seatbelt is by
        # definition paired with a mechanism that does filter, so the refusal
        # would be false. A non-ceding one keeps refusing, unchanged -- that is
        # what stops a net-granted spec from silently running with no filter at
        # all when nothing else in the stack carries egress.
        if spec.network.allowed_domains and not self._cedes_network:
            raise NetworkUnsupported(
                "seatbelt has no DNS awareness and cannot filter egress by domain "
                "(per-domain egress is connect_proxy's job, M6); got "
                f"spec.network.allowed_domains={spec.network.allowed_domains!r}"
            )

        # `LISTEN` is the only `ChannelKind` there is (decision-153), so
        # "declares a LISTEN channel" is "declares a channel".
        has_listen_channel = bool(spec.channels)

        # ReadModelUnsupported (case 2) and UnresolvedPath (case 4) are
        # raised BY render_sbpl itself when they apply -- propagated to
        # this method's own caller unchanged.
        content = render_sbpl(
            spec,
            resolved=ctx.resolved_paths,
            jail_dir=ctx.jail_dir,
            cedes_network=self._cedes_network,
        )

        jail_dir = ctx.jail_dir

        def wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
            return (
                _SANDBOX_EXEC,
                _SANDBOX_EXEC_FLAG,
                f"{jail_dir}/{_STAGED_PROFILE_RELPATH}",
                *argv,
            )

        wrap_transformer: ArgvTransformer = wrap

        grades: dict[Axis, Graded] = {
            Axis.FS_READ: Graded(Grade.ENFORCED, _FS_READ_DETAIL),
            Axis.FS_WRITE: Graded(Grade.ENFORCED, _FS_WRITE_DETAIL),
        }
        # Grading an axis this instance does not claim would be a grade-up of
        # exactly the kind decision-118 refused for channel_exclusivity: the
        # profile still does network WORK when ceding (it denies everything
        # but the loopback hop), but the axis and its grade belong to
        # connect_proxy, and whatever observes the pairing raises it there.
        if not self._cedes_network:
            grades[Axis.NETWORK] = Graded(
                Grade.ENFORCED, _network_detail(has_listen_channel=has_listen_channel)
            )

        return Step(
            wrap=wrap_transformer,
            env={},
            staged=(StagedFile(relpath=_STAGED_PROFILE_RELPATH, content=content, mode=0o600),),
            helpers=(),
            requires=frozenset(),
            grades=grades,
            denial_signatures=(_DENIAL_SIGNATURE,),
        )


#: The mechanism instance embedders and `Stack` compose against -- same
#: posture as `brig.mech.env_scrub`'s own module-level `env_scrub` instance.
seatbelt: Seatbelt = Seatbelt()

__all__ = (
    "ChannelInsideWriteDeny",
    "NetworkUnsupported",
    "PlatformUnsupported",
    "ReadModelUnsupported",
    "Seatbelt",
    "UnresolvedPath",
    "render_sbpl",
    "seatbelt",
)
