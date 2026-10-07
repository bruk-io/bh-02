---
id: TASK-0045
title: '/compact: continue a conversation from a summary'
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
labels:
  - commands
  - agent
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02 never compacts, so long sessions on local models hit the context window or slow down as the prompt grows. A compaction also refreshes the kept prompt and folds in the change notes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `/compact` asks the model for a summary and starts a new conversation seeded with it
- [ ] #2 Only the loop and transcript restart; the kernel's namespace is kept, since the summary refers to it
- [ ] #3 The new transcript is written in one step and the old one kept as `.bak`
- [ ] #4 The answer is `cleared`, a note carrying the summary, then `restarting`, so the ui's replay starts there
- [ ] #5 The model call has a timeout, since commands cannot be interrupted
<!-- AC:END -->
