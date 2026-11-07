---
id: TASK-0201
title: test_trajectory_view's sub-agent name test fails deterministically
status: To Do
assignee: []
created_date: '2026-11-07 04:27'
labels:
  - app
  - tests
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02/app/tests/test_trajectory_view.py::test_a_sub_agent_is_a_name_in_the_agents_directory_that_bh_02_makes_and_no_other fails in 0.15 s on macOS 27.0.1 (2026-11-06): the expected 'fine' is not in the output, which begins 'rows.jsonl not found: row reloads are not shown'. TASK-0169.04's review called it pre-existing on the base commit; nobody filed it. Check on Linux too.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause is in the notes and the test passes on macOS and Linux, still asserting what it was written to
<!-- AC:END -->
