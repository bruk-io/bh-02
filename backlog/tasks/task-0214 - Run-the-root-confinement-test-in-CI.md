---
id: TASK-0214
title: Run the root confinement test in CI
status: To Do
assignee: []
created_date: '2026-11-08 19:23'
labels:
  - ci
  - brig
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
test_bwrap_root_confined.py is the one test that notices brig losing its root confinement: with --cap-drop ALL removed on purpose it failed as root, while the four member suites stayed at 704 passed. It is in neither the default run of scripts/linux-jail-check nor the suites, and it skips as the unprivileged user, so .github/workflows/linux-jail.yml never runs it. It guards the hole TASK-0079.20 found, and its last recorded run before TASK-0079.31 was a one-off in TASK-0198. scripts/linux-jail-check --root now makes the run possible.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 linux-jail.yml runs libs/brig/tests/integration/test_bwrap_root_confined.py through scripts/linux-jail-check --root, and a failure there fails the job
- [ ] #2 The job is seen failing with brig's --cap-drop ALL removed, then passing with it restored
<!-- AC:END -->
