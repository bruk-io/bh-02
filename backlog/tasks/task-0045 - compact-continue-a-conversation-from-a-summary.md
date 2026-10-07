---
id: TASK-0045
title: '/compact: continue a conversation from a summary'
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 13:18'
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
- [x] #1 `/compact` asks the model for a summary and starts a new conversation seeded with it
- [x] #2 Only the loop and transcript restart; the kernel's namespace is kept, since the summary refers to it
- [x] #3 The new transcript is written in one step and the old one kept as `.bak`
- [x] #4 The answer is `cleared`, a note carrying the summary, then `restarting`, so the ui's replay starts there
- [x] #5 The model call has a timeout, since commands cannot be interrupted
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
agent:compact registers /compact [WHAT TO KEEP]: one model step over the loop's own request asking for a plain-text summary (a call it makes never runs), with a 300 s timeout and a note while it works. The transcript is rewritten in one step, the old kept under the first free .bak, .bak.2, ...; the loop and transcript restart and the kernel keeps its namespace. The answer is cleared, the note carrying the summary, the usage, then restarting. Quitting during the summary cancels it and changes nothing; held ! output survives. The operator's job queue moved to cordis-helpers (perform).
<!-- SECTION:FINAL_SUMMARY:END -->
