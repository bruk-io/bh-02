---
id: TASK-0145
title: Say when the session's row log stopped writing
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 12:15'
updated_date: '2026-10-18 12:46'
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
- [x] #2 A run whose row log never failed prints nothing new; scripts/check passes
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

Check `scripts/check` exited 0

(30 earlier lines omitted)
```text
........................................................................ [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
.........................................ss...ssss.s.s.s.s..sss...ss..ss [ 48%]
.s.s..ss.s.s.ssss...s................................................... [ 50%]
........................................................................ [ 51%]
........................................................................ [ 53%]
sssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss..... [ 55%]
........................sssssssssss.....s............................... [ 57%]
........................................................................ [ 59%]
........................................................................ [ 61%]
..............................................sss....................... [ 63%]
...........................s............................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
..................................................................       [100%]
3766 passed, 118 skipped in 195.59s (0:03:15)
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
INFO    -  Documentation built in 3.48 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review: not closed. Both ACs met (full scripts/check exit 0, 3766 passed; AC2 ticked). close-task refuses: a bug needs its repro recorded (record-check TASK-0145 --repro -- <test>) from before the fix, or a 'No repro:' note. The worker reports the tests failing before the fix but did not record it; the reviewer cannot record a pre-fix failure honestly on the fixed tree.

Review round 1 (blocking finding 1): the bug's repro is not on record, and close-task refuses a bug without one. No code change. Plan: (1) a detached git worktree at the pre-fix commit 973a789 in the scratchpad; (2) the two tests as they stand in ecd3c5e (test_row_log.py, test_command_line.py) copied onto it and committed there, so record-check can name the commit; (3) run each test there and see it fail, then record each with record-check --repro against this board (--root); (4) run the same two tests on the fixed tree (ebd3c1c) to show they pass; (5) remove the worktree; (6) squash to one commit. Risk: the worktree's bh_02 import must be the worktree's source, not the editable install of this checkout: checked with bh_02.__file__ before the recorded run.

Repro at cb1d74514469, test files: bh-02/app/tests/test_row_log.py; command: `uv run pytest bh-02/app/tests/test_row_log.py::test_a_log_that_cannot_be_written_ends_and_the_run_goes_on -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
__________ test_a_log_that_cannot_be_written_ends_and_the_run_goes_on __________

composition = <function composition.<locals>.layer at 0x7f2b263517a0>
tmp_path = PosixPath('/tmp/pytest-of-root/pytest-2388/test_a_log_that_cannot_be_writ0')

    async def test_a_log_that_cannot_be_written_ends_and_the_run_goes_on(
        composition: Callable[..., Path], tmp_path: Path
    ) -> None:
        """The log is for the person, not the run: its directory is gone (a session being removed), the first
        write fails on its thread, and the listener stops without taking down the row that was emitting. The
        person is told once, after the rows have unwound, through `report`: the file, when the shell found the
        write failing, and the error."""
        log = tmp_path / "gone" / "rows.jsonl"
        told: list[str] = []
        await asyncio.wait_for(run([*layers(), patch(composition)], [CHAT], report=told.append, row_log=log), 10)
        assert not log.exists()
>       (line,) = told
        ^^^^^^^
E       ValueError: not enough values to unpack (expected 1, got 0)

bh-02/app/tests/test_row_log.py:153: ValueError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_row_log.py::test_a_log_that_cannot_be_written_ends_and_the_run_goes_on
1 failed in 2.80s
```

Repro at cb1d74514469, test files: bh-02/app/tests/test_command_line.py; command: `uv run pytest bh-02/app/tests/test_command_line.py::test_a_row_log_that_stops_is_said_once_after_the_app_exits_and_a_healthy_one_is_not -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
_ test_a_row_log_that_stops_is_said_once_after_the_app_exits_and_a_healthy_one_is_not _

composition = <function composition.<locals>.layer at 0x7f2effe25fe0>
state = PosixPath('/tmp/pytest-of-root/pytest-2389/test_a_row_log_that_stops_is_s0')

    def test_a_row_log_that_stops_is_said_once_after_the_app_exits_and_a_healthy_one_is_not(
        composition: Callable[..., Path], state: Path
    ) -> None:
        """A row log that can't be written ends the log and not the run, and the shell says so once, after
        the app has exited: the file, when the shell found the write failing, and the error. Here a link
        stands at the log's name (the appender never follows one), so the first write fails with ELOOP."""
        patch = _patch(composition)
        healthy = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
        assert healthy.exit_code == 0, healthy.output
        assert len(healthy.stderr.splitlines()) == 1  # the farewell, and nothing about the log
        (session,) = (state / "state" / "bh-02" / "sessions").iterdir()
        log = session / "rows.jsonl"
        log.unlink()
        log.symlink_to(state / "elsewhere.jsonl")
        resumed = CliRunner().invoke(main, ["--resume", "--patch", str(patch)])
        assert resumed.exit_code == 0, resumed.output
        *before, farewell = resumed.stderr.splitlines()
        assert farewell.startswith("session ")  # said last, after the line about the log
>       (told,) = before
        ^^^^^^^
E       ValueError: not enough values to unpack (expected 1, got 0)

/tmp/claude-0/-home-user/a0d5191d-f6a5-53e2-ae9a-0fb260cd6c48/scratchpad/prefix-973a789/bh-02/app/tests/test_command_line.py:93: ValueError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_command_line.py::test_a_row_log_that_stops_is_said_once_after_the_app_exits_and_a_healthy_one_is_not
1 failed in 2.48s
```

Review round 1, blocking finding 1 (the repro is not on record): fixed by recording it, no code change. A detached worktree at the pre-fix commit 973a789 (in the scratchpad, removed afterwards) got the two tests as they stand in ecd3c5e, committed there as cb1d745 (tree = 973a789 plus those two test files; no source change). bh_02 imported from that worktree (checked). Seen failing on the pre-fix tree: test_row_log.py::test_a_log_that_cannot_be_written_ends_and_the_run_goes_on fails (ValueError: not enough values to unpack (expected 1, got 0): nothing reported); test_command_line.py::test_a_row_log_that_stops_is_said_once_after_the_app_exits_and_a_healthy_one_is_not fails at (told,) = before (0 lines). Both recorded: record-check TASK-0145 --repro --root /home/user/bh-02 -- uv run pytest <test> -q, each exit 0 ('recorded on TASK-0145'). Passing on the fixed tree (ebd3c1c): the same two tests, 2 passed. Test files unchanged since cb1d745 (git diff --quiet). board-check close TASK-0145 (read-only): 'ok: TASK-0145 can close'. Not closed: that is the reviewer's. Note: cb1d745 is not on the branch; it is kept by git's object store (gc does not prune it for two weeks), and close-task reads it by its sha. No criterion ticked; scripts/check not run (no code changed).

Check `scripts/check` exited 0

(30 earlier lines omitted)
```text
........................................................................ [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
..........................................ss...ss.s.ss.ss..s.s.s.s..s.s. [ 48%]
s.s.s..ssss..ssss.s..........s.......................................... [ 50%]
........................................................................ [ 51%]
.......................................................................s [ 53%]
ssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss...... [ 55%]
.......................ssssssssssss..................................... [ 57%]
........................................................s............... [ 59%]
........................................................................ [ 61%]
................................................sss..................... [ 63%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
..................................................................       [100%]
3766 passed, 118 skipped in 195.66s (0:03:15)
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
INFO    -  Documentation built in 4.43 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review round 2: closed. Full scripts/check exit 0 (recorded). Both ACs met: the unwritable-log tests in test_row_log.py and test_command_line.py assert one line after exit with file, stamp and error; healthy runs print only the farewell. Repro recorded at cb1d745 failing pre-fix. Nits only: 'when' is when the shell found the failure (TASK-0147 tracks the exact time); the line is terminal-only (TASK-0149). No new drafts.
<!-- SECTION:NOTES:END -->
