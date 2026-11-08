---
id: TASK-0216
title: >-
  Find why scripts/check on darwin fails with a killpg EPERM and an appender
  teardown error
status: To Do
assignee: []
created_date: '2026-11-08 19:57'
labels:
  - brig
  - runner
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two scripts/check failures on darwin have no explanation. (1) test_an_extension_that_ends_the_worker_is_not_loaded_again_until_something_changes: PermissionError EPERM from os.killpg in extensions_cordis_plugin/testing.py _Started.stop, recorded in TASK-0079.31's notes; bcf17e7c touched that helper, so that commit is not ruled out. (2) A teardown error at test_a_file_replaced_under_the_appender_is_refused_and_neither_file_is_written[removed-held open], run at main 61cde05b, no traceback kept. test_a_file_that_fails_is_not_checked also failed in that run with no traceback; it may share TASK-0215's cause, which is inferred only. Each is rare: 2 of the last 4 runs of scripts/check failed, and these appeared only in some.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each failure has a cause said in the notes, from a traceback and a reproduction, or the notes say how many scripts/check runs were tried without seeing it again
- [ ] #2 A cause that is a defect is fixed or filed as its own task
<!-- AC:END -->
