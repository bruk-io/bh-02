---
id: TASK-0129
title: >-
  Make the runner's real-jail tests wait for what the program wrote, not for its
  file
status: To Do
assignee: []
created_date: '2026-10-16 23:37'
labels:
  - runner
  - tests
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0128's worker: three real-jail tests in bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py wait for the program's report with `said.exists()`, which is true once the program creates the file, before it writes. A read in that window gets an empty or partial report, and the test fails on a run where the jail did everything right (seen once with the same wait in TASK-0128's new test, which now waits for one line per directory). The three: test_a_linux_jail_refuses_an_input_that_writes_the_interpreter_bh_02_runs_on, test_a_linux_jail_refuses_an_input_that_changes_a_link_on_the_way_to_the_interpreter_bh_02_runs_on and test_a_host_whose_python_is_not_at_the_usual_path_starts_a_confined_session.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the three waits until the report is complete (the lines it expects, or a write the program makes atomically by rename), and fails with what it read when the wait runs out
- [ ] #2 Each passes 10 of 10 repeated runs in a real bwrap jail
<!-- AC:END -->
