"""Group teardown of a jail: `Jail.destroy` and `Process.stop` (`kill()` until
decision-183), filled in by task-020.

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
serialized jail in an embedder's log is exactly. So every item this
module tears down now carries the moment its leader STARTED as well as its
number (`brig/run/_identity.py`), and `_run_ladder` refuses to signal a pid
whose current occupant is demonstrably a different process: that item reports
`ALREADY_GONE`, because what the jail names is gone, and a stranger holding
its number is not it.

The check is deliberately `_identity.recycled` and not `not
identity_holds`: a leader that has exited and been REAPED leaves a pid that
names nothing at all, while its process group can still hold live children --
the single-pid-SIGKILL failure class this module exists to close, inverted.
Only a pid whose occupant is provably someone else is a reason to signal
nothing -- that, and a record with no stamp at all (decision-172,
2026-10-11): an unknown stamp leaves nothing to show the group is the jail's,
and a registration in a `jail_dir` the jail can write may be forged, so the
ladder signals nothing for it and the item says why.

This is why teardown here signals the process **group** (`os.killpg`, never
a single pid) at every rung, and why "ended" is only ever reported after an
independent, post-signal observation of the group's membership -- never
inferred from "the signal call did not raise".

task-027 (decision-042) adds the second kind `KillReport.items` can hold:
teardown ends the workload group FIRST, then every exec sibling
the jail names -- through the SAME ladder function, per SPEC.md §9's "the
ladder runs per item, and there is only one ladder." A sibling is found by
listing the records under `<jail_dir>/procs` (`brig/run/_records.py`, one
directory per process since decision-181; before it, a registration file
per sibling, and before decision-152 the event stream), never from an in-memory registration, which
is what makes this work for a jail rehydrated in a process that never
itself started the sibling. The durability clause SPEC.md §9 binds this to is
unchanged, only its medium.

**`kill` no longer writes a `KILL` record either** (decision-152). The
report this function RETURNS is the record: it carries every item, and it
carried strictly more than the events did (the events were an
already-lossy copy written after the fact). An embedder that wants the
teardown in its log writes the returned `KillReport` there.

**Group-membership check**: not `os.killpg(pgid, 0)` (which reports "at
least one member exists", not "which"), but a fresh `/bin/ps -Ao pid=,pgid=`
scan (alias-proof per decision-026) filtered to the target `pgid`, zombies
left out (decision-171: a zombie has ended, and where PID 1 does not reap it
would stay in the table forever) -- the same technique
`tests/integration/test_host_launch.py`'s `_children_of` already uses. This
module never signals a single pid on its own: the leader is reaped
(`os.waitpid`, `WNOHANG`) purely so a zombie the trusted process is the
real parent of does not make the group look perpetually non-empty;
reaping is not a teardown signal and sends nothing.

Teardown is idempotent: called again on an already-torn-down group, the
group-membership scan is empty immediately, no signal is sent, and the
item reports `ALREADY_GONE`.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

from brig.run import _identity, _records, _waiters

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
    jail names. `kind` is `"workload_group"` for the workload item and
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


class UnreadableProcessTable(ValueError):
    """The text of `ps -Ao pid=,pgid=,stat=` has a row that is not exactly
    pid, pgid and state: a table brig cannot read is no evidence a group is
    gone."""


def _live_group_members(ps_output: str, pgid: int) -> list[int]:
    """The pids in group `pgid` that are not zombies, from the text of
    `/bin/ps -Ao pid=,pgid=,stat=`. A zombie (state `Z` on Linux and darwin)
    has exited: nothing of it runs, and only its parent's `wait` -- or PID 1's,
    once reparented -- removes the row. Where PID 1 does not reap, a killed
    child stays in the table for good, so counting it would read a dead jail as
    surviving (TASK-0077, decision-171). Blank lines are skipped.

    Raises:
        UnreadableProcessTable: a non-blank row is not exactly an integer pid,
            an integer pgid and a non-empty state (a header, a missing or an
            extra column). Skipping it could read a live group as gone.
    """
    members: list[int] = []
    for line in ps_output.splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 3:
            raise UnreadableProcessTable(
                f"process table row {line!r} is not 'pid pgid stat'; the table cannot be read"
            )
        pid_s, pgid_s, state = parts
        try:
            pid, row_pgid = int(pid_s), int(pgid_s)
        except ValueError:
            raise UnreadableProcessTable(
                f"process table row {line!r} has a non-integer pid or pgid; the table cannot be read"
            ) from None
        if row_pgid == pgid and not state.startswith("Z"):
            members.append(pid)
    return members


def live_groups(ps_output: str) -> frozenset[int]:
    """Every process group with a member that is not a zombie, from the text
    of `/bin/ps -Ao pid=,pgid=,stat=` (`_live_group_members`'s reading of the
    table, for every group at once).

    Raises:
        UnreadableProcessTable: a non-blank row is not exactly pid, pgid and state.
    """
    groups: set[int] = set()
    for line in ps_output.splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 3:
            raise UnreadableProcessTable(
                f"process table row {line!r} is not 'pid pgid stat'; the table cannot be read"
            )
        _pid, pgid_s, state = parts
        try:
            int(_pid)
            pgid = int(pgid_s)
        except ValueError:
            raise UnreadableProcessTable(
                f"process table row {line!r} has a non-integer pid or pgid; the table cannot be read"
            ) from None
        if not state.startswith("Z"):
            groups.add(pgid)
    return frozenset(groups)


def read_process_table() -> str:
    """The whole process table as text: `/bin/ps -Ao pid=,pgid=,stat=`
    (alias-proof per decision-026 -- never a bare `ps`).

    Raises:
        OSError: `/bin/ps` cannot be run.
        subprocess.CalledProcessError: `/bin/ps` ran and failed.
    """
    return subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid=,stat="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _group_member_pids(pgid: int) -> list[int]:
    """Every live (non-zombie) pid currently in process group `pgid`, per a
    fresh scan of the whole process table. This is the module's sole source of
    truth for "is the group still there": a signal call succeeding proves only
    that the signal was deliverable, never that anything ended (SPEC.md §9's
    verification rung)."""
    return _live_group_members(read_process_table(), pgid)


def group_alive(pgid: int, *, read_table: Callable[[], str] = read_process_table) -> bool:
    """Whether process group `pgid` still has a member that runs: the one
    definition of "the group is there" that teardown's verification rung and
    an embedder's liveness check share (decision-176, TASK-0079.19).

    A group with at least one member not in state `Z` reads alive. A group
    with no rows, or only zombies, reads gone (a zombie has exited; where PID 1
    does not reap it stays for good, which `os.killpg(pgid, 0)` cannot see).
    When the process table cannot be read (`/bin/ps` missing or failing, or a
    row that is not `pid pgid stat`) the answer is alive: a caller that sweeps
    what is dead keeps what it cannot prove dead. `read_table` is the seam for
    that failure; it returns the text of `ps -Ao pid=,pgid=,stat=` and raises
    `OSError` or `subprocess.CalledProcessError` as the default does; a table
    it returns with a malformed row reads alive too."""
    try:
        table = read_table()
    except OSError, subprocess.CalledProcessError:
        return True
    try:
        return bool(_live_group_members(table, pgid))
    except UnreadableProcessTable:
        return True


def _reap_leader(leader_pid: int) -> None:
    """Collect the workload leader's exit status if it has one waiting.
    The trusted process is this pid's real parent (`HostSupervisor.start`
    spawned it directly), so until this runs, a dead leader sits as a
    zombie that `/bin/ps` still reports -- which would make
    `_group_member_pids` report the group as non-empty forever. This sends
    no signal; it only reaps what already exited. Safe to call on an
    already-reaped pid (an idempotent second `destroy`) or a pid this
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
    escalation rung would crash `destroy` outright on exactly the
    jail-rehydrated-elsewhere path SPEC.md §9 exists to cover, instead of
    reporting `FAILED` honestly if the group truly never clears."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def _run_ladder(
    pgid: int, leader_pid: int, leader_stamp: str, grace: float
) -> tuple[KillOutcome, str]:
    """SPEC.md §9's fixed ladder, run against ONE group -- the workload
    group or one exec sibling, identically (task-027: "The ladder runs per
    item, and there is only one ladder"):

    0. If `leader_stamp` is unknown, the record cannot be verified: signal
       nothing and reap nothing, and report `ALREADY_GONE` if the group has
       no live member, else `FAILED` (decision-172).
       If `leader_pid` names a process that is provably NOT the one
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
    process's child (a rehydrated jail tearing down an exec sibling it
    never itself started, task-027 AC #3), `_reap_leader` is a documented
    no-op (`ChildProcessError`, suppressed) -- the real parent still owns
    reaping it, exactly like `Process.alive()`'s own stated limit on a
    rehydrated jail.
    """
    if leader_stamp == _identity.UNKNOWN:
        # decision-172. No start time was recorded, so nothing shows this
        # pid or this group is the jail's. (A jail can no longer forge the
        # record, decision-173/174, but a launch that read no stamp, a record
        # tampered with on the host or a disk fault still can leave one.)
        # Nothing is signalled, and nothing reaped
        # either (the pid may be another child of this process, whose status
        # is not teardown's to take); a live member reads as FAILED.
        if not _group_member_pids(pgid):
            return KillOutcome.ALREADY_GONE, "process group had already ended before kill() ran"
        return (
            KillOutcome.FAILED,
            f"no start time was recorded for pid {leader_pid}, so nothing shows process group "
            f"{pgid} is this jail's; nothing was signalled. List its members (`ps -eo pid,pgid,args`) "
            f"and, if they are this jail's, end them yourself (`kill -KILL -- -{pgid}`)",
        )

    if _identity.recycled(leader_pid, leader_stamp):
        # decision-155. The pid exists, but it is not the process this
        # jail recorded: the OS reused the number. Signalling the group
        # now would signal a stranger, so nothing is sent and the item
        # reports what is true -- what the jail named is gone.
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


def _unsignalable(pgid: int, own_pgid: int) -> str | None:
    """Why `pgid` must never be signalled, or `None` if it may be. 0 means the
    caller's own group to `killpg`, 1 is init's, a negative one is no group, and
    `own_pgid` is the trusted process itself: a record naming any of them aims
    teardown at the process doing the tearing down (or at the machine)."""
    if pgid == own_pgid:
        return f"process group {pgid} is this process's own"
    if pgid <= 1:
        return f"{pgid} is not a process group a jail can have"
    return None


def _guarded_ladder(
    pgid: int, leader_pid: int, leader_stamp: str, grace: float
) -> tuple[KillOutcome, str]:
    """`_run_ladder` for one item, behind the two things that make teardown
    total: a group that must never be signalled is refused (`FAILED`, nothing
    signalled), and any exception the ladder raises (a `ps` that failed, a pid
    the OS rejects) becomes this item's `FAILED` outcome, so one item can never
    stop the next.

    Raises nothing from an item; only `BaseException`s that are not
    `Exception`s (`KeyboardInterrupt`, `SystemExit`) pass through.
    """
    refusal = _unsignalable(pgid, os.getpgrp())
    if refusal is not None:
        return (
            KillOutcome.FAILED,
            f"{refusal}; nothing was signalled. Inspect the record that named it "
            "and, if it names processes of this jail, end them yourself",
        )
    try:
        return _run_ladder(pgid, leader_pid, leader_stamp, grace)
    except Exception as error:
        return (
            KillOutcome.FAILED,
            f"tearing down process group {pgid} raised {type(error).__name__}: {error}; "
            "what it names may still run. List its members (`ps -eo pid,pgid,args`) "
            f"and, if they are this jail's, end them yourself (`kill -KILL -- -{pgid}`)",
        )


def _unreadable_item(unreadable: _records.Unreadable) -> KillItem:
    """The `FAILED` item for an entry under `procs/` brig cannot read as a
    record. Nothing it names is known, so nothing is signalled; the detail says
    where to look."""
    return KillItem(
        kind="exec_sibling",
        identity=unreadable.path,
        outcome=KillOutcome.FAILED,
        detail=(
            f"process record {unreadable.path} {unreadable.reason}; nothing it names was "
            "signalled. Inspect it: if it names a process of this jail, end that process "
            "yourself, and remove it"
        ),
    )


def _disagreeing_item(kind: str, jail_dir: str, on_disk: _records.ProcessRecord) -> KillItem:
    """The `FAILED` item for a record on disk that disagrees with the one the
    caller holds for the same process (decision-181): the held identity is
    ended through the ladder as its own item, and this copy signals nothing it
    names. Its identity is the file's path, its `kind` the held process's."""
    path = os.path.join(_records.process_dir(jail_dir, on_disk.id), _records.RECORD_FILENAME)
    return KillItem(
        kind=kind,
        identity=path,
        outcome=KillOutcome.FAILED,
        detail=(
            f"process record {path} disagrees with the record the caller holds for "
            f"process {on_disk.id} (it names pid {on_disk.pid}, process group "
            f"{on_disk.pgid}); the held identity was ended, and nothing this copy names "
            "was signalled. Something rewrote it: inspect it, and if it names a process "
            "of this jail, end that process yourself"
        ),
    )


def end_group(
    kind: str, pgid: int, leader_pid: int, leader_stamp: str, *, grace: float = DEFAULT_GRACE_S
) -> KillItem:
    """One item of a `KillReport`: the ladder against one group, guarded
    (`_guarded_ladder`), reported as `kind` with the pgid as its identity.
    The workload group, an exec sibling and a helper are each ended through
    this, and `HostSupervisor.stop` ends one process's group with it.

    Raises nothing from the item; only `BaseException`s that are not
    `Exception`s pass through."""
    outcome, detail = _guarded_ladder(pgid, leader_pid, leader_stamp, grace)
    return KillItem(kind=kind, identity=str(pgid), outcome=outcome, detail=detail)


def kill_named(
    *,
    known: Sequence[_records.ProcessRecord],
    jail_dir: str,
    helper_pids: tuple[int, ...],
    helper_stamps: tuple[str, ...],
    grace: float = DEFAULT_GRACE_S,
) -> KillReport:
    """Tear down EVERYTHING a jail names, through the same ladder
    (`_run_ladder`), per process in start order, then every `JAIL_LIFETIME`
    helper (decision-181). The returned `KillReport` is the record: nothing
    is written anywhere (decision-152). `HostRuntime.destroy` comes here.

    The processes are `known`, the ones the caller holds in memory, in start
    order, then every record under `<jail_dir>/procs` whose id `known` does
    not name (`_records.scan`), in start order: what a later start, or a
    start in another process, recorded. A known process is ended by the
    identity the caller holds, never by a disk copy of it; a disk copy that
    disagrees with it (`_records.disagrees`) is its own `FAILED` item, its
    identity the file's path, signalling nothing it names (decision-181). The first process
    is reported as `workload_group` and every later one as `exec_sibling`, so
    a report reads as it did when only the first process had a group of its
    own. A record outlives its process's `wait`, so a waited process is
    still ended here: its group, if empty, reads `ALREADY_GONE`, and anything
    it left running in that group is ended.

    Total (decision-175): an entry under `procs/` that cannot be read as a
    record is its own `FAILED` item, and each item's ladder runs inside
    `_guarded_ladder`, so no exception from one item stops the next. Raises
    nothing from an item.

    Raises:
        ValueError: `helper_stamps` does not have one entry per helper pid.
    """
    if len(helper_stamps) != len(helper_pids):
        raise ValueError(
            f"kill_named: {len(helper_stamps)} helper stamp(s) for {len(helper_pids)} pid(s)"
        )
    held = {process.id: process for process in known}
    scanned = _records.scan(jail_dir)
    processes = (
        *known,
        *(record for record in scanned.records if record.id not in held),
    )
    disagreeing = tuple(
        record
        for record in scanned.records
        if record.id in held and _records.disagrees(held[record.id], record)
    )
    items: list[KillItem] = [
        end_group(
            "workload_group" if position == 0 else "exec_sibling",
            process.pgid,
            process.pid,
            process.start_time,
            grace=grace,
        )
        for position, process in enumerate(processes)
    ]
    kinds = {
        process.id: "workload_group" if position == 0 else "exec_sibling"
        for position, process in enumerate(processes)
    }
    items.extend(_disagreeing_item(kinds[record.id], jail_dir, record) for record in disagreeing)
    items.extend(_unreadable_item(unreadable) for unreadable in scanned.unreadable)

    # `Step.helpers` with JAIL_LIFETIME (SPEC.md §6). Each ran with
    # `start_new_session=True`, so its pid is its own pgid and the same
    # ladder applies. "Kill leaves nothing" (§9) covers helpers: a proxy
    # that outlives the jail it filtered for is a listening socket nobody
    # owns.
    items.extend(
        end_group("helper", helper_pid, helper_pid, helper_stamp, grace=grace)
        for helper_pid, helper_stamp in zip(helper_pids, helper_stamps, strict=True)
    )

    return KillReport(items=tuple(items))
