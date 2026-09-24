"""Group teardown of a launched jail: `kill()`, filled in by task-020.

SPEC.md §9, the fixed ladder, verbatim:

> **The ladder is fixed, and its last rung is verification**: `SIGTERM` to
> the group, a grace period, `SIGKILL` to the group, then *verify* the
> survivors are actually gone -- and only then report, per item. The
> verification rung is not optional. A `KillReport` that records something
> as ended because a signal was *sent* is law 1's grading dishonesty
> relocated into teardown, and law 7 makes deliverability itself a graded
> claim rather than an assumption.

And SPEC.md law 7: "Control must not require cooperation. Interrupt and
kill are delivered by mechanism-level means that work when the jail is
spinning, wedged, or hostile. Teardown is process-group/tree-shaped, and
its deliverability is itself graded in the report."

**The pgid signalled here was read at spawn, and the pid-reuse seam that
created was ACCEPTED by decision-144 and is CLOSED by decision-155
(2026-09-08).** decision-144 named the window precisely -- leader exits, is
reaped, its pid recycles, the new holder becomes a group leader with the same
number, and is alive when teardown fires -- and its second condition for
ending the acceptance was "holding a pid across a durable boundary", which a
serialized `Handle` in an embedder's log is exactly. So every item this
module tears down now carries the moment its leader STARTED as well as its
number (`brig/run/_identity.py`), and `_run_ladder` refuses to signal a pid
whose current occupant is demonstrably a different process: that item reports
`ALREADY_GONE`, because what the handle names is gone, and a stranger holding
its number is not it.

The check is deliberately `_identity.recycled` and not `not
identity_holds`: a leader that has exited and been REAPED leaves a pid that
names nothing at all, while its process group can still hold live children --
the single-pid-SIGKILL failure class this module exists to close, inverted.
Only a pid whose occupant is provably someone else is a reason to signal
nothing.

This is why teardown here signals the process **group** (`os.killpg`, never
a single pid) at every rung, and why "ended" is only ever reported after an
independent, post-signal observation of the group's membership -- never
inferred from "the signal call did not raise".

task-027 (decision-042) adds the second kind `KillReport.items` can hold:
`kill_jail` tears down the workload group FIRST, then every exec sibling
the handle names -- through the SAME ladder function, per SPEC.md §9's "the
ladder runs per item, and there is only one ladder." A sibling is found by
listing `brig/run/_execs.py`'s registration directory under `handle.jail_dir`
(never from an in-memory registration -- `Handle` is frozen and carries
none), which is what makes this work for a handle rehydrated in a process
that never itself called `exec()`. That directory replaced the event
stream's `EXEC`-without-`EXEC_END` pairing at decision-152 (2026-09-08),
when the stream was deleted; the durability clause SPEC.md §9 binds this to
is unchanged, only its medium.

**`kill` no longer writes a `KILL` record either** (decision-152). The
report this function RETURNS is the record: it carries every item, and it
carried strictly more than the events did (the events were an
already-lossy copy written after the fact). An embedder that wants the
teardown in its log writes the returned `KillReport` there.

**Group-membership check**: not `os.killpg(pgid, 0)` (which reports "at
least one member exists", not "which"), but a fresh `/bin/ps -Ao pid=,pgid=`
scan (alias-proof per decision-026) filtered to the target `pgid` -- the
same technique `tests/integration/test_launcher.py`'s `_children_of`
already uses. This module never signals a single pid on its own: the
leader is reaped (`os.waitpid`, `WNOHANG`) purely so a zombie the trusted
process is the real parent of does not make the group look perpetually
non-empty; reaping is not a teardown signal and sends nothing.

`kill_jail` is idempotent: called again on an already-torn-down group, the
group-membership scan is empty immediately, no signal is sent, and the
item reports `ALREADY_GONE`.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from brig.run import _execs, _identity, _waiters

#: SPEC.md §9: "grace period (default 2.0s, a keyword argument)". Applied
#: once after SIGTERM (letting a cooperative group exit on its own) and
#: again, as an upper bound, after SIGKILL (which cannot be ignored, but a
#: reparented descendant still needs the kernel a moment to actually remove
#: it from the process table once signalled).
DEFAULT_GRACE_S: Final = 2.0

#: How often the post-signal verification loop re-scans `/bin/ps` while
#: waiting out a grace period. Short relative to `DEFAULT_GRACE_S` so a
#: group that dies quickly is observed quickly, not held to the full grace
#: window.
_POLL_INTERVAL_S: Final = 0.02

#: SPEC.md §9: closed vocabulary of kinds that a KillReport item can hold.
#: Ordered as the spec lists them. A jail produces "workload_group",
#: "exec_sibling" and "helper" today; M10 adds "container". `"pane"` went
#: with the `tmux` launcher (decision-154, 2026-09-08) -- it named a thing
#: only that launcher could produce, and nothing will ever produce one now.
KILL_ITEM_KINDS: Final = ("workload_group", "exec_sibling", "helper", "container")


class KillOutcome(Enum):
    """Per-item teardown outcome. Ambiguity A11 in the M2 plan: SPEC.md §9
    requires per-item reporting and never fixes this enum's members; these
    three are the ones a verified group-teardown can actually produce."""

    ENDED = "ENDED"
    ALREADY_GONE = "ALREADY_GONE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class KillItem:
    """One torn-down (or already-gone, or un-teardownable) thing the
    handle names. `kind` is `"workload_group"` for the workload item and
    `"exec_sibling"` for each exec sibling (task-027, decision-042); the
    two kinds a jail can produce today, alongside `"helper"`;
    `"container"` is M10's to add. `identity` is the pgid, as text, for
    every kind a jail produces."""

    kind: str
    identity: str
    outcome: KillOutcome
    detail: str

    def __post_init__(self) -> None:
        """Validate that `kind` is in the closed vocabulary
        KILL_ITEM_KINDS. decision-054: constructing a KillItem with a kind
        outside the vocabulary must fail."""
        if self.kind not in KILL_ITEM_KINDS:
            raise ValueError(f"KillItem kind must be one of {KILL_ITEM_KINDS}, got {self.kind!r}")


@dataclass(frozen=True, slots=True)
class KillReport:
    """Everything `kill()` tore down (or found already gone), one item per
    thing: the workload group first, then one item per exec sibling
    (task-027) in the order they were registered. The shape
    is per-item so a later mechanism can append helpers/containers without
    a shape change."""

    items: tuple[KillItem, ...]


def _group_member_pids(pgid: int) -> list[int]:
    """Every pid currently in process group `pgid`, per a fresh `/bin/ps`
    scan of the whole process table (`/bin/ps -Ao pid=,pgid=`, alias-proof
    per decision-026 -- never a bare `ps`). This is the module's sole
    source of truth for "is the group still there": a signal call
    succeeding proves only that the signal was deliverable, never that
    anything ended (SPEC.md §9's verification rung)."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid="],
        capture_output=True,
        text=True,
        check=True,
    )
    members: list[int] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        pid_s, pgid_s = parts
        if int(pgid_s) == pgid:
            members.append(int(pid_s))
    return members


def _reap_leader(leader_pid: int) -> None:
    """Collect the workload leader's exit status if it has one waiting.
    The trusted process is this pid's real parent (`SubprocessLauncher`
    spawned it directly), so until this runs, a dead leader sits as a
    zombie that `/bin/ps` still reports -- which would make
    `_group_member_pids` report the group as non-empty forever. This sends
    no signal; it only reaps what already exited. Safe to call on an
    already-reaped pid (idempotent second `kill_jail` call) or a pid this
    process never parented (`ChildProcessError`) -- both suppressed."""
    if _waiters.is_watched(leader_pid):
        # A waiter thread owns this reap and will record the EXIT status.
        # Racing it with waitpid here would win sometimes and destroy the
        # status the waiter exists to capture.
        return
    with contextlib.suppress(ChildProcessError, ProcessLookupError):
        os.waitpid(leader_pid, os.WNOHANG)


def _wait_until_group_gone(pgid: int, leader_pid: int, deadline: float) -> bool:
    """Poll `_group_member_pids` (reaping the leader on every iteration)
    until the group is empty or `deadline` (a `time.monotonic()` value)
    passes. Returns whether the group was observed empty."""
    while True:
        _reap_leader(leader_pid)
        if not _group_member_pids(pgid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL_S)


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    """Signal the process **group** -- never a single pid; that
    distinction is the entire subject of this module (SPEC.md §9's
    "single-pid SIGKILL that leaves the interesting child alive"). A group
    that has already vanished raises `ProcessLookupError`, which is not a
    failure here -- the verification rung is what actually decides the
    outcome, not whether this call raised.

    `PermissionError` is suppressed for the same reason, for a
    platform-specific fact task-027 surfaced (confirmed on darwin, this
    tree's only tested platform per README.md's honesty section): once a
    process group's only remaining member is an unreaped zombie (exited,
    not yet reaped by its REAL parent -- exactly `_run_ladder`'s
    cross-process case, task-027 AC #3, where `_reap_leader` is a
    documented no-op), `os.killpg` on that pgid raises `EPERM`, not
    `ESRCH`, even for the caller's own zombie. Without this, the SIGKILL
    escalation rung would crash `kill_jail` outright on exactly the
    handle-rehydrated-elsewhere path SPEC.md §9 exists to cover, instead of
    reporting `FAILED` honestly if the group truly never clears."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def _run_ladder(
    pgid: int, leader_pid: int, leader_stamp: str, grace: float
) -> tuple[KillOutcome, str]:
    """SPEC.md §9's fixed ladder, run against ONE group -- the workload
    group or one exec sibling, identically (task-027: "The ladder runs per
    item, and there is only one ladder"):

    0. If `leader_pid` names a process that is provably NOT the one
       `leader_stamp` was taken from, the OS recycled the number: report
       `ALREADY_GONE` and signal nothing (decision-155).
    1. If the group is already gone (idempotent re-call, or the process
       had already exited on its own), report `ALREADY_GONE` -- no signal
       sent.
    2. `SIGTERM` to the group, then verify for up to `grace` seconds.
    3. If anything survives, `SIGKILL` to the group, then verify again for
       up to `grace` seconds.
    4. Report `ENDED` only if the post-signal scan actually found the
       group empty; `FAILED` if it never does (a permission failure, or a
       process a kernel signal cannot remove for reasons outside this
       module's control).

    `leader_pid` is reaped (`_reap_leader`) before every group-membership
    check -- this process's own child (the workload leader, or an exec
    sibling THIS process itself started) would otherwise linger as a
    zombie `/bin/ps` keeps reporting. When `leader_pid` is not this
    process's child (a rehydrated handle tearing down an exec sibling it
    never itself started, task-027 AC #3), `_reap_leader` is a documented
    no-op (`ChildProcessError`, suppressed) -- the real parent still owns
    reaping it, exactly like `Handle.alive()`'s own stated limit on a
    rehydrated handle.
    """
    if _identity.recycled(leader_pid, leader_stamp):
        # decision-155. The pid exists, but it is not the process this
        # handle recorded: the OS reused the number. Signalling the group
        # now would signal a stranger, so nothing is sent and the item
        # reports what is true -- what the handle named is gone.
        return (
            KillOutcome.ALREADY_GONE,
            f"pid {leader_pid} now names a different process (start time does not match "
            "the one recorded at launch); nothing was signalled",
        )

    _reap_leader(leader_pid)
    if not _group_member_pids(pgid):
        return KillOutcome.ALREADY_GONE, "process group had already ended before kill() ran"

    _signal_group(pgid, signal.SIGTERM)
    ended = _wait_until_group_gone(pgid, leader_pid, time.monotonic() + grace)

    if not ended:
        _signal_group(pgid, signal.SIGKILL)
        ended = _wait_until_group_gone(pgid, leader_pid, time.monotonic() + grace)

    if ended:
        return KillOutcome.ENDED, ""
    return (
        KillOutcome.FAILED,
        f"process group {pgid} still had member(s) after SIGTERM+grace and SIGKILL+grace",
    )


def _live_exec_siblings(handle: Any) -> list[tuple[int, int, str]]:
    """`(pid, pgid)` for every exec sibling `handle` has registered
    (SPEC.md §9: "`exec` records the sibling ... somewhere the handle can
    read back in a later process") and whose exit status has not yet been
    observed -- read from `brig/run/_execs.py`'s registration directory
    under `handle.jail_dir`, not from any in-memory state, which is what
    lets a handle rehydrated in a LATER process find execs it never itself
    started (task-027, decision-042; medium changed by decision-152).
    Order matches registration order.

    Each registration carries the sibling's start-time stamp alongside its
    pid and pgid (decision-155), which is what closes the reuse gap this
    docstring used to name as open: a pid the OS handed to something else
    between one sibling's deregistration and this scan is signalled by
    nothing, because `_run_ladder` compares the stamp before it signals.
    """
    return _execs.live(handle.jail_dir)


def kill_jail(handle: Any, *, grace: float = DEFAULT_GRACE_S) -> KillReport:
    """Tear down EVERYTHING `handle` names -- the workload group, then
    every still-live exec sibling it registered (task-027), then every
    `JAIL_LIFETIME` helper -- through the same ladder (`_run_ladder`),
    workload first. The returned `KillReport` is the record: nothing is
    written anywhere (decision-152)."""
    items: list[KillItem] = []

    outcome, detail = _run_ladder(handle.pgid, handle.pid, handle.start_time, grace)
    items.append(
        KillItem(kind="workload_group", identity=str(handle.pgid), outcome=outcome, detail=detail)
    )

    for pid, pgid, stamp in _live_exec_siblings(handle):
        outcome, detail = _run_ladder(pgid, pid, stamp, grace)
        items.append(
            KillItem(kind="exec_sibling", identity=str(pgid), outcome=outcome, detail=detail)
        )

    # `Step.helpers` with JAIL_LIFETIME (SPEC.md §6). Each ran with
    # `start_new_session=True`, so its pid is its own pgid and the same
    # ladder applies. "Kill leaves nothing" (§9) covers helpers: a proxy
    # that outlives the jail it filtered for is a listening socket nobody
    # owns.
    for helper_pid, helper_stamp in zip(handle.helper_pids, handle.helper_stamps, strict=True):
        outcome, detail = _run_ladder(helper_pid, helper_pid, helper_stamp, grace)
        items.append(
            KillItem(kind="helper", identity=str(helper_pid), outcome=outcome, detail=detail)
        )

    return KillReport(items=tuple(items))
