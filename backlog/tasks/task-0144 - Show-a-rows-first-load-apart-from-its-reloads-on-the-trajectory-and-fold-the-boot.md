---
id: TASK-0144
title: >-
  Show a row's first load apart from its reloads on the trajectory, and fold the
  boot
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:15'
updated_date: '2026-10-18 14:38'
labels:
  - app
  - size-3
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0136.11 and its real run (2026-10-18). cordis has no first-load or restart event, so rows.jsonl records a row's first load as a reload: bh-02 trajectory opens with about 34 boot lines, and each sub-agent's start adds about 15, which bury the reloads that matter (a /model switch, a /clear). The reader can tell them apart: a row id not seen before in the session is its first load.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bh-02 trajectory labels a row's first load in the session apart from a reload of a row seen before (a restart, a dependency replaced, a layer edit), from rows.jsonl as it is written today
- [x] #2 The first loads at the session's start are one line (how many rows, the time from the first to the last), and a sub-agent's first loads are one line under it; reloads and failures still print one line each in time order (tests)
- [x] #3 GLOSSARY.md and the docs page for bh-02 trajectory say what each line means; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) trajectory.py: _Reload gains first (a reload of a row id not yet seen in the time-sorted rows: set in _reloads, so trajectory() stays pure); _with_reloads batches the records popped for each line (and each owner's trailing rest), and a run of consecutive first loads in a batch becomes one line (one row: 'row first load NAME'; many: 'row first load  TIME  N rows in S'), keyed by its first record so a follower prints it once; reloads and failures stay one line each. Live view holds back a trailing first-load run (it may still be growing). So the session's boot (before its first reply) is one line and a sub-agent's first loads one line under its 'sub-agent' line. (2) tests in test_trajectory.py: first flag from rows as written today (a real boot sequence, a /clear restart), the boot fold, a sub-agent fold, reloads and failures between runs, a late first load, live hold-back, stable keys; update existing tests whose same-row reloads now include a first load. Plant: make first always False and see the fold tests fail. (3) docs: GLOSSARY (first load, rows.jsonl, bh-02 trajectory), docs/bh-02/reference/command-line.md (sample + bullet), docs/bh-02/using/sessions.md, app/README.md, decision-0009 'What it prints' stays (a row reload line). (4) Proof: pytest the trajectory tests, scripts/check bh-02/app, scripts/arch-check --no-fix not needed unless outside a member (docs only inside bh-02/ and docs/). Risk: --resume appends to the same rows.jsonl so a resumed boot reads as reloads (file a follow-up task, no marker written here).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
What changed: bh_02/trajectory.py: _reloads marks each reload of a row id not yet in the (time-sorted) records as first (a failed row has been named, so its next reload is not; a failed is never first); trajectory() stays pure (frozen data from bytes). _with_reloads batches the records placed before each line of their writer (and each writer's trailing rest) and _grouped makes one item of each run of consecutive first loads: 'row first load  TIME  N rows in S' (one row: 'row first load NAME'), keyed by the run's first record so a follower prints it once; reloads and failures are one line each as before. So the session's boot (before its first reply) is one line and a sub-agent's rows (agents/NAME, agents/NAME/...) one line under its sub-agent line; the session's own reload during a child's boot does not cut the child's run (per writer). In the live view a trailing run of first loads is held back (_unclosed) so it is printed once with its final count. Rows that come up after the first reply are a line of their own (counted if several). Docs: GLOSSARY.md (new 'first load' entry, rows.jsonl, bh-02 trajectory), docs/bh-02/reference/command-line.md (sample and the three row-line kinds), docs/bh-02/using/sessions.md, bh-02/app/README.md.

Evidence: tests in test_trajectory.py (first flag by time, failed never first, named-by-failing; boot fold with count and span; reload/failure between runs; sub-agent fold under its line and not cut by the session's reload; a late row its own line; no conversation; live hold-back; key stable as rows come up; control characters), test_trajectory_view.py (a sub-agent's rows coming up while following printed once with all 3), test_row_log.py (the rows.jsonl the real shell writes on a boot and a /clear: one first-load line with the exact count of distinct rows, then one row reload line per restarted row). Existing tests with fresh row ids were updated to the new labels. Planted violations seen failing: first forced False -> 16 tests failed (the new fold tests and the 8 updated ones); hold-back removed -> the live test and the follow test failed (the follow one would print the sub-agent's line with 2 rows, never updated). scripts/check bh-02/app: first run lint found 3 over-long lines (fixed), types, 347 tests, gates (all five) and docs ok; rerun --no-gates --no-docs exit 0; scripts/arch-check --no-fix exit 0.

Limit found: --resume goes on in the same rows.jsonl, so a resumed run's boot reads as reloads (every row seen before); documented in command-line.md; filed as TASK-0155 (a marker line when the log is opened), not started. decision-0009's 'each row reload' is left as written. AC #3 left unticked: 'scripts/check passes' is the reviewer's to prove (member check and docs build passed).

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
...............s.s....sss.s.s.s...sss...ss.s.s.s.s.s.ss.s.s..sss......s. [ 49%]
.s...................................................................... [ 51%]
.............................................s.......................... [ 53%]
................................................ssssssssssssssssssssssss [ 54%]
sssssssssssssssssssssssssssssssssssssssssss............................. [ 56%]
.sssssssss..........s.....ss............................................ [ 58%]
........................................................................ [ 60%]
........................................................................ [ 62%]
......................sss............................................... [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................s............... [ 71%]
........................................................................ [ 73%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 96%]
........................................................................ [ 98%]
...................................................                      [100%]
3823 passed, 118 skipped in 201.74s (0:03:21)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 3.80 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
