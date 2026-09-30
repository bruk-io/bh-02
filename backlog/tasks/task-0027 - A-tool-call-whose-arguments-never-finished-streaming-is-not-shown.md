---
id: task-0027
title: A tool call whose arguments never finished streaming is not shown
status: To Do
assignee: []
created_date: '2026-09-30 01:36'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0021. When Claude Code drops a connection mid-stream it closes the open block with content_block_stop before retrying, so a half-streamed tool call reaches the TUI with broken arguments just before the step fails. Nothing runs, but the person sees a call that was never made.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A tool call whose arguments don't parse when its block closes is not shown in the transcript or recorded as a call; a test with the fake Claude Code covers it
- [ ] #2 The step still fails with the existing restarted-reply error in that case, and a well-formed call is shown as before
- [ ] #3 scripts/check passes
<!-- AC:END -->
