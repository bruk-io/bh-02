---
id: TASK-0049
title: Tell a resumed conversation's memory notes only once
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 13:18'
labels:
  - agent
  - context
  - kernel
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The rows that add to `memory` (shell hints, on-touch guidance) keep what they have told as their own state, which starts empty when a session is resumed, so a note the transcript already carries can be told again.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After `--resume`, guidance, a rule or a shell hint already told in the transcript is not told again
- [x] #2 `/clear` still starts afresh
- [x] #3 Tests cover a resume after a note was told
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
kernel:shell_hints and context:on_touch read the transcript's messages once, at the first input that may need them, and count a note as told when a tool entry holds it whole after a blank line, so a resumed conversation is not told it again, while a file cut back since is. /clear and /compact start them afresh. The search for told notes is linear in the transcript.
<!-- SECTION:FINAL_SUMMARY:END -->
