"""The rlimits exec trampoline: `python -m brig.mech.trampoline --cpu N -- argv...`.

Per MILESTONES.md M3's scope bullet, this program is how the `rlimits`
mechanism (a later task) puts a kernel limit under a workload: it sets the
limit with `resource.setrlimit`, then `os.execvp`s the remaining argv --
never fork, never wait, never survive as a parent. Because the limit is set
*by this process itself* before it becomes the workload (`setrlimit` is
inherited across `exec`, same as any other process attribute), nothing needs
to run inside the child after a fork to put the limit in place: a trampoline
is a plain argv wrapper, so it composes under any launcher (`subprocess`,
`tmux`, a future PTY launcher) exactly the way SPEC.md section 8 says a
mechanism must -- the launcher never needs to know a limit is being applied
at all.

No `Popen`-style post-fork child hook is used anywhere in this library. That
is a pinned property, not a preference: such a hook runs in the child
*after* fork but is documented as unsafe in a multithreaded process, and it
ties the limit-setting code to whichever launcher does the forking. A
trampoline that is itself the thing `exec`'d needs no such hook and works
identically launched directly, under `subprocess`, or inside a pty.

Only `--cpu N` is implemented (`RLIMIT_CPU`, in whole seconds). Memory, task
count and wall-clock limits are out of scope here per MILESTONES.md: they
land on `systemd_scope` at M7, and nothing in this task's own evidence shows
them reliably enforceable via `setrlimit` on this platform.

Argv shape: every token up to a literal `--` is a limit flag; everything
after `--` is the workload's own argv, handed to `os.execvp` unmodified. An
unrecognized flag, a missing `--` separator, or an empty tail after `--` is a
refusal (non-zero exit, message on stderr) -- never a silent pass-through,
because a trampoline that ignores what it doesn't understand would silently
under-enforce the exact limit it exists to apply.

This module carries no `if __name__ ==` guard of its own -- importing it,
which the unit tests do directly for `parse_trampoline_argv`, never applies a
limit or execs anything. Only actually running this package (as `python -m`
does) touches the process image; that guard lives in the sibling module,
whose own docstring explains why the split is required, not stylistic.
"""

from __future__ import annotations

import os
import resource
import sys
from collections.abc import Sequence
from dataclasses import dataclass

_CPU_FLAG = "--cpu"
_SEPARATOR = "--"

#: CPU-seconds between `RLIMIT_CPU`'s soft limit (which raises `SIGXCPU`)
#: and its hard limit (which is `SIGKILL`). See `apply_limits` for why it is
#: not zero -- decision-161.
_HARD_CPU_HEADROOM_S = 1


@dataclass(frozen=True, slots=True)
class ParsedTrampolineArgv:
    """The pure result of parsing trampoline argv: limits plus workload argv.

    Attributes:
        cpu_seconds: `RLIMIT_CPU`'s SOFT seconds, or None if `--cpu` was not
                     given (no limit is applied for an omitted flag). The hard
                     limit `apply_limits` sets is one second above it --
                     decision-161, and that function's docstring.
        workload_argv: The argv to `os.execvp`, unmodified from the caller's
                       tail after `--`. Always non-empty (an empty tail is a
                       parse error, not a valid result).
    """

    cpu_seconds: int | None
    workload_argv: tuple[str, ...]


class TrampolineArgvError(ValueError):
    """Raised by `parse_trampoline_argv` on any argv this program refuses.

    Carries a human-readable reason as its sole `str(...)`, written to
    stderr by `main` alongside a non-zero exit. Never used to signal a
    silent pass-through -- every raise site here corresponds to a case the
    module docstring names as a refusal.
    """


def parse_trampoline_argv(argv: Sequence[str]) -> ParsedTrampolineArgv:
    """Parse `--cpu N ... -- argv...` into limits and the workload argv.

    Pure function: no I/O, no `resource` calls, no exec. Everything left of
    the first literal `--` is limit flags; everything right of it is the
    workload's own argv, handed back verbatim. Raises `TrampolineArgvError`
    (never returns a partial or best-guess result) when:

    - there is no `--` separator anywhere in `argv`;
    - the tail after `--` is empty (nothing to exec);
    - a flag left of `--` is not `--cpu`, or `--cpu` has no following value,
      or that value does not parse as an integer.
    """
    if _SEPARATOR not in argv:
        raise TrampolineArgvError(
            f"missing {_SEPARATOR!r} separator between limit flags and workload argv"
        )
    sep_index = list(argv).index(_SEPARATOR)
    flags = list(argv[:sep_index])
    workload_argv = tuple(argv[sep_index + 1 :])
    if not workload_argv:
        raise TrampolineArgvError(f"empty workload argv after {_SEPARATOR!r}")

    cpu_seconds: int | None = None
    i = 0
    while i < len(flags):
        flag = flags[i]
        if flag == _CPU_FLAG:
            if i + 1 >= len(flags):
                raise TrampolineArgvError(f"{_CPU_FLAG!r} requires a value")
            raw_value = flags[i + 1]
            try:
                cpu_seconds = int(raw_value)
            except ValueError as exc:
                raise TrampolineArgvError(
                    f"{_CPU_FLAG!r} value must be an integer, got {raw_value!r}"
                ) from exc
            if cpu_seconds <= 0:
                # A non-positive value is not "no limit" and not caught by
                # int()'s own parsing -- resource.setrlimit(RLIMIT_CPU, (-1,
                # -1)) means RLIM_INFINITY (no limit at all, the opposite of
                # what a negative number reads as), and 0 trips instantly.
                # Both are exactly the silent under-enforcement this module's
                # docstring says a refusal exists to prevent, so they refuse
                # here rather than being handed to `resource.setrlimit`
                # unexamined.
                raise TrampolineArgvError(
                    f"{_CPU_FLAG!r} value must be a positive integer, got {raw_value!r}"
                )
            i += 2
        else:
            raise TrampolineArgvError(f"unknown flag: {flag!r}")

    return ParsedTrampolineArgv(cpu_seconds=cpu_seconds, workload_argv=workload_argv)


def apply_limits(parsed: ParsedTrampolineArgv) -> None:
    """Apply `parsed`'s limits via `resource.setrlimit`, in this process.

    Called by `main` after parsing and before `os.execvp` -- the limit must
    be set *before* the exec so it is already active in the process image
    that replaces this one (a POSIX rlimit is inherited across `exec`,
    which is precisely what makes a trampoline sufficient without any
    post-fork child hook: nothing needs to run inside the workload's own
    process to put the limit in place).

    **The hard limit is one second above the soft limit** (decision-161,
    2026-09-08), not equal to it. `RLIMIT_CPU`'s soft limit is what raises
    `SIGXCPU`; the hard limit is `SIGKILL`. Linux checks the hard limit
    FIRST, so a soft-equals-hard pair there kills with `SIGKILL` and this
    mechanism's whole `SIGXCPU` story -- its denial signature
    (`signal:SIGXCPU`), its `LIMIT_TRIP` event, the limits battery that
    reads them -- silently never fires. Darwin raises `SIGXCPU` at the soft
    limit either way, which is why soft-equals-hard survived until the
    suite was first run on Linux. One second of headroom makes `SIGXCPU`
    the observed ending on both kernels, and `SIGKILL` one CPU-second later
    remains the backstop for a workload that catches `SIGXCPU` and refuses
    to die. Both numbers are still derived from `--cpu N`, and the cap the
    Spec asked for is still the soft one.
    """
    if parsed.cpu_seconds is not None:
        resource.setrlimit(
            resource.RLIMIT_CPU, (parsed.cpu_seconds, parsed.cpu_seconds + _HARD_CPU_HEADROOM_S)
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Parse argv, apply limits, `execvp` the workload.

    `argv` defaults to `sys.argv[1:]`. On a refusal (see
    `parse_trampoline_argv`), prints the reason to stderr and returns `2`
    without touching `resource` or exec-ing anything. On success this
    function does not return at all: `os.execvp` replaces this process's
    image, so there is no "after the exec" for this function to reach --
    the calling process the workload now runs *as* is this trampoline's own
    pid, not a child of it. Called only from this package's `-m` entry
    point (see the sibling file), never at import time.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = parse_trampoline_argv(args)
    except TrampolineArgvError as exc:
        print(f"brig.mech.trampoline: refused: {exc}", file=sys.stderr)
        return 2
    apply_limits(parsed)
    os.execvp(parsed.workload_argv[0], list(parsed.workload_argv))
