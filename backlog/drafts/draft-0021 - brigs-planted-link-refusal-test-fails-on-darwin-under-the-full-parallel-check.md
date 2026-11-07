---
id: DRAFT-0021
title: brig's planted-link refusal test fails on darwin under the full parallel check
status: Draft
assignee: []
created_date: '2026-11-07 05:03'
labels:
  - brig
  - darwin
  - tests
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0079.34's review ran scripts/check (full tier, xdist) on macOS 27.0.1 on 2026-11-07: libs/brig/tests/integration/test_channel_planted_link.py::test_a_listener_that_left_after_listening_is_refused FAILED (no traceback kept in the -q summary). The orchestrator's serial run of 2026-11-06 passed test_channel_planted_link. It is in the verified dial TASK-0079.31 will rely on, so a load-dependent failure there may be a real race in the dial's leader/peer check, not only a test-timing issue. Not in TASK-0198 or TASK-0205.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The failure is reproduced on macOS with its traceback and explained (dial race or test timing)
- [ ] #2 The test passes on macOS both serially and under scripts/check, and still fails if the refusal it guards is removed
<!-- AC:END -->
