---
id: TASK-0167
title: 'Subagents README: bh-02 watch also ends when the session is no longer running'
status: To Do
assignee: []
created_date: '2026-10-18 23:55'
labels:
  - subagents
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The subagents README's 'Watching a child' bullet (around line 235) says bh-02 watch follows a log 'until agent_end'. TASK-0161 made the follow also end, saying so, once the session is no longer running (the pid in running.lock is gone); docs/bh-02/reference/command-line.md says that, the README does not. Found while doing TASK-0163, which is about the log-stopped note's Ctrl-C wording only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The subagents README's watch bullet names both ends: agent_end, and the session no longer running (saying so), as docs/bh-02/reference/command-line.md does
<!-- AC:END -->
