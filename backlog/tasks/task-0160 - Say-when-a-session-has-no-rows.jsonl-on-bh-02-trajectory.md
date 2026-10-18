---
id: TASK-0160
title: 'Say when a session has no rows.jsonl, on bh-02 trajectory'
status: To Do
assignee: []
created_date: '2026-10-18 19:32'
labels:
  - app
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0149's ruling (Fable, 2026-10-18). The shell makes <session>/rows.jsonl at boot, before any reply (bootstrap.py, around 488-489), so a session with a conversation and no rows.jsonl had its row log removed or never written. bh-02 trajectory then shows no reloads with no sign why. test_trajectory_view.py (around 123-125) calls that case 'its rows have not loaded yet', which is not what it is.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02 trajectory prints one line, rows.jsonl not found: row reloads are not shown, for a session with a conversation and no rows.jsonl, and nothing new otherwise (tests)
- [ ] #2 test_trajectory_view.py's no-rows test says what the case is; scripts/check passes
<!-- AC:END -->
