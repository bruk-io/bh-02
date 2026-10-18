---
id: TASK-0145
title: Say when the session's row log stopped writing
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:15'
updated_date: '2026-10-18 12:33'
labels:
  - app
  - size-1
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0136.11's review. When a write to <session>/rows.jsonl fails (the disk is full), the shell's listener removes itself and the run goes on (bootstrap.py _row_log), as the sub-agent event log does, but nothing tells the person, so a trajectory read later is missing its reloads with no sign why. The shell speaks once the app has exited (bh-02/CLAUDE.md, the app owns the terminal), so that is where it says it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When the row log stopped, the shell prints one line after the app exits saying it stopped, when, and the error (a test with an unwritable log)
- [ ] #2 A run whose row log never failed prints nothing new; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Test first (test_command_line.py, the shell's line): a run that writes rows.jsonl, then --resume of that session with rows.jsonl replaced by a symlink (O_NOFOLLOW refuses it, ELOOP on the first write). Assert one 'error:' line after the run, before the farewell, naming the file, the stamp and the error; a healthy run's stderr is the farewell only. Also a run-level check in test_row_log.py that report hears the line once with a row log that cannot be written. Seen failing before the fix.
2. bootstrap._row_log: remember the first failure as a frozen _RowLogStop (when the shell heard it, the OSError). The listener removes itself as now and records it; the close path (which suppressed OSError) records it if the listener did not. In the finally, after the rows have unwound, report(...) once through run()'s existing report channel, which cli._run prints after the app exits (no print in bootstrap).
3. run(): pass report to _row_log; docstrings of run, _row_log, cli module and app README say the log's stop is reported too.
4. Gates: scripts/check bh-02/app (with gates and docs), then mypy/ruff as the failing step needs.
Risk: host_paths.Appender keeps no time of its failed write (the thread), so 'when' is the time the shell found it (the next line, or exit). Stated in the line's wording and in the report; a follow-up task files the exact stamp in host_paths. Not changing host_paths here (other owners' gate and tests).
Proof: pytest on test_row_log.py and test_command_line.py; the new test seen failing before step 2.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: bh-02/app/src/bh_02/bootstrap.py (_row_log takes run()s report; the listener and the close record the first failure as _RowLogStop(at, error); after the rows unwind, one line through report, built by _stopped_line; the close no longer suppresses OSError); run() passes report and its docstring says so; cli.py module docstring and bh-02/app/README.md say the shell prints it after exit. Tests: test_row_log.py (the unwritable log now asserts the one line; a healthy log tells nobody) and test_command_line.py (a symlink at rows.jsonl, then --resume: one error line before the farewell, naming the file, a UTC stamp and ELOOP; a healthy run prints only the farewell).
Seen failing before the fix: the two unwritable-log tests fail with 0 lines reported; the healthy-log test passes both before and after.
Planted check: report on every run (or PLANTED): test_a_log_that_was_written_to_the_end_tells_nobody_anything and test_a_row_log_that_stops_is_said_once... failed; reverted, 30 passed.
Commands: uv run pytest bh-02/app/tests/test_row_log.py bh-02/app/tests/test_command_line.py -q: 28 passed before, 30 passed after; ruff check and ruff format --check on the 4 files: pass; scripts/check bh-02/app: exit 0 (first run exit 1 on two long lines, fixed), lint, mypy (9 files), tests 330 passed 1 skipped, gates (root and every lib), docs all ok.
When: the appender writes on a thread and keeps no time of its failed write, so the line gives the time the shell found it (the next line queued, or the close). Exact time filed as TASK-0147. Sub-agent event log: TASK-0148. A trajectory read later cannot show the stop (the line is on the terminal only): TASK-0149, a design question.
AC 2 is left unticked: its scripts/check part is the reviewer's; the first half (a healthy run prints nothing new) is evidenced above.
<!-- SECTION:NOTES:END -->
