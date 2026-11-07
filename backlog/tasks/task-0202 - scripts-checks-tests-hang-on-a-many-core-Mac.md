---
id: TASK-0202
title: scripts/check's tests hang on a many-core Mac
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-07 04:27'
updated_date: '2026-11-07 04:54'
labels:
  - scripts
  - tests
  - darwin
  - size-2
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On a 28-core Mac (macOS 27.0.1, 2026-11-06) scripts/check's test step (pytest -n auto --dist loadgroup, so 28 workers) stalls: one worker goes silent around 4% and the 377 tests queued behind it never run; the run sat at 0% CPU for 28 minutes. With -n 8 the same suite finishes in 84 s. Three test_booting.py tests failed under -n auto and pass alone in 6 s. Earlier notes (TASK-0169.01, TASK-0170) blamed stray runs holding the jail lock; nothing held /tmp/bh-02-jails-501.lock during this hang. Until fixed, no 'scripts/check passes' criterion can be proven on this machine.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The hang is explained (which test or fixture, and why many workers trigger it)
- [x] #2 scripts/check completes on a 28-core Mac every time (three runs in a row), whatever the core count, and the worker count it uses is said where TEST_WORKERS is set
- [x] #3 Tests that fail only under load are fixed or filed, not retried away
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Cause (found by probe, single worker): under -n auto a test_booting.py run() hits its 2 s wait_for mid-boot; run() is cancelled inside boot(), before its try/finally, so the runtime is never shut down and ~26 row tasks stay on the loop; pytest-asyncio's Runner.close then cancels every task at once and a fiber whose _live task was cancelled before it first ran never resolves its inertia, so a parent's undo (retire -> settled) awaits it forever: teardown blocks at 0% CPU, the xdist worker goes silent and the work queued on it is stranded. 2. Fix bh_02.run: whatever ends boot, the runtime is shut down (boot inside the try). Regression test in test_booting.py: a run cancelled mid-boot leaves no task of its runtime pending; seen failing before the fix. 3. File the cordis mechanism (a _live task cancelled before it starts leaves inertia unresolved) as its own task. 4. scripts/check: TEST_WORKERS capped at min(8, cpu count), comment says why; adjust test_check_script if needed. 5. File the 2 s boot deadlines in test_booting.py as load-only failures. 6. Three testlock scripts/check runs; diff failures against filed tasks, file leftovers. Risk: shutdown inside a cancelled run adds up to 1 s (grace) to a cancelled run.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-06: Approved as the run's first task (Opus worker): nothing else can prove 'scripts/check passes' on this Mac until it is fixed. Fix the cause; a lower worker count is fine only if AC #1 explains the hang and AC #3's load-only failures are fixed or filed, not retried away.

Cause (AC #1). The captured -n auto log (pytest -v, 28 workers) shows gw24 report two results and go silent at 2%: its last was FAILED test_booting.py::test_an_unrelated_providers_background_work_does_not_keep_an_interactive_session_open (its 2 s wait_for timed out: 28 workers booting the shipped stack at once), and the one test never started was the next one handed to it; every other worker finished and the session never ended. Reproduced on one worker with no load: wait_for(run([*layers(), patch]), 0.02) on that test's patch hung in teardown, faulthandler (30 s) showing asyncio/runners.py _cancel_all_tasks under pytest-asyncio's _scoped_runner. A task dump after the timeout: run() had been cancelled inside boot(), before its try/finally, so the runtime was never shut down and 26 row tasks were left on the loop (cancelling=0). The loop's close then cancels them all at once; after that one task stays for ever, a parent's undo in Fiber.retire -> settled -> shield(inertia) (cordis runtime.py:119/99) whose child task ended without resolving its inertia (a task cancelled before its first step never enters _live's except). 0% CPU, worker silent, its queue stranded. Why many workers: only a deadline missed mid-boot cancels run() there, and only load makes the boot miss 2 s.

Fix: bh_02.run shuts the runtime down however the run ends, boot included (bootstrap.py). New test test_booting.py::test_a_run_cancelled_while_its_rows_start_leaves_no_row_running cancels run() at its first row's reload and asserts no task is left: with the fix reverted (git stash) it failed ('Left contains 35 more items', _live tasks); with it, test_booting.py 19 passed. The 0.02..1.0 s probe that hung before ran 10 cases in 2.75 s with the fix. The cordis half (a pre-start cancel leaving inertia unresolved) is filed as TASK-0203.

AC #2. scripts/check: TEST_WORKERS = str(min(8, os.cpu_count() or 1)), the comment says why (TASK-0202, 28 vs 8). New test test_check_script.py::test_the_tests_run_on_eight_workers_at_most_whatever_the_core_count: failed with TEST_WORKERS planted back to 'auto', passes with the cap (9 passed). Three 'testlock scripts/check' in a row: exit 1 each in 74 s, 72 s, 73 s; every step reported (format, lint, types, gates, docs, tokens ok; tests 15 failed/3795 passed/25 errors, then 16/3794/25 twice). Exit 1 is the filed failures, not a hang.

AC #3, failures under load or not filed before: the three 2 s boot deadlines in test_booting.py (fail at 28 workers, pass at 8: the cap hides them) -> TASK-0204; brig's run_id teardown running a missing /usr/bin/docker, an ERROR on whichever test ends each worker (8 a run, the 'flaky' warden/host-paths/brig ERRORs) -> TASK-0205; test_tui_working real-clock and test_channel_planted_link listener test, each failing in one run of three -> TASK-0206. The rest are filed: TASK-0197 (session from home), TASK-0198 (supervisor_link SEQPACKET, SIGRTMIN, exit_status, teardown_zombies), TASK-0199 (interpreter-deny chflags), TASK-0200 (six sub-agent wiring), TASK-0201 (trajectory name), TASK-0169.04 (keyed model key), TASK-0169.05 (xdist groups). Not verified: a run at 28 workers (this run's rules cap pytest at -n 8).

Correction to the AC #1 note: the captured pytest-v.log is not the 28-minute run the description reports. It is a later -n auto run that reached ~99% and was stopped at session finish (OSError: cannot send (already closed?)): gw24 went silent at 2% right after its timed-out booting test, and exactly one collected test never started (the log does not show which worker it was queued on, so it is not attributed to gw24 here). The description's run stranded 377 tests behind its silent worker. Same mechanism, two runs; how much work is stranded depends on how much the silent worker had queued when its test missed the deadline.
<!-- SECTION:NOTES:END -->
