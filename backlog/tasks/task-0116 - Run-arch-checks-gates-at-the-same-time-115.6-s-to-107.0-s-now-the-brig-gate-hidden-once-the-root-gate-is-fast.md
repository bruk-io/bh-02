---
id: TASK-0116
title: >-
  Run arch-check's gates at the same time: 115.6 s to 107.0 s now, more once the
  root gate is fast
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 08:19'
updated_date: '2026-10-16 12:19'
labels:
  - gates
  - scripts
  - size-2
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. scripts/arch-check runs its five gates (the root and libs/brig, cordis, cordis-helpers, host-paths) one after another. They share nothing: each runs pypeeker in its own directory on its own .pypeeker. Warm, the root gate is 102.7 s and the other four together 12.7 s, so running them at the same time takes the longest, not the sum.

Measured saving: a local, uncommitted edit that submits run_gate for every gate to a ThreadPoolExecutor took scripts/arch-check --no-fix from 115.6 s (three runs: 115.9, 114.1, 115.6) to 107.0 s (107.4, 106.5, 107.0), 8.7 s or 7.5%, on 4 cores with nothing else running. It is worth more once the root gate is faster: with the root gate near 44 s (see TASK-0113, TASK-0114 and TASK-0115), the other four gates' 12.7 s (brig 8.6 of them) would be a fifth of the run, and running them beside the root gate would hide all of it.

What the edit leaves to do: each gate's output must not interleave (capture each gate's output and print it whole, in gate order, as scripts/check does for its steps), a failing gate must still name itself and the exit code stay non-zero if any failed, and the --fix mode (pypeeker applies fixes as a transaction per gate) must be checked for two gates fixing at once; keep --fix as it is if it cannot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scripts/arch-check runs its gates at the same time, prints each gate's output whole in gate order, names each failed gate and exits non-zero if any failed; a test shows the gates overlap, as test_check_script does for scripts/check's steps
- [x] #2 scripts/arch-check --no-fix wall time before and after is recorded in the notes (115.6 s before, warm, 4 cores, nothing else running), and --fix still works or is kept sequential with the reason in the script
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Safety of --fix first: read pypeeker's fix path (per-gate .pypeeker/transactions, tempfile dirs, edits only inside the gate's indexed files; the five gates' src are disjoint) and prove it by running two gates' --fix at once over planted fixable violations, seeing both land, many repeats.
2. scripts/arch-check: run_gate returns an Outcome(ok, output) (all its steps stay where they are; sys.exit and click.echo inside it become values, since a SystemExit in a pool thread would end the run at the first failure and lose the other gates' output); index returns its problem as text. main runs run_gate over every gate in a ThreadPoolExecutor (pool.map, so outcomes arrive in gate order), prints each gate whole as scripts/check does (== name, output, ok or FAILED: name), exits 1 if any failed. --fix runs at once too if step 1 shows it safe, else stays sequential with the reason in the script.
3. Tests in bh-02/app/tests/test_arch_check.py: update _run and the two SystemExit tests to the Outcome; add overlap (rendezvous, as test_steps_run_at_the_same_time), whole-in-gate-order whichever ends first, failed gate named + exit 1, a gate that cannot be indexed is named and the others still report. See the overlap and ordering tests fail with a sequential main (planted) before trusting them.
4. Time scripts/arch-check --no-fix before (git stash of the script / the committed version) and after, interleaved, median of 3, machine shared. Proof: pytest on the test file, scripts/arch-check --no-fix, scripts/arch-check (fix), scripts/check bh-02/app --no-gates --no-docs. Update CLAUDE.md/docs lines that say 'root, then libs/*'.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0116 worker notes.

## What changed
- scripts/arch-check: run_gate now returns Outcome(ok, output) and writes nothing itself; its steps are where they were (sync_src, index what has no entry, optional --fix, check --strict), and the check is captured, not inherited. index returns its problem as text (None when it indexed) instead of calling sys.exit, because a SystemExit inside a pool thread would end the run at the first failing gate and lose the others' output. main runs run_gate over every gate in a ThreadPoolExecutor (outcomes(), pool.map, so results arrive in gate order) and prints each gate whole as scripts/check does for its steps: '== (root)' or '== libs/brig', the output, then 'ok' or 'FAILED: <gate>'. It exits 1 if any gate failed. The old trailing 'gate failed: X' lines are the FAILED lines now. A clean run prints five name/ok pairs where it printed nothing.
- bh-02/app/tests/test_arch_check.py: _run asserts run_gate wrote nothing to the terminal (capfd) and returns (0 or 1, output); the two SystemExit tests assert the failing outcome instead; the spy for index returns what index returns. New: a workspace fixture (root + libs/one + libs/two, real pypeeker, script ROOT moved to it) and seven tests: the gates are the root then each library that keeps one; gates run at the same time (three gates meet at a Barrier, as test_steps_run_at_the_same_time does for scripts/check); each gate prints whole in gate order whichever ends first; all-pass exits 0; a failed gate is named, the others report, exit non-zero; a gate that cannot be indexed is named, the others report; three gates each apply their --fix at once.
- CLAUDE.md: the scripts/arch-check command line says the gates run at once.

## Criterion 1 evidence
- uv run pytest bh-02/app/tests/test_arch_check.py -q: 19 passed (12 before, 7 new).
- Planted and seen failing, then the script restored (cmp against the good copy): ThreadPoolExecutor(max_workers=1) made test_gates_run_at_the_same_time (BrokenBarrierError) and test_each_gate_prints_whole_in_gate_order_whichever_ends_first fail; always sys.exit(0) made the failed-gate and cannot-be-indexed tests fail; the check run with capture=False (output to the terminal) made a run_gate test fail on the capfd assertion in _run.
- scripts/check bh-02/app --no-gates --no-docs: exit 0 (format, lint, types, 217 passed 1 skipped; tokens skipped, no bh-01/dist). uv run mypy on the test file is clean.
- scripts/arch-check --no-fix: exit 0, five gates ok (103.9 s, machine shared). scripts/arch-check (with --fix): exit 0, five gates ok, tree unchanged (258 s: --fix runs the root gate's rules twice, once for the fix and once for the check, about 100 s each; not part of this task).
- Not ticked here and left to the reviewer: nothing; the criteria do not name scripts/check.

## Criterion 2 evidence
Wall time of scripts/arch-check --no-fix, warm, paired and interleaved (before = the script at 11f8dd8 run from a scratch copy, after = this one), 3 pairs. The 4 cores were SHARED with two other workers (load average about 2 throughout), so these are noisy and not comparable with TASK-0111's 115.6 s and 107.0 s from a quiet machine: before 106.6, 109.6, 113.5 s (median 109.6); after 99.2, 100.3, 107.8 s (median 100.3). Saving 9.3 s (8.5%) at the median, the size TASK-0111 measured (8.7 s): the four small gates (12.7 s) hide behind the root gate. Exit 0 every run.
--fix with gates at once: checked, safe, so it runs at once too. pypeeker applies a gate's fix as one transaction under that gate's own .pypeeker/transactions, edits files of that gate's src, and uses uniquely named temporary directories; the gates' src are disjoint (each library has its own gate, the root's src has no libs/). Run: five scratch gates (3 members, 5 files each with 5 unused imports) through outcomes(fix=True), 25 repeats: 0 failures (every gate ok, 'import os' gone from every file, exactly one transaction per gate); the same driver with fix=False reported 5 failures, so it can fail. The precondition (no file in two gates' src) is in the script's docstring. Not tried: this checkout's root index also holds 54 stale entries for libs/brig/src (TASK-0118 drops them); whether the root gate could plan a fix to such a file was not tested.

## Not part of this task (for the report)
- --fix doubles the root gate's time (fix pass, then check pass): about 258 s against 104 s here.
- I ran chmod +x on my own scratch timing script in the scratchpad (a file I created); no repository file or directory mode was touched.

Reviewer: CLOSE. 23/23 tests in test_arch_check.py pass; scripts/arch-check --no-fix exit 0, five gates ok in gate order. Merge with TASK-0118 is correct: drop_entries(outside_src) is run_gate's first step after sync_src, docstring keeps both paragraphs. index returning its problem becomes Outcome(False), so every indexing failure still fails the run. --fix concurrency argument (per-gate .pypeeker, disjoint src) accepted with the 25-round stress. Nits, not filed: an exception (not an Outcome) raised inside run_gate propagates through pool.map and drops later gates' output, though the exit stays non-zero; --fix doubles the root gate's time (noted by worker, outside scope).
<!-- SECTION:NOTES:END -->
