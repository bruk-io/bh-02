---
id: TASK-0083
title: >-
  Make the real-launch /model refusal test hold when the screen wraps the
  message
status: To Do
assignee: []
created_date: '2026-10-12 09:14'
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
- [ ] #1 The test waits for text that a line wrap cannot split (or matches across the wrap), and passes as root and as tester under tini
<!-- AC:END -->
