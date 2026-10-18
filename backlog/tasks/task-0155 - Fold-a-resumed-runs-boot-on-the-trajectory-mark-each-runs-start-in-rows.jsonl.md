---
id: TASK-0155
title: >-
  Fold a resumed run's boot on the trajectory: mark each run's start in
  rows.jsonl
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 14:31'
updated_date: '2026-10-18 22:07'
labels:
  - app
  - size-2
  - finish-moved
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0144. bh-02 trajectory tells a row's first load by its row id not being in rows.jsonl before. A session resumed with --resume goes on in the same rows.jsonl (the appender appends), so the resumed run's whole boot (about 34 rows, and a sub-agent's again) reads as reloads of rows seen before and prints a line each, burying what matters, as the boot did before TASK-0144. cordis has no event for a run's start, and the file cannot tell a mass dependency replacement (a /model switch) from a boot, so the shell would have to write a marker line when it opens the log (for example kind run at the time), which the trajectory reads: the rows after it that are already seen are that run's loads, folded the same way. Changes what rows.jsonl is written as, so a decision-0009 amendment, the GLOSSARY entries and the command-line docs follow.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A resumed session's boot is one line on bh-02 trajectory, apart from a reload of a running session's row (a restart, a dependency replaced)
- [x] #2 GLOSSARY.md and the docs page for bh-02 trajectory say what the marker and the line mean; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. bootstrap._row_log: when it opens the log, queue one marker line {at, kind: run} through the Appender before the listener goes on (pure _run_line(at) beside _row_line). 2. trajectory._reloads: a run record needs only at+kind; it ends the run before it: the rows after it that are already seen are that run's first loads (seen set cleared), and a new Reload.run index keeps two runs' boots apart when nothing sits between them (_grouped groups first loads by run). The marker prints no line of its own; the run's boot is the folded 'row first load ... N rows in S' line. 3. Tests: pure trajectory tests (resumed boot folds to one line, restart after it is a reload, two boots with nothing between stay two lines, a run record is not a reload and a bad one is skipped); test_row_log: marker is first line, and two runs into one rows.jsonl give two boot lines (planted: with the marker not written the second boot is N reload lines, seen failing); update the tests that assumed every line has a row. 4. Docs: decision-0009 Row reloads + Amended (TASK-0155), GLOSSARY (rows.jsonl, lifecycle event, first load, bh-02 trajectory, session), docs command-line.md and sessions.md, CONTRACTS.md output row, app/README.md, sessions.py docstring. 5. Proof: uv run pytest on the app tests, scripts/check bh-02/app, scripts/arch-check --no-fix (docs/pyproject touched outside a member). Risks: a marker with no row must not break the reader's 'at, kind, row required' rule; the log-stopped tests now fail on the marker write rather than the first reload, check they still hold.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's rule, 2026-10-18 (root CLAUDE.md, Conventions: no backwards compatibility before a supported release): criterion #2, 'a rows.jsonl written before the marker reads as it does now', pinned an old form and is removed. A rows.jsonl written before the marker is not read specially; say in the notes how it now reads.

What changed. bootstrap._row_log queues one marker line {at, kind: "run"} (pure _run_line) through the Appender when it opens the log, before the listener goes on and before any row's line; it names no row. trajectory._reloads treats the file's start and each run line as the start of a run: a reload is 'first' when its row id was not seen since then (the seen set is cleared at a run line), the run line is not one of Trajectory.reloads, and _Reload gains run (how many run lines came before it) so _grouped never merges two runs' boots that have no printed line between them. The marker prints no line of its own: a resumed run's boot is the same folded 'row first load  TIME  N rows in S' line as the session's first, a sub-agent's rows under its sub-agent line likewise, and a restart or a replaced dependency after the boot is still 'row reload NAME' a line each. Docs: decision-0009 (Row reloads text, and an Amended paragraph for TASK-0155), GLOSSARY.md (lifecycle event, rows.jsonl, run, first load, bh-02 trajectory), docs/bh-02/reference/command-line.md and using/sessions.md, CONTRACTS.md (output), app/README.md, sessions.py docstring.

Evidence, criterion 1. New pure tests in test_trajectory.py (a resumed run's boot is one line and a restart after it a reload; two boots with nothing between them are two lines; sub-agent and failed rows are first loads again in a new run; a run line is no reload and one with a bad time starts nothing). test_row_log.py: the marker is the first line (rows_of asserts {at, kind: run}), and a second run() into the same rows.jsonl gives two markers and a trajectory of exactly two 'row first load' lines, no reload. test_command_line.py: main then main --resume, then main trajectory prints two 'row first load' lines and no 'row reload'. Planted violations seen failing, then restored: (1) seen not cleared at a run line: 5 tests failed (the resumed-boot, two-boots, sub-agent/failed and run-line tests in test_trajectory.py, and the two-run test in test_row_log.py); (2) _grouped keyed by first alone: the two-boots test and the two-run test failed; (3) the shell writing no marker: 6 test_row_log.py tests failed, and the CLI resume test failed on the count of run lines (0 != 2). uv run pytest on the app: 369 passed, 1 skipped (inside scripts/check bh-02/app).

Criterion 2 is left unticked: GLOSSARY.md and the command-line and sessions docs now say what the marker and the line mean, scripts/check bh-02/app passed (exit 0: format, lint, types, 369 tests, all gates including the root and libs gates, docs build; tokens skipped, no bh-01 dist), but 'scripts/check passes' for the whole workspace is the reviewer's to prove.

How a rows.jsonl written before the marker now reads (owner's rule, 2026-10-18: no old-form reading, no test pinning it). Nothing reads it specially, and no test or doc pins it. It has no run line, so the reader takes the whole file as one run: its first boot is one 'row first load' line, and if the session was resumed in it, that resumed run's rows (all seen before) print a 'row reload NAME' line each, as they did before this task. A new run of such a session appends its own run line, and from there the file reads right. I checked this once while writing the tests (the test passed), then removed it so the old form is not pinned. No other file stops working.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 46%]
......................................................sss...ssss.s.s..ss [ 48%]
.s.s...s....ss.s.ss.ss..ss..sss.s..........s............................ [ 50%]
........................................................................ [ 52%]
........................................................................ [ 54%]
..............sssssssssssss.ssssssssssssssssssssssssssssssssssssssssssss [ 55%]
ssssssssss............................sssssssssss......s................ [ 57%]
................................................s....................... [ 59%]
........................................................................ [ 61%]
............................................................sss......... [ 63%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
..............................                                           [100%]
3874 passed, 118 skipped in 203.16s (0:03:23)
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
INFO    -  Documentation built in 4.54 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
