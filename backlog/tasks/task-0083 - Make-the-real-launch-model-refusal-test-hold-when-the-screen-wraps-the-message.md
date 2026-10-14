---
id: TASK-0083
title: >-
  Make the real-launch /model refusal test hold when the screen wraps the
  message
status: Done
assignee:
  - '@claude'
created_date: '2026-10-12 09:14'
updated_date: '2026-10-14 03:16'
labels:
  - app
  - tests
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0079.27 (unrelated to it; fails on the unchanged tree too). bh-02/app/tests/test_real_launch.py::test_a_patch_that_sets_the_model_row_s_config_keeps_its_model_and_says_so waits for the token "row's config" on the screen. The message names the patch file's path, so with a longer tmp path (run as the tester user: /tmp/pytest-of-tester/pytest-N/...) the TUI wraps the line between "row's" and "config", and the wait fails although the right message is shown. As root the path is shorter and it passes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The test waits for text that a line wrap cannot split (or matches across the wrap), and passes as root and as tester under tini
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Message text: switch.py:148 'not switched: {patch} sets the {row!r} row's config, which replaces the session's ... whole'. 2. Test waits (after said) for 'row's config' which a wrap splits. Change to wait for the single word 'replaces' (unbreakable, unique to that message, only searched after 'not switched:'). 3. Prove: run the unchanged test as tester under tini (expect fail), restore, run as root and tester (expect pass). 4. uv run pytest test_real_launch.py, scripts/check. Risk: none to app; only the test wait token changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause: the message from switch.py (not switched: {patch} sets the 'model' row's config, which replaces ...) wraps at the long tmp path, so 'row's config' is split across two screen lines. Change: test_real_launch.py waits for the single word 'replaces' from the same message (after the 'not switched:' offset) instead of the phrase. Message and app untouched.
Evidence:
- Before (unchanged test, as tester under tini: su tester -c 'cd /home/user/bh-02 && tini -s -- .venv/bin/python -m pytest -q -p no:cacheprovider bh-02/app/tests/test_real_launch.py -k patch_that_sets'): FAILED, '"row's config" never appeared'; the screen showed the full message wrapped as "sets the 'model' row's" / "config, which replaces".
- After, root (uv run pytest bh-02/app/tests/test_real_launch.py -k patch_that_sets -q): 1 passed, exit 0.
- After, tester under tini (same command): 1 passed, exit 0.
- Full file as root (uv run pytest bh-02/app/tests/test_real_launch.py -q): 30 passed, exit 0.
- scripts/check (root): 2528 passed, 31 skipped; gates ok; docs ok; tokens skipped (no ../bh-01/dist); exit 0.
Note: the before-run was on the unchanged tree (no stash needed, tree was clean).

Closed on review (Opus, low) of 0d6f5d4: CLOSE, nothing blocking, nothing to fix. 'replaces' after 'not switched:' identifies only the shadowed-patch message (switch.py:148); the test still checks the patch's model is kept and --model refused. Root and tester under tini: 1 passed each; the pre-commit test failed as tester ('row's config never appeared'). The whole real-launch file as tester under tini: 30 passed, so no other wait splits on a wrap. Nit left: the wait no longer checks the words 'row's config' themselves.
<!-- SECTION:NOTES:END -->
