---
id: TASK-0103
title: >-
  Run the test suite on every core with pytest-xdist, keeping tests that share
  host state apart
status: To Do
assignee: []
created_date: '2026-10-15 02:28'
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
<!-- AC:END -->
