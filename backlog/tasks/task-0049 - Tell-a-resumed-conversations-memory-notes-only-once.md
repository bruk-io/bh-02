---
id: TASK-0049
title: Tell a resumed conversation's memory notes only once
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
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
- [ ] #1 After `--resume`, guidance, a rule or a shell hint already told in the transcript is not told again
- [ ] #2 `/clear` still starts afresh
- [ ] #3 Tests cover a resume after a note was told
<!-- AC:END -->
