"""Suite-wide gates: tier markers are mandatory, and tests leave no residue.

The leak-check grows with the library: process groups (M2), helper
processes (M3+), containers (M10). Each
milestone that spawns a new kind of thing extends this file in the same PR.

M2's process-group check is deliberately NOT registration-based: a registry
only catches leaks from tests that remembered to register, which is the
leak class least likely to happen. Instead every workload the suite ever
launches is required to carry a per-run token in its argv (see
`workload_argv`), and a background poller plus a session-teardown `/bin/ps`
sweep look for that token -- and for the process groups it was ever seen
tagging -- with no cooperation required from the test that leaked.

**task-027's third arm: a leaked exec sibling.** `handle.exec()`'s argv is
CALLER-supplied, not built by any brig code, so the two arms above are
structurally blind to a leaked exec sibling whose caller never bothered to
route it through `workload_argv`: no run-id token then ever lands in its
command line, and `start_new_session=True` gives it a pgid the background
poller's token-match never had a reason to tag. The fix is a THIRD arm at
final sweep only (not the continuous poller -- see below): any process
whose `ppid` is this session's own pid (`harness_pid`, captured the same
way as `harness_pgid`) and is still alive at teardown is a leak, full stop
-- every jail workload and every exec sibling this suite ever launches is
this process's direct child while it runs, and every one of them is
expected to be gone (reaped, one way or another) by the time the SESSION
ends, whichever test launched it. This arm is deliberately restricted to
the one-shot final sweep, not the poller: `_ps_rows()`'s own `/bin/ps`
invocation is unavoidably its own row (it lists itself while it is still
enumerating), and a *synchronous* helper `/bin/ps` call some other test
makes (`_ps_pgid`-shaped helpers exist in several test files) is a genuine,
transient child of this same pid that would false-positive a continuously
sampling poller if it happened to overlap a sample; by final-sweep time
every such synchronous call other tests made has long since returned and
been reaped, so the only self-observation left to exclude is this sweep's
own `/bin/ps` command line, which it excludes by exact match. A zombie
(exited, unreaped) still counts as a leak here on purpose -- that is
exactly the failure class `teardown._reap_leader` exists to close, and
letting a zombie slip past a leak-check would defeat the point of adding
this arm at all.

**task-035's fourth arm: a grandchild.** doc-007 §8 A-3 named the gap
decision-050's EC6 rewording left open, unruled at the M2 gate: M3 adds a
THIRD spawn route (`python -m brig.mech.trampoline … -- argv`), and the
harness-child arm above keys on `ppid == harness_pid`, one generation only --
a trampoline that execs, or a mechanism helper's own child, is a grandchild
that arm cannot see. `_harness_grandchild_pids` extends the sweep by exactly
one generation past it; see that function's own docstring for precisely what
it catches and what it does not (decision-050's positive-claim-with-blind-
spots voice). This paragraph and the new arm's code are pure additions: no
line above this one in this file is changed by task-035 -- including the
"three arms" and "THIRD arm" phrasing already on the page, which now
undercounts by one on purpose. That is this task's own zero-deletion `git
diff` pin (WORKFLOW.md decision-026 rule 2), not an oversight left uncorrected.

**task-049: a spawn registry becomes the PRIMARY channel; the four arms
above are demoted to SECONDARY.** The paragraph opening this docstring argues
against a registry on the grounds that "a registry only catches leaks from
tests that remembered to register" -- true of a registry a *test* populates
by hand, and this is not that. `subprocess.Popen.__init__` is wrapped for the
session (installed and restored by the `run_id` fixture below) so every
process this suite spawns through the stdlib's own spawn point is recorded
automatically, with the same zero-cooperation guarantee the token arm always
offered -- on a channel, `os.kill(pid, 0)` / `os.killpg(pgid, 0)`, that does
not read a command line at all, so it cannot be defeated by one being too
long to fit in `/bin/ps`'s `command=` column (`doc-013` §13.8 ask 8's
"marker early in argv" dead end) or too briefly readable mid-exec to match
(`doc-013` §3's measured race, the failure that actually took the M3 gate
down). See `_sweep_registry`'s docstring, just above the SECONDARY banner
below, for the registry's exact liveness rules, and the `run_id` fixture for
where PRIMARY and SECONDARY are combined into one failure. The four existing
arms are unchanged in code -- not deleted, per this task's own Deliverable --
and remain exactly what they were for a process the registry never saw (a
grandchild that escaped its own process group before `os.getpgid` could read
it, most plausibly).
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any, Final

import pytest

# How often the background poller samples `/bin/ps` for the run-id token,
# in seconds. This exists because the token can live only in the argv of
# the process a launcher's teardown code is *supposed* to signal (e.g. the
# `bash -c` leader), and a buggy teardown that kills that one pid instead
# of its process group leaves an untagged orphan behind with no token in
# its own command line. Sampling continuously -- not just once at session
# teardown -- lets the sweep learn "this pgid once carried the token"
# while the token-bearing process is still alive, so it can still catch
# that pgid's survivors after the tagged process is gone.
_POLL_INTERVAL_S = 0.05

_TIERS = frozenset({"unit", "integration", "e2e"})

#: The tiers are `unit`, `integration` and `e2e` (an older spelling called the
#: top tier `system`; same tests, same platform gating, same meaning).

#: Everything above the unit tier drives a REAL OS mechanism: process groups,
#: `setrlimit`, `/bin/ps`, `sandbox-exec`. Darwin-only mechanisms carry their
#: own `skipif` at the module that uses them; this is the floor beneath those
#: -- on a platform with no POSIX process model at all there is nothing for
#: these tests to observe, and a jail that cannot be built is not a failing
#: jail. They skip, loudly and by name, rather than erroring out of fixtures.
_OS_TIERS = frozenset({"integration", "e2e"})
_BRIG_TESTS_ROOT = pathlib.Path(__file__).resolve().parent


def platform_skip_reason(os_name: str, tiers: frozenset[str]) -> str | None:
    """The skip reason for a test in `tiers` on a host whose `os.name` is
    `os_name`, or `None` to run it.

    Split out of the collection hook below, and taking `os.name` as an
    ARGUMENT rather than reading it, for one reason: on every machine this
    workspace runs on -- the darwin development machine and the ubuntu CI
    runner alike -- `os.name` is `"posix"`, so the branch that actually
    skips is structurally unreachable from any runner in
    `.github/workflows/verify.yml`. As a hook-local expression it could only
    ever be proven by a Windows runner nobody has. As a pure function it is
    proven by `tests/unit/test_tier_gate.py` passing `"nt"` in, which is a
    real test of the DECISION and still not a test of the skip actually
    taking effect during collection on a non-POSIX host. That second thing
    remains unproven here and is not claimed.
    """
    if os_name == "posix" or not (tiers & _OS_TIERS):
        return None
    return (
        f"brig's {sorted(tiers)[0]} tier drives real POSIX process "
        f"mechanisms; os.name is {os_name!r}"
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Fail collection for any test not carrying exactly one tier marker.

    Also skip brig's OS-driven tiers where the OS cannot host them. The hook
    sees the whole session's items, brig's and the rest of the workspace's
    alike, and both checks are facts about brig's tests only: the tier
    vocabulary is brig's, so only items under this directory are held to it.
    """
    for item in items:
        if _BRIG_TESTS_ROOT not in pathlib.Path(str(item.path)).parents:
            continue
        found = _TIERS & {mark.name for mark in item.iter_markers()}
        if len(found) != 1:
            raise pytest.UsageError(
                f"{item.nodeid}: must carry exactly one of {sorted(_TIERS)}, found {sorted(found)}"
            )
        reason = platform_skip_reason(os.name, found)
        if reason is not None:
            item.add_marker(pytest.mark.skip(reason=reason))


def workload_argv(run_id: str, body: str) -> list[str]:
    """Build a `bash -c` argv for a test workload that carries `run_id`.

    The token is embedded as the FIRST LINE of the `-c` script -- i.e. the
    first argv content after the interpreter -- never appended after
    `body`. This is load-bearing, not cosmetic: `ps` truncates long command
    lines, and M2's workloads are not short (a `bash -c` wrapper around a
    multi-line `python -c` body is the longest shape in play). A token
    placed after a long `body` can land past the truncation boundary, at
    which point the leak sweep matches nothing and every clean run still
    looks green.

    `body` is run in a background job and waited on
    (`<body> & wait`), which is the shape every M2 workload launcher uses
    so the resulting process group outlives the immediate child.

    PRECONDITION ON THE CALLER, not enforced here (this function only
    builds argv; it never spawns anything): launch this argv with
    `subprocess.Popen(argv, start_new_session=True)`, or an equivalent call
    that gives the resulting process its own process group. The leak sweep
    tells this workload apart from the test harness's own long-lived
    processes (the shell / `uv` / `pytest` chain running the suite) by
    pgid; a workload that is never given its own pgid shares the harness's,
    and a same-group descendant of it that no longer carries the token in
    its own argv (e.g. because a launcher's teardown killed only the
    immediate leader pid, not the group) is then indistinguishable from the
    harness's own processes and goes uncaught. See the `run_id` fixture's
    docstring for the reasoning and a reproduced example of that gap. Every
    M2 launcher must isolate its process group for this reason, independent
    of also wanting `killpg` to work on teardown.
    """
    token_line = f": BRIG_TEST_RUN_{run_id}"
    script = f"{token_line}\n{body} &\nwait"
    return ["bash", "-c", script]


# ============================================================================
# PRIMARY (task-049): the spawn registry. Liveness only -- no /bin/ps, no
# argv read anywhere in this block. See this module's docstring for why this
# replaces argv-matching as the primary channel.
# ============================================================================


def teardown_group(handle: object, *, timeout: float = 20.0) -> None:
    """Group-kill a launched workload, RE-SIGNALLING until the group clears.

    task-086, and the root cause it closes. Fifteen test modules had each
    grown their own `_teardown_group` with the same body: one
    `killpg(pgid, SIGKILL)`, then `handle.wait()` for the LEADER. That body
    leaks, intermittently, and here is the mechanism.

    A `workload_argv` workload is `<body> & wait` -- the leader forks a
    BACKGROUNDED child moments after it starts. A single `killpg` signals
    the members the kernel enumerates at that instant. When teardown lands
    while the workload is still starting up (this suite's exec tests run a
    fast `/usr/bin/true` and tear down almost immediately), the fork and the
    signal race: the leader is signalled and dies, and the child it forked
    concurrently can miss that one signal entirely. It is then orphaned to
    init and survives -- a live `sleep 100` with `ppid=1`, still carrying the
    dead leader's pgid.

    Nothing failed at the time. The survivor was found later by the
    session-scoped sweep, attributed to whatever test ran last, and a re-run
    hid it -- three investigations (task-073, task-075, task-086) each began
    by reading the wrong file. Reproduced deliberately for this fix: 1 in ~36
    runs of `test_exec_confinement.py` alone, and the registry's
    `spawned_by` field named the real culprit rather than the last test.

    **So the signal is a LOOP, not a single call**, and that is the fix: any
    child forked after an earlier `killpg` is signalled by the next pass.
    Verification is the loop's exit condition -- an empty group observed by
    the same `/bin/ps` scan the sweep uses -- so this cannot return while a
    member survives. If the group never clears it raises, naming the
    survivors, in the test that actually leaked.

    `PermissionError` is suppressed alongside `ProcessLookupError`, which the
    copies did not do: `brig/run/teardown.py`'s `_signal_group` documents
    that darwin raises EPERM, not ESRCH, once a group's only remaining member
    is an unreaped zombie -- even for the caller's own. Under the copies that
    EPERM escaped a cleanup path, erroring the test AND leaving the group
    alive. Demonstrated with a control: the old body raises PermissionError
    on that shape; this one does not.

    Deliberately NOT `Handle.kill()` / `kill_jail`: those are the code under
    test in several callers, and a test's cleanup path must not be the thing
    it is testing (the reasoning every copied helper already carried).
    """
    import signal as _signal

    pgid = handle.pgid  # type: ignore[attr-defined]
    deadline = time.monotonic() + timeout
    survivors: list[tuple[int, int, int, str, str]] = []
    while True:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, _signal.SIGKILL)
        with contextlib.suppress(Exception):
            handle.wait(timeout=0.5)  # type: ignore[attr-defined]

        # Zombies are excluded: an exited-but-unreaped member is not a leak,
        # and its own parent owns reaping it (`_reap_leader`'s documented
        # no-op case for a handle rehydrated in another process).
        survivors = [row for row in _ps_rows() if row[2] == pgid and not row[3].startswith("Z")]
        if not survivors:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"teardown_group: process group {pgid} still has live members "
                f"after {timeout}s of repeated SIGKILL -- this test leaked "
                f"them, and without this loop they would have surfaced later "
                f"against an unrelated test: {survivors!r}"
            )
        time.sleep(0.02)


def _is_ps_probe(args: object) -> bool:
    """True when a `subprocess.Popen` call is one of the suite's own `ps`
    housekeeping invocations (the background poller's `_ps_rows`, the
    teardown sweep's `_ps_rows`, or a test file's own local `_ps_rows` /
    `_ps_has_row_for` helper -- several shapes of this exist across the
    test files) rather than a workload under test.

    Excluded from the spawn registry on purpose: these calls are
    extremely short-lived, so recording every one of them -- the
    background poller alone samples every `_POLL_INTERVAL_S` for the
    whole session -- would bloat the registry with thousands of
    already-dead entries the final sweep has to walk for nothing, and
    opens a real, if small, pid-reuse window: a dead `ps` pid recorded
    here that the kernel later reissues to an unrelated live process
    before teardown would read back as `os.kill(pid, 0)` succeeding -- a
    false leak report against a process the suite never spawned as a
    workload at all. This mirrors the self-exclusion the harness-child
    arm below already does by exact command match; this one is by
    executable basename because more than one `ps` invocation shape
    exists in this file and the test files that copy its pattern.
    """
    argv: object = args
    if isinstance(args, (list, tuple)):
        argv = args[0] if args else None
    if isinstance(argv, bytes):
        try:
            argv = argv.decode()
        except UnicodeDecodeError:
            return False
    if isinstance(argv, os.PathLike):
        argv = os.fspath(argv)
    if isinstance(argv, str) and " " in argv:
        argv = argv.split(None, 1)[0]
    return isinstance(argv, str) and os.path.basename(argv) == "ps"


def _pid_liveness(pid: int) -> tuple[bool | None, str]:
    """Classify whether `pid` is alive using `os.kill(pid, 0)` alone --
    no argv is ever read. `True` means alive, `False` means confirmed
    gone (`ProcessLookupError`), `None` means liveness could not be
    determined (e.g. permission denied) -- a pid this cannot classify is
    reported by `_sweep_registry`, never silently treated as gone
    (task-049 AC #6).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False, "no such process"
    except PermissionError as exc:
        return None, f"permission denied ({exc})"
    except OSError as exc:
        return None, f"os error ({exc})"
    return True, "alive"


def _pgid_liveness(pgid: int) -> tuple[bool | None, str]:
    """Same three-way classification as `_pid_liveness`, for the whole
    process group via `os.killpg(pgid, 0)`. This is what gives the
    registry reach past the exact registered pid: every descendant a
    registered `start_new_session=True` leader forks stays in the same
    pgid unless it deliberately leaves it, so a leaked grandchild whose
    immediate parent already exited is still caught here even though only
    the leader's `(pid, pgid)` was ever recorded.
    """
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False, "no such process group"
    except PermissionError as exc:
        return None, f"permission denied ({exc})"
    except OSError as exc:
        return None, f"os error ({exc})"
    return True, "alive"


def _sweep_registry(
    registry: list[tuple[int, int, str]], harness_pgid: int
) -> tuple[list[str], list[str]]:
    """PRIMARY leak-detection path (task-049). Reaps against the spawn
    registry `subprocess.Popen` recorded a `(pid, pgid)` into at spawn
    time for every process this suite started -- not by matching argv,
    and not by invoking `/bin/ps`. Liveness is `os.kill(pid, 0)` /
    `os.killpg(pgid, 0)` only, which is argv-length-independent (AC #3)
    and unaffected by the process later exec-ing into something else
    entirely (AC #4): neither call reads the command line at all, only
    whether the kernel still has the pid/pgid.

    `pgid == harness_pgid` is the one case the pgid check is skipped for:
    a workload spawned without its own process group shares the
    harness's -- the operator's own shell / `uv` / `pytest` chain -- and
    `os.killpg(harness_pgid, 0)` would then read "alive" forever
    regardless of whether the registered pid itself is long gone. This is
    the same arm-(b) tradeoff the `run_id` fixture's own docstring already
    documents for the pgid arm below: such an entry is judged on its
    exact registered pid alone.

    Returns `(leaked, unclassifiable)`, both lists of pre-formatted detail
    lines. `leaked` entries are still alive by either check.
    `unclassifiable` entries are ones liveness could not be determined
    for -- reported, never assumed gone (AC #6).
    """
    leaked: list[str] = []
    unclassifiable: list[str] = []
    for pid, pgid, spawned_by in registry:
        pid_alive, pid_reason = _pid_liveness(pid)
        if pgid == harness_pgid:
            pgid_alive: bool | None = False
            pgid_reason = "skipped (shares harness pgid)"
        else:
            pgid_alive, pgid_reason = _pgid_liveness(pgid)
        if pid_alive or pgid_alive:
            leaked.append(
                f"  pid={pid} pgid={pgid} arm=registry "
                f"pid={'alive' if pid_alive else pid_reason} "
                f"pgid={'alive' if pgid_alive else pgid_reason} "
                f"spawned_by={spawned_by}"
            )
        elif pid_alive is None or pgid_alive is None:
            unclassifiable.append(
                f"  pid={pid} pgid={pgid} arm=registry-unclassifiable "
                f"pid={pid_reason} pgid={pgid_reason} spawned_by={spawned_by}"
            )
    return leaked, unclassifiable


#: The real `subprocess.Popen.__init__`, captured once at import time --
#: before the `run_id` fixture ever installs the recording wrapper -- so
#: the fixture always has a stable original to restore at teardown,
#: independent of how many sessions import this module (there is only
#: ever one, but this avoids ever capturing an already-wrapped version).
_REAL_POPEN_INIT: Final = subprocess.Popen.__init__


# ============================================================================
# SECONDARY (task-049, demoted): the pre-existing /bin/ps run-id-token scan.
# Unchanged below this banner (task-049's own zero-deletion `git diff` pin,
# WORKFLOW.md decision-026 rule 2). Kept as a net for a process the registry
# above never saw -- see this module's docstring.
# ============================================================================

#: The exact argv `_ps_rows` invokes -- used to exclude that call's own
#: self-referential row (see this module's docstring) from the
#: harness-child leak arm. `/bin/ps`'s `command=` field renders the
#: argv space-joined, which is exactly `" ".join(_PS_ARGV)`.
_PS_ARGV: Final = ["/bin/ps", "-Ao", "pid=,ppid=,pgid=,stat=,command="]
_PS_SELF_COMMAND: Final = " ".join(_PS_ARGV)


def _ps_rows() -> list[tuple[int, int, int, str, str]]:
    """Return (pid, ppid, pgid, stat, command) for every process visible
    right now. `ppid` and `stat` are the fields task-027 adds for the
    harness-child leak arm; `stat` is carried for the failure message's
    sake (see this module's docstring: a zombie is still a leak here, not
    excluded by state)."""
    proc = subprocess.run(_PS_ARGV, capture_output=True, text=True, check=True)
    rows: list[tuple[int, int, int, str, str]] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 4)
        if len(parts) < 5:
            continue
        pid_s, ppid_s, pgid_s, stat, command = parts
        rows.append((int(pid_s), int(ppid_s), int(pgid_s), stat, command))
    return rows


def _harness_grandchild_pids(harness_pid: int) -> set[int]:
    """Return the pids of processes exactly TWO generations below
    `harness_pid` -- a grandchild, task-035's fourth sweep arm, discharging
    doc-007 §8 A-3.

    Takes its OWN `/bin/ps` snapshot (a second, separate invocation from
    whichever call `_sweep_for_leaks` makes for its own loop -- these are
    milliseconds apart, not the same instant; see the blind spots below).
    Builds a pid -> ppid map from that snapshot and returns every pid whose
    `ppid`, looked up in the SAME snapshot, itself has `ppid == harness_pid`
    -- i.e. whose parent is a `harness-child`.

    **What this catches:** a process two generations below the harness
    process, provided its immediate parent is also present (alive, or an
    unreaped zombie) in THIS call's own snapshot -- the grandparent link can
    only be walked through a row this snapshot actually saw. This is
    precisely the gap doc-007 §8 A-3 named: M3's trampoline
    (`python -m brig.mech.trampoline … -- argv`) execs into the workload, so
    a workload launched *through* a wrapper that itself was launched as a
    harness-child lands one generation past the harness-child arm's reach.

    **What this does NOT catch (decision-050's voice, named rather than
    assumed away):**
    - a THIRD-or-deeper generation descendant (a grandchild's own child):
      this walks exactly one hop past the harness-child arm, not the whole
      subtree below it;
    - a grandchild whose intermediate parent has ALREADY exited and been
      reaped (or otherwise reparented away, e.g. to pid 1) by the moment
      this snapshot is taken -- the chain breaks in this single snapshot and
      the leaf is invisible to this arm, though it remains catchable by the
      **token** arm if it still carries the run-id token in its own argv;
    - the small race between this call's `/bin/ps` and `_sweep_for_leaks`'s
      own: a process that exits in the gap between the two invocations is
      scored against whichever snapshot happened to sample it, not against
      one frozen instant shared by both.

    Deliberately final-sweep-only, never the background poller, for the same
    reason the harness-child arm is (see this module's docstring): a
    synchronous helper `/bin/ps` call some other test makes is a genuine,
    transient descendant of this process, and a grandchild of one would
    false-positive a continuously sampling poller.
    """
    rows = _ps_rows()
    ppid_by_pid = {pid: ppid for pid, ppid, _pgid, _stat, _command in rows}
    return {
        pid for pid, ppid, _pgid, _stat, _command in rows if ppid_by_pid.get(ppid) == harness_pid
    }


def _sweep_for_leaks(run_id: str, seen_pgids: set[int], harness_pid: int) -> None:
    """Fail the run if any process matches one of three arms:

    1. **token** -- `run_id` appears directly in its own command line.
    2. **pgid** -- it shares a pgid the background poller once saw
       carrying the token (catches a same-group process with no token of
       its own in argv, e.g. a launcher's teardown that killed only the
       leader pid).
    3. **harness-child** (task-027) -- its `ppid` is this session's own
       pid and it is not this sweep's own `/bin/ps` call. Catches a leaked
       exec sibling (or any other harness-spawned process) whose argv the
       first two arms have no way to see -- see this module's docstring.

    4. **grandchild** (task-035) -- its parent is itself a `harness-child`,
       computed by `_harness_grandchild_pids`. See that function's own
       docstring for exactly what it catches and what it does not. The
       "three arms" above is text this task's own zero-deletion `git diff`
       AC pins and does not edit -- it undercounts by one on purpose, not by
       oversight.

    A survivor's message names every arm that matched it, so a mutation
    check can tell which arm actually caught a given plant.
    """
    grandchildren = _harness_grandchild_pids(harness_pid)
    labeled: list[tuple[int, int, int, str, str, list[str]]] = []
    for pid, ppid, pgid, stat, command in _ps_rows():
        arms: list[str] = []
        if run_id in command:
            arms.append("token")
        if pgid in seen_pgids:
            arms.append("pgid")
        if ppid == harness_pid and command != _PS_SELF_COMMAND:
            arms.append("harness-child")
        if pid in grandchildren:
            arms.append("grandchild")
        if arms:
            labeled.append((pid, ppid, pgid, stat, command, arms))
    if not labeled:
        return
    detail = "\n".join(
        f"  pid={pid} ppid={ppid} pgid={pgid} stat={stat} arm={'+'.join(arms)} command={command}"
        for pid, ppid, pgid, stat, command, arms in labeled
    )
    pytest.fail(
        f"leaked process(es) survived the test run (run_id={run_id}, harness_pid={harness_pid}):\n"
        f"{detail}",
        pytrace=False,
    )


def _poll_once(
    token: str,
    harness_pgid: int,
    seen_pgids: set[int],
    poll_errors: list[str],
) -> None:
    """One sampling iteration of the background leak poller.

    Split out from the `run_id` fixture's polling thread so the
    transient-failure branch below is directly callable -- with a stubbed
    `/bin/ps` failure -- without needing to time an actual outage against
    the session-scoped fixture's background thread.

    On success, records every pgid seen carrying `token` EXCEPT the
    harness's own (`harness_pgid`, this process's pgid at session start,
    e.g. the operator's shell / `uv` / `pytest` chain). That exclusion is
    load-bearing, not cosmetic -- see the `run_id` fixture's docstring for
    what it trades away.

    On failure, appends to `poll_errors` and returns instead of raising.
    An unhandled exception here would silently end polling for the rest of
    the session -- with a plain `warnings.warn` faring no better: a
    warning raised from a daemon thread is not reliably surfaced by
    pytest's item-scoped, main-thread warning capture, and under
    `filterwarnings = ["error", ...]` it would raise *inside this thread*
    and kill the poller anyway -- the exact failure mode this exists to
    prevent. `poll_errors` is a plain list read back on the main thread
    after `poller.join()`, which cannot be swallowed either way, and the
    `run_id` fixture fails the run loudly if it is ever non-empty.
    """
    try:
        rows = _ps_rows()
    except (OSError, subprocess.SubprocessError) as exc:
        poll_errors.append(repr(exc))
        return
    for _pid, _ppid, pgid, _stat, command in rows:
        if token in command and pgid != harness_pgid:
            seen_pgids.add(pgid)


@pytest.fixture(scope="session", autouse=True)
def run_id() -> Iterator[str]:
    """Mint a per-run token and sweep for leaked process groups at teardown.

    Every workload the suite launches must carry this token in its argv
    (see `workload_argv`) so a background poller and the teardown sweep
    can find the suite's own processes without any test registering them.

    A workload spawned WITHOUT `start_new_session=True` shares this
    process's own pgid rather than getting one of its own.
    `workload_argv`'s docstring states process-group isolation as a
    precondition on every caller, but nothing here can enforce it, so this
    fixture must choose between two ways to fail when that precondition is
    violated:

      (a) record the shared pgid anyway, and every long-lived process that
          happens to share it (the operator's own shell, `uv`, `pytest`
          itself) is reported as a false-positive "leak" for the rest of
          the session -- this is the failure a rejected rework of this
          fixture was caught on; or
      (b) never record the harness's own pgid (`os.getpgid(0)`, captured
          here as `harness_pgid` before anything is spawned) -- what this
          fixture does.

    (b) has a demonstrated, accepted cost, not a hidden one: if a workload
    sharing the harness's pgid is later reduced to an untagged descendant
    (e.g. a launcher's teardown kills only the leader pid, not the group),
    that descendant is indistinguishable from the harness's own processes
    and is NOT caught. A workload that keeps the token in its own command
    line is still caught directly regardless of pgid, for as long as it is
    still running -- only the *transitive*, token-less descendant case
    inside the harness's own pgid is uncovered. This is exactly why
    `workload_argv` states `start_new_session=True` as a hard precondition
    for every M2 launcher: the sweep can only tell a leak in the harness's
    own pgid apart from the harness's own processes when the workload never
    shared that pgid to begin with.

    **task-049 adds the PRIMARY registry alongside all of the above.**
    `subprocess.Popen.__init__` is wrapped for the session's lifetime so
    every process this suite spawns through the stdlib is recorded as a
    `(pid, pgid)` pair -- see this module's docstring and
    `_sweep_registry`'s for the reasoning and the exact liveness rules.
    Teardown runs the registry sweep FIRST, then this fixture's original
    /bin/ps-based sweep as the demoted SECONDARY net; a failure from either
    fails the run, with both sections named in one message.
    """
    token = uuid.uuid4().hex
    harness_pgid = os.getpgid(0)
    # `harness_pid` (task-027): captured the same way as `harness_pgid`,
    # before anything is spawned -- this session's own pid, which is
    # `ppid` on every process this suite launches directly (see this
    # module's docstring, "task-027's third arm").
    harness_pid = os.getpid()
    seen_pgids: set[int] = set()
    poll_errors: list[str] = []
    stop = threading.Event()

    # PRIMARY (task-049): the spawn registry, and the `subprocess.Popen`
    # wrapper that populates it with zero cooperation required from the
    # test that spawns the process. `registry_path` is a file under a
    # short `/tmp` scratch root (this module's traps: never `tmp_path`) so
    # a session that crashes before reaching this `finally` still leaves
    # something on disk -- a future reaper's problem, not this sweep's;
    # THIS session's own sweep below reads the in-memory `registry` list.
    #
    # `_record_spawn` runs inside `subprocess.Popen.__init__` for every
    # spawn the suite makes -- including the launcher's own workload
    # `Popen` calls, on the critical path between a caller creating a
    # process and doing anything with its pid -- so it is a single lock
    # plus a list append and nothing else. The durability file is written
    # from the POLLER thread instead (`_flush_registry`, called each poll
    # cycle and once more at teardown), never synchronously inside
    # `__init__`: a file `open`/`write`/`close` there measurably shifts
    # spawn/reap timing for every caller in the process, `handle.pid`'s
    # own launcher included, and this file exists for crash durability
    # only -- THIS session's own sweep never reads it back.
    registry: list[tuple[int, int, str]] = []
    registry_lock = threading.Lock()
    registry_path = f"/tmp/bg{harness_pid}-spawnreg"
    flushed_count = [0]

    def _record_spawn(pid: int, pgid: int) -> None:
        # task-086: the SPAWNING test is recorded alongside the pid.
        #
        # Without it this sweep can only ever name the test that happened to
        # be running when the session-scoped teardown fired -- which is the
        # LAST test in the session, and never the one that leaked. Two real
        # observations were mis-attributed that way before this line existed
        # (`test_wait_ready`, then `test_wrap_prefix`, a pure unit test that
        # spawns nothing at all), and both cost an investigation that began
        # by reading the wrong file.
        #
        # The leaked process itself cannot answer the question: it is the
        # BACKGROUNDED child of a `workload_argv` leader, so its own argv is
        # a bare `sleep 100` carrying no run-id token -- the SECONDARY arm
        # is blind to it by construction.
        #
        # `PYTEST_CURRENT_TEST` is pytest's own env var, a plain dict
        # lookup. That is deliberately within this function's documented
        # budget ("a single lock plus a list append and nothing else"):
        # no I/O, no syscall, nothing that shifts spawn/reap timing the way
        # the durability-file write above is explicitly kept out for.
        spawned_by = os.environ.get("PYTEST_CURRENT_TEST", "<no test running>")
        with registry_lock:
            registry.append((pid, pgid, spawned_by))

    def _flush_registry() -> None:
        with registry_lock:
            pending = registry[flushed_count[0] :]
            flushed_count[0] = len(registry)
        if not pending:
            return
        try:
            with open(registry_path, "a") as fh:
                for pid, pgid, spawned_by in pending:
                    fh.write(f"{pid} {pgid} {spawned_by}\n")
        except OSError:
            pass  # best-effort durability only; see the paragraph above

    def _recording_popen_init(
        popen_self: subprocess.Popen[Any], *args: object, **kwargs: object
    ) -> None:
        _REAL_POPEN_INIT(popen_self, *args, **kwargs)  # type: ignore[call-overload]
        argv = getattr(popen_self, "args", None)
        if _is_ps_probe(argv):
            return
        pid = popen_self.pid
        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = pid
        _record_spawn(pid, pgid)

    subprocess.Popen.__init__ = _recording_popen_init  # type: ignore[assignment]

    def _poll() -> None:
        while not stop.is_set():
            _poll_once(token, harness_pgid, seen_pgids, poll_errors)
            _flush_registry()
            stop.wait(_POLL_INTERVAL_S)

    poller = threading.Thread(target=_poll, name="brig-leak-poller", daemon=True)
    poller.start()
    try:
        yield token
    finally:
        stop.set()
        poller.join(timeout=2.0)
        subprocess.Popen.__init__ = _REAL_POPEN_INIT  # type: ignore[method-assign]
        _flush_registry()  # catch anything recorded since the last poll cycle

        if poll_errors:
            first = poll_errors[0]
            more = f" (+{len(poll_errors) - 1} more)" if len(poll_errors) > 1 else ""
            pytest.fail(
                f"brig-leak-poller: /bin/ps sampling failed {len(poll_errors)} "
                f"time(s) during the session, degrading pgid-membership "
                f"coverage for that window: {first}{more}",
                pytrace=False,
            )

        # PRIMARY (task-049): registry sweep -- no argv, no /bin/ps.
        with registry_lock:
            registry_snapshot = list(registry)
        leaked_lines, unclassifiable_lines = _sweep_registry(registry_snapshot, harness_pgid)
        with contextlib.suppress(OSError):
            os.remove(registry_path)

        failure_sections: list[str] = []
        if leaked_lines:
            failure_sections.append(
                "PRIMARY (registry) sweep -- pid/pgid liveness only, no argv "
                "read:\n" + "\n".join(leaked_lines)
            )
        if unclassifiable_lines:
            failure_sections.append(
                "PRIMARY (registry) sweep -- entries it could NOT classify "
                "(reported, never assumed gone):\n" + "\n".join(unclassifiable_lines)
            )

        # SECONDARY (task-049, demoted): the /bin/ps run-id-token scan.
        try:
            _sweep_for_leaks(token, seen_pgids, harness_pid)
        except pytest.fail.Exception as exc:
            failure_sections.append(f"SECONDARY (/bin/ps) sweep also failed:\n{exc}")

        if failure_sections:
            pytest.fail(
                f"run_id={token} harness_pid={harness_pid}\n\n" + "\n\n".join(failure_sections),
                pytrace=False,
            )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --sweep-aged option for session-level scratch cleanup."""
    parser.addoption(
        "--sweep-aged",
        action="store_true",
        default=False,
        help="Sweep aged scratch roots (default: False)",
    )


@pytest.fixture(scope="session", autouse=True)
def _scratch_sweep(request: pytest.FixtureRequest) -> Iterator[None]:
    """Session-scoped fixture that sweeps this run's scratch roots at teardown.

    Takes a snapshot of existing scratch roots before tests run and removes,
    after tests complete, only roots absent from that snapshot whose
    pid-bearing suffix STARTS WITH str(harness_pid) (decision-121 predicate
    2, arm a -- a prefix match, never a substring match anywhere in the
    name). With --sweep-aged, also removes roots older than 1 day regardless
    of origin.

    Pre-existing roots (present in the snapshot) are always spared, and the
    spawn registry file is spared by predicate 3 (isdir). Named rather than
    hidden: the pid-prefix match is not collision-proof -- a concurrent
    sibling session's root is still swept if that sibling's pid decimal
    string literally begins with this run's harness_pid string. That is
    decision-121's predicate as specified, not a gap this fixture papers
    over.
    """
    from tests.scratch_sweep import roots_to_sweep, snapshot_roots, sweep_roots

    harness_pid = os.getpid()
    scratch_dir = "/tmp"
    prefix = "bg"

    # Take snapshot before any tests run
    snapshot = snapshot_roots(scratch_dir, prefix=prefix)

    yield

    # Sweep after all tests
    sweep_aged = request.config.getoption("--sweep-aged")
    roots = roots_to_sweep(
        scratch_dir,
        snapshot=snapshot,
        prefix=prefix,
        harness_pid=harness_pid,
        now=time.time(),
        sweep_aged=sweep_aged,
    )

    failures = sweep_roots(roots)
    if failures:
        for line in failures:
            print(line)
