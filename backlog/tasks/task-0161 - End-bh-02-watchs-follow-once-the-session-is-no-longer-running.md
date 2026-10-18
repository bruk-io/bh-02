---
id: TASK-0161
title: End bh-02 watch's follow once the session is no longer running
status: To Do
assignee: []
created_date: '2026-10-18 19:32'
labels:
  - app
  - subagents
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by Fable ruling TASK-0148 (2026-10-18). bh-02 watch SESSION AGENT follows a child's event log until its agent_end line. A log that stopped writing never gets one, nor does a session that ended without it (a crash), so the follow never ends and Ctrl-C is the only way out. TASK-0143 made a running bh-02 hold its session's running.lock; watch can end its follow once that lock is free (the session no longer runs) and say why.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02 watch ends its follow, saying the session is no longer running, once the session's running.lock is free, even with no agent_end in the log (a test with the lock released and no end line)
- [ ] #2 A follow of a running session's child is unchanged; watch never takes the lock; scripts/check passes
<!-- AC:END -->
