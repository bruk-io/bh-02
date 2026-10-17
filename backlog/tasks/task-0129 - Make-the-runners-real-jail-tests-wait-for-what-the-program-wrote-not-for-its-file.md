---
id: TASK-0129
title: >-
  Make the runner's real-jail tests wait for what the program wrote, not for its
  file
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 23:37'
updated_date: '2026-10-17 02:35'
labels:
  - runner
  - tests
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0128's worker: three real-jail tests in bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py wait for the program's report with `said.exists()`, which is true once the program creates the file, before it writes. A read in that window gets an empty or partial report, and the test fails on a run where the jail did everything right (seen once with the same wait in TASK-0128's new test, which now waits for one line per directory). The three: test_a_linux_jail_refuses_an_input_that_writes_the_interpreter_bh_02_runs_on, test_a_linux_jail_refuses_an_input_that_changes_a_link_on_the_way_to_the_interpreter_bh_02_runs_on and test_a_host_whose_python_is_not_at_the_usual_path_starts_a_confined_session.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each of the three waits until the report is complete (the lines it expects, or a write the program makes atomically by rename), and fails with what it read when the wait runs out
- [x] #2 Each passes 10 of 10 repeated runs in a real bwrap jail
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) baseline: run the three tests once in a real jail under tini to confirm they pass here. (2) Planted race: with the pre-fix file, make each program's report slow (sleep between creating and writing the report) and see the wait read an empty report: KeyError/empty, the failure the task names. (3) Fix, test-only, in bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py: each of the three programs writes its report to a temporary name and renames it into place (os.replace), as _LISTEN_THEN_SAY_SO already does, so the report's name exists only whole; one host-side helper _report(said, started) waits for that name and returns its text, and on timeout fails with what it found (the directory's entries and what the jail ended for, started.ended()) instead of FileNotFoundError/KeyError. (4) Re-run the planted slow write against the fixed file: passes. (5) Proof: each of the three 10 times in a row in a real jail (loop in shell, under tini -s --), then -k linux_jail, then scripts/check bh-02/plugins/runner-cordis-plugin once. Risks: TASK-0128's test (one line per directory) is left as it is; the shared machine makes timings noisy, so a jail failure is re-run once alone before judging it. Changes: that one file only.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py only. The reporting programs (the interpreter and link programs, and _LISTEN_THEN_SAY_SO) now write a temporary name and os.replace it into place, so the report name exists only whole. One host-side helper _report(said, started) waits up to 10 s for the name and returns the text; on timeout its assertion lists the directory entries and the jail's ended() reason, instead of FileNotFoundError or a KeyError on an empty report. The three tests read through it and assert with the report text as the message. TASK-0128's test (one line per directory) is untouched.
Planted race, before the fix: the pre-fix file with a 1.5 s sleep between creating the report and writing it: tests one and two fail (KeyError: 'write beside', KeyError: 'beside', the empty-report KeyError the task names). Test three passes: its program already renamed into place, so only its timeout path differed.
Planted race, after the fix (sleep before the temporary's write): 3 passed. Planted missing rename: fails with 'no report at .../said after 10 s: the directory holds [... said.tmp ...]; the jail's own reason for ending the program: none'.
Proof: tini -s -- loop, each test 10 times in a row in a real bwrap jail as root: 30 of 30 exit 0, each '1 passed', none skipped. tini -s -- uv run pytest runner -k linux_jail: 13 passed, 75 deselected. tini -s -- scripts/check bh-02/plugins/runner-cordis-plugin: exit 0; format, lint, types ok; tests 87 passed, 1 skipped; gates ok; docs ok; tokens skipped (no bh-01 dist beside this checkout). Machine shared with three other workers; no timings recorded.

No repro: the race is timing-dependent on the unfixed file; the worker reproduced it only by planting a 1.5 s sleep between creating and writing the report (KeyError 'write beside' / 'beside'), which needs a code edit, so no unmodified test fails on demand.

Reviewer verdict: CLOSED. AC1 met: all three programs write said+'.tmp' in the same directory and os.replace it in (atomic), _report waits for the final name and on timeout asserts with the directory listing and started.ended(), no FileNotFoundError/KeyError (.get/.pop with default, report as message). No vacuous pass: each test asserts on report content. AC2 met: worker's 30/30 under tini, plus reviewer's 3 runs of the three in a real jail as root under tini -s --: 3 passed each, none skipped. Only test_runner_confined.py changed (plus the task file). Nit: _report's started is typed Any; no action.
<!-- SECTION:NOTES:END -->
