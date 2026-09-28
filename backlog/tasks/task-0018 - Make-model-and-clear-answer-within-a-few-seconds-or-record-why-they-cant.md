---
id: task-0018
title: 'Make /model and /clear answer within a few seconds, or record why they can''t'
status: To Do
assignee: []
created_date: '2026-09-28 12:26'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-0014's live run measured 12-15 s for /model and /clear while the Claude Code CLI restarted. That measurement predates strict_mcp_config, which cut the CLI's start-up work. Measure the time now; if it is still slow, bring it down where the cost can be avoided (e.g. switching models without restarting the process).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The time from /model NAME (and /clear) to the next reply being possible is measured against the real Claude Code CLI and recorded in the task notes
- [ ] #2 If the measured time is over ~5 s, the avoidable part is removed and re-measured, or the notes say what makes it unavoidable
- [ ] #3 Any change keeps the conversation carrying on after /model, and is covered by a test
- [ ] #4 The Claude credential is only read from local.env as CLAUDE.md prescribes, never printed or logged
<!-- AC:END -->
