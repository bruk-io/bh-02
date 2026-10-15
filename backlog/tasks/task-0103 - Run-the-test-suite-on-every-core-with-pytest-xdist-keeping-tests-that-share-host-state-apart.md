---
id: TASK-0103
title: >-
  Run the test suite on every core with pytest-xdist, keeping tests that share
  host state apart
status: Done
assignee: []
created_date: '2026-10-15 02:28'
updated_date: '2026-10-15 18:35'
labels:
  - tests
  - size-3
  - finish-moved
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-15), after the measurement in the scripts/check task: the suite is 2756 tests, 433 s, one at a time (no xdist installed). Some tests share state on the host and must not run beside each other: the jail lock (/tmp/bh-02-jails-{uid}.lock; TASK-0085 and TASK-0091 gave some tests a lock of their own), the real-launch tests (pseudo-terminals, an installed script), brig's real jails (bubblewrap), hypothesis's database. A time-boxed change: find what shares state, group it (xdist_group with --dist loadgroup, or a marker run serially), and keep the suite as reliable as it is now. If it cannot be made reliable within its size, stop and report what shares what, and leave the suite serial.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 uv run pytest -n auto runs the whole suite green five times in a row, with the groups that share host state named in conftest and their reason beside each
- [x] #2 scripts/check uses it, and its wall time before and after is recorded; or the notes say why it stays serial and what would have to change first
- [x] #3 scripts/check passes
- [x] #4 scripts/arch-check writes the root pyproject.toml's src list atomically (a temp file then os.replace), since it now runs while pytest, ruff and mypy read that file at startup (from TASK-0102's close review)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-0102's close review (2026-10-15):
- Should-fix, now AC #4: scripts/arch-check's sync_src writes pyproject.toml with write_text (truncate, then write) while scripts/check starts pytest, ruff and mypy beside it, and all three read that file at startup. It writes only when the src list changes (a new member), so the window is small but real.
- Nit, not a criterion: scripts/check captures each step's output, so a long test run shows nothing until it ends. If xdist changes how the tests report, keep that in mind; no change is asked for.

Stopped by the owner (2026-10-15) before its end: the runs cost too much. What it built is committed as it stood, checked by the orchestrator, not reviewed:
- pytest-xdist in the root dev group (uv.lock by uv); scripts/check runs the tests with `-n auto --dist loadgroup`; `-n` is not in addopts, so a bare pytest stays serial.
- One group, `jail-lock`, in the root conftest.py with its reason (one lock file per user; a jail started by one worker keeps the placeholders of a jail another stops): test_python_repl, test_runner_confined, test_runner_tmux, test_agents_wiring. bh-02/app/tests/test_xdist_groups.py fails if a group names a missing file or a test file that starts a jail is in no group.
- Two tests fixed that load exposed: the zombie-planting bodies in test_runner_confined.py and brig's test_kill_group.py now keep their Popen (a dropped one reaps its exited child in __del__, so no zombie was planted); a real-launch assertion reads words, since xdist's longer tmp_path moved a line break.
- AC #4: scripts/arch-check writes pyproject.toml through a temporary file and os.replace, only when the list changes (replace_file; tests in test_arch_check.py).
Evidence: the worker's log shows its last four full runs under -n auto green (2778 passed, 31 skipped; 2m08s to 2m49s, against about 8 min serial), after a run with 3 failures its last fixes addressed. The orchestrator then ran ruff format and lint, mypy, scripts/arch-check --no-fix (all exit 0) and the touched tests under xdist (22 passed). Not done: a fifth green run, scripts/check's before/after recorded by step, a reviewer. AC #4 is ticked on the code and its tests; #1 to #3 stay open for whoever picks this up.

Close evidence (2026-10-15):
- AC #2, whole check before and after: scripts/check with serial tests, 478 s wall (TASK-0102's recorded after; tests 487 s, the step that sets the wall time); with -n auto --dist loadgroup, 155 s wall (tests 153.81 s, 2796 passed, 31 skipped) on head 96492f9, exit 0. The test step went from about 8 min to about 2.5 min.
- AC #1: the worker's last four full runs under -n auto (2778 passed) and the batch's full check on 96492f9 are five green runs in a row; the fifth is on a later head with TASK-0100 and TASK-0099.05 on top of this commit, not on 894daf6 itself. Neither deferred flake (TASK-0086.01, TASK-0097) failed in it.

Finish moved (2026-10-15): AC #4 (the atomic write of pyproject.toml's src list in scripts/arch-check) was added after acceptance and before any code, from TASK-0102's close review: TASK-0102 made arch-check run beside pytest, ruff and mypy, which all read that file at startup, so a truncate-then-write could be read half done. It joined this task rather than a new one because this task already changed scripts/check and scripts/arch-check.

Closed on the independent review (Opus low, did not do the work): CLOSE, on the condition that AC #2's whole-check numbers are recorded (done in the notes above).
- AC #1 met narrowly: five green runs in a row as the notes say. The jail-lock group (conftest.py) names exactly the four files that start a jail on the per-user lock, with a true reason. The reviewer checked brig's /tmp paths (per-pid), the real-launch tests (--no-jail, XDG dirs under tmp_path), test_command_line.py and test_arch_check.py (gates under tmp_path) and found them safe ungrouped.
- AC #2 met: scripts/check passes -n auto --dist loadgroup, also for scripts/check MEMBER; 478 s to 155 s.
- AC #3 met: the batch check exit 0.
- AC #4 met: replace_file writes through mkstemp in the same directory, keeps the mode, os.replace, unlinks the temporary file on any failure, writes only on change; tests cover each, a concurrent reader included.
- Bare pytest stays serial (addopts has no -n).
Nits answered here, none filed: the guard test finds a jail-starting file by `BrigJail(` or `runner:confined"`, so a jail started from a conftest fixture or a helper module would slip past it (none does today; the group's reason says what belongs); os.replace turns a symlinked pyproject.toml into a file (not one here); captured output still hides a 2.5 min test run until it ends.
<!-- SECTION:NOTES:END -->
