---
id: TASK-0186
title: >-
  test_real_launch's keyed-model --no-jail launch exits 1 on quit, once, under
  the full check
status: To Do
assignee: []
created_date: '2026-11-03T03:39:00Z'
updated_date: '2026-11-04T12:39:00Z'
labels:
  - tests
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen once in the reviewer's full scripts/check for TASK-0179 (2026-11-03, on 1e0b11b): test_a_keyed_model_s_key_never_reaches_an_input_s_environment asserted app.exit_code() == 0 and got 1 after Ctrl-Q. Passes alone and in later full runs; not reproduced. The cause is unknown and could involve the Unjailed stop path that TASK-0179 changed (it now removes the socket directory on stop). The assertion shows nothing of why.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When the launch's exit code is not 0, the failure shows the app's last screen and stderr (app.text())
- [ ] #2 If it recurs, the cause is named and fixed, or the test's flake is explained in its notes
- [ ] #3 Every exit_code() mismatch in test_real_launch.py shows app.text() in its failure; a planted non-zero exit shows it
- [ ] #4 The notes record whether the keyed-model launch failure recurred over a stated number of full runs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
