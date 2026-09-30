---
id: task-0027
title: A tool call whose arguments never finished streaming is not shown
status: To Do
assignee: []
created_date: '2026-09-30 01:36'
updated_date: '2026-09-30 01:40'
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
- [ ] #1 When Claude Code closes a stream it will retry (message_stop with no stop reason) while a tool call's arguments are incomplete, that call is neither shown nor recorded; a test with the fake Claude Code covers it
- [ ] #2 A call whose arguments genuinely didn't decode in a finished step (a stop reason arrived) is still shown and classified as today; the loop's existing undecodable-call tests pass unchanged
- [ ] #3 scripts/check passes
<!-- AC:END -->
