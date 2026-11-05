---
id: TASK-0195
title: >-
  The Working line's first tick can say 0s: Textual's timer wakes early and the
  widget floors
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T18:32:00Z'
updated_date: '2026-11-05T04:20:00Z'
labels:
  - size-1
  - tui
  - bug
  - finish-moved
dependencies: []
modified_files:
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/widgets/working.py
  - bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
test_tui_working.py::test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts failed about one run in ten. Diagnosed 2026-11-05: it failed at the first line's text, which read 'Working · 0s', not at the 0.4 s absence check. Textual's timer wakes half a millisecond before each interval (textual/_time.py sleep: 'reduce the sleep to compensate'), so the first tick after a reply began reads 0.9995 s, and Working._tick passed that to render.working_line, which floors: 0s, and every later tick could say a second behind. A real display defect, not a slow test. Separately, the test's 0.4 s absence check is evidence only if the pause ended within the first second; on a loaded machine it can run past.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A tick that comes a hair before a whole second says that second (a driven-clock test at 0.9995 s says 1s), seen failing before the fix
- [x] #2 The real-clock test's absence check holds only when its pause ended within the first second
- [x] #3 The real-clock test passes 20 of 20 in a row, where it failed 1 of 10 before
- [x] #4 scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work

1. Repro: test_a_tick_that_comes_a_hair_early_says_the_second_it_is_for in bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py (driven clock: began, then +0.9995 s must read 1s, +1 s more 2s). Seen failing before the fix.
2. widgets/working.py _tick: round the elapsed time to the nearest second before render.working_line. render's floor stays (59.9 s reads 59s, its tests pin that); the tick is what is a hair early, so the widget corrects it.
3. The real-clock test asserts absence after its 0.4 s pause only if the pause really ended within WORKING_EVERY.

### Risks

A driven test that moves the clock by a fraction would now round where it floored; every driven clock in the tui tests moves by whole seconds (checked).

### Proof

The repro failing before and passing after; the real-clock test 20 of 20; scripts/check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro before the fix: test_a_tick_that_comes_a_hair_early_says_the_second_it_is_for failed (the line never read 1s). The real-clock test before: 1 failed of 10 runs, the failure 'Working · 0s' at the first line's text. After the fix: the repro passes, the real-clock test 20 of 20 (uv run pytest -q -p no:randomly on that test id, 20 runs in a row), test_tui_working.py and test_tui_command_working.py 38 passed.

Check `scripts/check` exited 0

(13 earlier lines omitted)
```text

........................................................................ [  2%]
........................................................................ [  5%]
...............s........................................................ [  7%]
..................................x..................................... [ 10%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 18%]
....s................................................................... [ 20%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 28%]
........................................................................ [ 30%]
........................................................................ [ 33%]
..ss.................................................................... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 87%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
............................................................             [100%]
2791 passed, 6 skipped, 1 xfailed in 139.99s (0:02:19)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
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
INFO    -  Documentation built in 4.49 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Check `scripts/check` exited 0

(13 earlier lines omitted)
```text

........................................................................ [  2%]
........................................................................ [  5%]
...............s........................................................ [  7%]
................................x....................................... [ 10%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 18%]
.........s.............................................................. [ 20%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 28%]
........................................................................ [ 30%]
........................................................................ [ 33%]
..............ss........................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 87%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
............................................................             [100%]
2791 passed, 6 skipped, 1 xfailed in 176.99s (0:02:56)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
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
INFO    -  Documentation built in 11.14 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (reviewer): the change is sound and all four criteria are met and ticked (diagnosis confirmed in textual/_time.py sleep and timer.py _run; rounding in Working._tick is the right place, render's floor stays; the conditional absence check is conservative; real-clock test 10/10 here; full check exit 0, no files changed). close-task refused on process only: (1) the bug has no recorded repro: record-check TASK-0195 --repro -- the hair-early test, or a 'No repro:' note; (2) the criteria changed since acceptance in 2140d73 without the finish-moved label and a note saying why. Status left In Progress.

finish-moved: the criteria were rewritten after promotion (2140d73) once the cause was found. The draft guessed the line was drawn before 0.4 s. The failure was the first line reading 'Working · 0s' (Textual's timer wakes 0.5 ms early and the widget floored), so the criteria now name that defect and its fix.

No repro: the repro test (test_a_tick_that_comes_a_hair_early_says_the_second_it_is_for) and the fix landed in one commit, 7e67f6c, so no commit holds the test without the fix for record-check --repro to run. Its failure before the fix was seen and is in the notes above ('what the test waited for never happened': the line never read 1s), as is the real-clock test's failure before the fix (1 of 10, the first line 'Working · 0s'). Lesson kept: commit the repro before the fix.
<!-- SECTION:NOTES:END -->
