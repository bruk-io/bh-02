---
id: TASK-0214
title: Run the root confinement test in CI
status: To Do
assignee: []
created_date: '2026-11-08 19:23'
updated_date: '2026-11-08 19:23'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the comparison of root options for TASK-0079.31 (the owner chose scripts/linux-jail-check --root, 2026-11-08). The rejected rewording's research: the 'as root and as tester' wording spread by copying (494e49b7, 87680b6e, 1a42ac15, 5892f494) and records the machine of that time; no decision ruled on it. uid 0 paths are in brig, not the four member suites: compile_ctx.py:107, bwrap.py:416-426, oci.py:503, _supervisor_program.py:799; decision-197 grades uid 0 as a real deployment. No bh-02 test plants a block at the no-namespace endpoint; brig does (test_process_namespaces.py:57). Rejected prototypes, recoverable by SHA until git prunes them: option B 24170441, option C 064a4548.
<!-- SECTION:NOTES:END -->
