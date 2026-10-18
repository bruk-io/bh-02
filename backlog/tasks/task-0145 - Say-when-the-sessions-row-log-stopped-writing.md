---
id: TASK-0145
title: Say when the session's row log stopped writing
status: To Do
assignee: []
created_date: '2026-10-18 12:15'
labels:
  - app
  - size-1
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0136.11's review. When a write to <session>/rows.jsonl fails (the disk is full), the shell's listener removes itself and the run goes on (bootstrap.py _row_log), as the sub-agent event log does, but nothing tells the person, so a trajectory read later is missing its reloads with no sign why. The shell speaks once the app has exited (bh-02/CLAUDE.md, the app owns the terminal), so that is where it says it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When the row log stopped, the shell prints one line after the app exits saying it stopped, when, and the error (a test with an unwritable log)
- [ ] #2 A run whose row log never failed prints nothing new; scripts/check passes
<!-- AC:END -->
