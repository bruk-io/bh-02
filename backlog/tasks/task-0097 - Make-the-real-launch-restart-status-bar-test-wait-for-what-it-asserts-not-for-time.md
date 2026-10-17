---
id: TASK-0097
title: >-
  Make the real-launch restart status-bar test wait for what it asserts, not for
  time
status: To Do
assignee: []
created_date: '2026-10-14 13:40'
updated_date: '2026-10-17 02:33'
labels:
  - app
  - tests
  - size-2
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02/app/tests/test_real_launch.py::test_while_the_model_restarts_the_status_bar_says_so_and_a_message_waits_visibly failed once in TASK-0093's close review (221 passed, 1 failed) and passed alone and on rerun; TASK-0087's worker saw a timing flake in a test_real_launch status-bar test the same way. TASK-0093 added a second pty launch to the file. A real-launch test that reads a pty must wait for the text it asserts (as TASK-0083 did for the /model refusal), never for a fixed time; find what this one races on and make it wait for it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test waits for the screen text it asserts, with a bound, never for a fixed delay; the race it had is named in the notes
- [ ] #2 test_real_launch.py passes 20 runs in a row under load (for example beside another pytest process), recorded in the notes
- [ ] #3 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred by the owner (2026-10-15): this run fixes only critical bugs; this one is not critical (no data loss, no security exposure, a workaround exists). Not to be started without the owner's word.

Orchestrator, 2026-10-17: the owner's word to start it, which the earlier deferral asked for: "ok wrap up all tasks that you are able to" (in conversation, this date).
<!-- SECTION:NOTES:END -->
