---
id: TASK-0204
title: test_booting's 2 s deadlines fail when boots are slow (28 workers)
status: To Do
assignee: []
created_date: '2026-11-07 04:50'
updated_date: '2026-11-07 05:58'
labels:
  - bh-02
  - tests
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Under pytest -n 28 on a 28-core Mac (TASK-0202, 2026-11-06) test_the_shipped_stack_boots_around_a_patched_model, test_an_unrelated_providers_background_work_does_not_keep_run_from_returning and ..._does_not_keep_an_interactive_session_open failed: each boots the whole shipped stack (a Python process included) inside asyncio.wait_for(..., 2), and with 28 workers booting at once a boot takes longer. They pass alone (6 s) and at -n 8, which scripts/check now uses (TASK-0202), so the cap hides them rather than fixes them. Their timeout was also what triggered TASK-0202's hang.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The three tests state what they guard (does run() return once the chat row is done) without a deadline a slow boot misses, or with one justified against a measured boot under load
- [ ] #2 They pass under pytest -n 8 three runs in a row and alone
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-06: Ruled on TASK-0200 that the red full check on darwin does not hold up closing tasks whose criteria are limited to other areas; app-side failures in that run that belong to these deadlines stay here. Reviewers must still map each failure to its owning task in their closing notes.
<!-- SECTION:NOTES:END -->
