---
id: TASK-0163
title: >-
  Sub-agent log-stopped note: say bh-02 watch ends with the session, not only by
  Ctrl-C
status: To Do
assignee: []
created_date: '2026-10-18 20:58'
labels:
  - subagents
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0161 made bh-02 watch end its follow, saying so, once the session is no longer running (the pid in running.lock is gone). The note child.log_stopped (TASK-0148) still says a watch of a log that stopped 'must be left with Ctrl-C'; it is true only while the session runs. Reword it (child.py, subagents README line ~230, CONTRACTS.md subagents:parent row, their tests in test_agents_child.py and test_agents_wiring.py) to say watch shows nothing after it until the session is no longer running, or Ctrl-C leaves it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The log-stopped note says bh-02 watch shows nothing after the failure and ends when the session is no longer running or on Ctrl-C
- [ ] #2 The subagents README, CONTRACTS.md and tests say the same; scripts/check passes
<!-- AC:END -->
