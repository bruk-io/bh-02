---
id: DRAFT-0028
title: >-
  runner:confined's darwin refusal names the archived TASK-0176.05, not
  TASK-0196
status: Draft
assignee: []
created_date: '2026-11-06T15:51:00Z'
updated_date: '2026-11-06T15:52:00Z'
labels:
  - brig
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Seatbelt jail moved from TASK-0176.05 (archived) to TASK-0196 on 2026-11-06, but the person-facing refusal still points to the old id: bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/jail.py:428 (error message), jail.py:7 (module docstring), bh-02/plugins/runner-cordis-plugin/README.md:252, tests/test_runner_confined.py:1771.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The darwin refusal message, the jail module docstring, the runner README and the test docstring name TASK-0196
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed directly in 224f96b (four text lines: jail.py's docstring and refusal message, the runner README, the darwin test's docstring), small enough not to need a task; scripts/check on the runner plugin exited 0 (266 passed). Archived as done.
<!-- SECTION:NOTES:END -->
