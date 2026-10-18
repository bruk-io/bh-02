---
id: TASK-0148
title: >-
  Say when a sub-agent's event log stopped being written, as the row log now
  does
status: To Do
assignee: []
created_date: '2026-10-18 12:33'
labels:
  - subagents
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0145. A child's events.jsonl (subagents plugin, eventlog.py) stops writing on a failed write and the child goes on, and nothing tells the person, so bh-02 watch and the trajectory of a sub-agent are missing its later events with no sign why. The row log now says so once after the app exits (bootstrap._row_log, through run()'s report). Decide how a plugin's event log reaches that channel without the plugin importing bh_02 (plugin-layering), then say it the same way. The owner's call is whether the sub-agent log should speak at all, since eventlog.py documents it as best-effort.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A sub-agent's event log that stops after a failed write is said once after the app exits, naming the file, when and the error, as the row log's line is.
- [ ] #2 A run whose event logs never failed says nothing new, and the test with an unwritable event log proves it.
<!-- AC:END -->
