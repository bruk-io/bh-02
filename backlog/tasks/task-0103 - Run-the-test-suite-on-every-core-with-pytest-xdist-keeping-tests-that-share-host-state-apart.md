---
id: TASK-0103
title: >-
  Run the test suite on every core with pytest-xdist, keeping tests that share
  host state apart
status: To Do
assignee: []
created_date: '2026-10-15 02:28'
updated_date: '2026-10-15 12:37'
labels:
  - tests
  - size-3
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
- [ ] #1 uv run pytest -n auto runs the whole suite green five times in a row, with the groups that share host state named in conftest and their reason beside each
- [ ] #2 scripts/check uses it, and its wall time before and after is recorded; or the notes say why it stays serial and what would have to change first
- [ ] #3 scripts/check passes
- [ ] #4 scripts/arch-check writes the root pyproject.toml's src list atomically (a temp file then os.replace), since it now runs while pytest, ruff and mypy read that file at startup (from TASK-0102's close review)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-0102's close review (2026-10-15):
- Should-fix, now AC #4: scripts/arch-check's sync_src writes pyproject.toml with write_text (truncate, then write) while scripts/check starts pytest, ruff and mypy beside it, and all three read that file at startup. It writes only when the src list changes (a new member), so the window is small but real.
- Nit, not a criterion: scripts/check captures each step's output, so a long test run shows nothing until it ends. If xdist changes how the tests report, keep that in mind; no change is asked for.
<!-- SECTION:NOTES:END -->
