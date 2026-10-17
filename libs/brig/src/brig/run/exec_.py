"""What a start in a jail is held to: `ExecWrapNotAPrefix` and `ExecFidelity`.

SPEC.md §9: an exec sibling -- since decision-181 any `jail.start`, the
first included -- "is subject to the same Spec as the workload -- never a
weaker one. A mechanism that cannot guarantee this refuses exec." Named
`exec_` (trailing underscore) because `exec` is a Python builtin.

**`wrap_prefix`, not `jail.wrap` (task-046).** A jail's dict cannot carry the
compiled `wrap` callable across `to_dict`/`from_dict`, so `HostRuntime.create`
DERIVES and VERIFIES `wrap_prefix` once (`brig/run/host.py`), and every start
spawns `(*wrap_prefix, *argv)`. Three cases, per SPEC.md §9:

- `wrap_prefix is None` -- the compiled wrap is not a pure argv prefix.
  Every start refuses (`ExecWrapNotAPrefix`) before anything is made or
  spawned, rather than fall back to a bare, unconfined spawn.
- `wrap_prefix == ()` -- the empty stack (or an identity wrap): the process
  is spawned bare and its fidelity is `ExecFidelity.PLAIN`.
- non-empty -- `(*wrap_prefix, *argv)`, `ExecFidelity.EQUIVALENT_PROFILE`:
  an identical wrapper, a different instance.

The env is `{**os.environ, **jail_env}` in every case, composed fresh at each
start (decision-152). A sibling is a `jail.start` and its handle a `Process`
(decision-183); there is no `interactive` start (it could only refuse, for
want of `PTY`).
"""

from enum import Enum


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
    same posture as `host.LaunchRefused`.
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
    inside the *same boundary instance* (`SAME_INSTANCE`: no M4 mechanism
    could deliver this, task-046; a bwrap jail does since decision-192, SPEC.md
    §9, every process a request to the supervisor that is its PID 1, in the jail's
    confinement and, since decision-195, in namespaces of its own where the host gives
    them); `seatbelt` and any other
    argv-wrap mechanism (`env_scrub`, `rlimits`, and their composition) can
    only start a sibling under an *identical, re-derived* wrapper --
    `EQUIVALENT_PROFILE`, first reachable at task-046, whenever
    the jail's `wrap_prefix` is a non-empty, verified prefix; a stack with no
    mechanisms (or an identity wrap) execs a plain process (`PLAIN`) --
    M2's only member, still the empty-stack case as of this task."""

    SAME_INSTANCE = "SAME_INSTANCE"
    EQUIVALENT_PROFILE = "EQUIVALENT_PROFILE"
    PLAIN = "PLAIN"
