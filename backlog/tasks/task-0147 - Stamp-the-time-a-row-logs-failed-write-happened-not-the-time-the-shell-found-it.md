---
id: TASK-0147
title: >-
  Stamp the time a row log's failed write happened, not the time the shell found
  it
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:33'
updated_date: '2026-10-18 20:15'
labels:
  - host-paths
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0145. host_paths.Appender keeps the first failed write's error but no time (the write runs on its thread), so the line the shell prints after exit says when the shell found the failure (the next line queued, or the close), not when the disk filled or the write failed. Record the time of the failure on the writer thread and say it through the Appender, so bootstrap._row_log can report the actual moment. Decision needed from the owner only if the Appender's API should change shape.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The Appender records when its first failed write happened, and a caller can read it (a test with a write that fails after other writes).
- [x] #2 bootstrap._row_log reports that time, not the time the shell heard of the failure; the test in test_row_log.py that asserts the line is updated to match.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order of work:
1. host_paths.Appender: a frozen dataclass Failure(at, error), at = datetime.now(UTC) taken on the writer thread in _failing, the first failure only (set together, so never half-read). Read-only property `failure` (None until a write fails). _raise raises failure.error, so raised errors are unchanged. Export Failure beside Replaced. Docstrings, host-paths README table row and CLAUDE.md layout line say it.
2. Test first (test_host_paths_appender.py): a write that fails after one that succeeded; failure is None before; the caller waits 100 ms after the thread failed, then append raises; assert before <= failure.at and failure.at + 50 ms < the caller's heard time; failure.error is the raised error; a later close does not replace it. Planted: stamp taken at the caller's time (in the failure property) -> must fail.
3. bootstrap._row_log: the listener only removes itself on OSError; after close, _stopped(appender) builds _RowLogStop from appender.failure (at, error). Wording: '(a write failed at STAMP)' in _stopped_line, docstrings updated (no 'the shell found').
4. test_row_log.py (the test that asserts the line): spy os.open on the log path to record when the failing open raised (UTC, on the thread); a trace callback that, once that failure is recorded, holds the loop 0.2 s before the next event, so the shell would hear of it 200 ms late. Assert the stamp is within 50 ms of the recorded failure time and the new wording. Planted: stamp from the shell's hear time -> must fail.
5. test_command_line.py asserts the same wording (regex): update it; app/README.md line about the stopped log.
6. Checks: uv run pytest on the changed test files while iterating; scripts/check libs/host-paths (gates and docs); scripts/check bh-02/app --no-gates --no-docs; scripts/arch-check --no-fix only if I touch anything outside a member.
Risks: the trace-based pause relies on trace running before the shell's listener for each event (it does: run() appends trace before _row_log's hear); the 50 ms window must stay well under the 200 ms pause.
Proof: planted violations for host-paths and row-log tests seen failing, then reverted and passing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: libs/host-paths/src/host_paths/appender.py (Failure(at, error), a frozen dataclass; the thread records at = datetime.now(UTC) in _failing, first failure only; read-only property Appender.failure, None until a write fails; _raise raises failure.error, so raised errors are unchanged; Failure exported from host_paths), __init__.py, README.md and CLAUDE.md. bh-02/app/src/bh_02/bootstrap.py: the listener only removes itself on OSError; _stopped(appender) builds _RowLogStop from appender.failure after the close; the line reads 'stopped being written (a write failed at STAMP)'. bh-02/app/tests/test_command_line.py (regex follows the wording), test_row_log.py, app README. No existing signature changed.
AC1 proof: libs/host-paths/tests/test_host_paths_appender.py::test_the_first_failure_says_when_its_write_failed_not_when_the_caller_heard_of_it (one write succeeds, the next fails; the caller waits 100 ms after the thread failed; asserts before <= at, at + 50 ms < heard, the same error object, and a later close does not replace it). Before the change: AttributeError (no failure). Planted: failure stamped at the caller's time -> FAILED on the at/heard assertion (both times equal to the microsecond); reverted, passes.
AC2 proof: bh-02/app/tests/test_row_log.py::test_a_log_that_cannot_be_written_ends_and_the_run_goes_on: spies os.open on the log path to record when the open failed; a trace callback holds the loop 0.2 s once that failure is recorded, so the shell would hear of it late; asserts the stamp is within 50 ms of the recorded failure. Planted: _stopped stamped with the shell's clock -> FAILED (gap 376 ms against 50 ms); reverted, passes.
Commands and results: uv run pytest libs/host-paths/tests/test_host_paths_appender.py -q: 28 passed. scripts/check libs/host-paths (gates and docs): format, lint, types, 69 passed, gates (root, every lib), docs, all ok. scripts/check bh-02/app --no-gates --no-docs: first run failed format (2) and lint (2) on lines I wrote; fixed, ruff format --check and ruff check clean, rerun: format, lint, mypy (9 files), 347 passed 1 skipped. uv run pytest bh-02/plugins/agent-cordis-plugin bh-02/plugins/subagents-cordis-plugin (the other Appender users): 322 passed 1 skipped. scripts/arch-check --no-fix: every gate ok. Not run: the full scripts/check (left to the reviewer), scripts/linux-jail-check (not asked).

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
.........s......sss.s.s...s..s.ssss.s.s.s.s.s.s.s.s.s.ssss.......s.s.... [ 49%]
........................................................................ [ 51%]
...............................................s........................ [ 53%]
.........................................sssssssssssssssssssss.sssssssss [ 54%]
ssssssssssssssssssssssss.ssssssssss..sss.........................sssssss [ 56%]
s.ss..........ss........................................................ [ 58%]
........................................................................ [ 60%]
........................................................................ [ 62%]
...............sss...................................................... [ 64%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 76%]
........................................................................ [ 78%]
.................................................s...................... [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 98%]
..............................................                           [100%]
3818 passed, 118 skipped in 207.90s (0:03:27)
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
INFO    -  Documentation built in 5.28 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
