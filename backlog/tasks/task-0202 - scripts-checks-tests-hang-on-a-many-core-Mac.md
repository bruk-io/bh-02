---
id: TASK-0202
title: scripts/check's tests hang on a many-core Mac
status: To Do
assignee: []
created_date: '2026-11-07 04:27'
labels:
  - scripts
  - tests
  - darwin
  - size-2
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On a 28-core Mac (macOS 27.0.1, 2026-11-06) scripts/check's test step (pytest -n auto --dist loadgroup, so 28 workers) stalls: one worker goes silent around 4% and the 377 tests queued behind it never run; the run sat at 0% CPU for 28 minutes. With -n 8 the same suite finishes in 84 s. Three test_booting.py tests failed under -n auto and pass alone in 6 s. Earlier notes (TASK-0169.01, TASK-0170) blamed stray runs holding the jail lock; nothing held /tmp/bh-02-jails-501.lock during this hang. Until fixed, no 'scripts/check passes' criterion can be proven on this machine.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The hang is explained (which test or fixture, and why many workers trigger it)
- [ ] #2 scripts/check completes on a 28-core Mac every time (three runs in a row), whatever the core count, and the worker count it uses is said where TEST_WORKERS is set
- [ ] #3 Tests that fail only under load are fixed or filed, not retried away
<!-- AC:END -->
