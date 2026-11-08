---
id: TASK-0217
title: >-
  Let darwin share one session jail by narrowing each start's channel and
  scratch grants
status: To Do
assignee: []
created_date: '2026-11-08 22:25'
labels:
  - brig
  - runner
  - size-3
dependencies:
  - TASK-0074
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner's ruling on TASK-0074, 2026-11-08: a session shares one jail only where Process.namespaces holds the bundle; elsewhere it keeps a jail per program. Measured under the runner's policy on darwin in one jail, program B lists A's socket, sees A's scratch file and unlinks A's socket, after which the host's redial of A fails; today's separate jails refuse the unlink and hide the scratch file. Connect and signal were refused, but no grade promises it (channel_exclusivity is unenforced). This task finds out whether brig can narrow each start's channel and scratch grants on Seatbelt so darwin can share a jail too. That looks possible but is unproven, so it starts as a question.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Under Seatbelt, a start can be granted only its own channel and scratch paths in one jail, measured with program B attacking program A, or the notes show why it cannot
- [ ] #2 If it can, the grade that promises it is named in brig's SPEC and darwin joins TASK-0074's shared jail; if not, the notes say so and darwin keeps a jail per program
<!-- AC:END -->
