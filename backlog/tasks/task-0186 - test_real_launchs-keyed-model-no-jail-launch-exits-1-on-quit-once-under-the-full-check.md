---
id: TASK-0186
title: >-
  test_real_launch's keyed-model --no-jail launch exits 1 on quit, once, under
  the full check
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T03:39:00Z'
updated_date: '2026-11-04T13:49:00Z'
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

Changed: all 43 exit_code() mismatches in bh-02/app/tests/test_real_launch.py (each 'assert X.exit_code(..) == N') now carry f"exit code was not N; the screen said:\n{X.text()[-3000:]}" (same shape as the existing wait_for/exit_code messages). Showing it works: planted '== 7' on the keyed-model launch (line 980); the failure printed 'assert 0 == 7' plus the whole last screen (session line, 'the input said: False False'); plant removed (diff is only the 43 message additions). Recurrence: scripts/check bh-02/app run 3 times (member check, not the whole-repo scripts/check; it includes test_real_launch), all exit 0, first lines were uv's UV_NATIVE_TLS deprecation warning; the keyed-model --no-jail launch failure did NOT recur in 3 runs. No repro: the original failure was seen once (reviewer's full run for TASK-0179 on 1e0b11b) and could not be reproduced on demand; a planted failure is not a repro. Criterion #2 left unticked: no recurrence, so cause is unknown; the new message will show the screen if it recurs. Criteria left unticked for the reviewer; AC#3 includes planted-failure evidence above.
<!-- SECTION:NOTES:END -->
