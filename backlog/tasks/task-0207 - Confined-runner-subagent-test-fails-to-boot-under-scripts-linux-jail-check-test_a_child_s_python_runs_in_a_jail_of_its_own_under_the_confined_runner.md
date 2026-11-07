---
id: TASK-0207
title: >-
  Confined-runner subagent test fails to boot under scripts/linux-jail-check:
  test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner
status: To Do
assignee: []
created_date: '2026-11-07 05:39'
updated_date: '2026-11-07 05:53'
labels:
  - subagents
  - linux
  - tests
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On Linux under scripts/linux-jail-check (Docker, Ubuntu 24.04, bubblewrap 0.9.0, discovered while verifying TASK-0200's fix on Linux), bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner fails before any python program runs: _booted's assertion that every row's loader status is 'active' fails with {'loop': 'inactive', ...}. darwin always skips this test (no /usr/bin/bwrap), so it has not been seen failing there; it is unrelated to TASK-0200 (_running's liveness check), which never reaches this test's model, approval or runner:confined rows. Full run: testlock scripts/linux-jail-check -- bh-02/plugins/subagents-cordis-plugin -q -> 137 passed, 1 failed (only this test).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause of the loop row's inactive status under runner:confined in this container is named
- [ ] #2 The test passes under scripts/linux-jail-check, or is shown to need an environment this container cannot give (and says so by skipping, named)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-07: TASK-0200's AC3 was narrowed to leave this test's Linux failure to this task; TASK-0200 no longer waits on it. This task now owns the only known failure in the subagents plugin's tests on Linux.
<!-- SECTION:NOTES:END -->
