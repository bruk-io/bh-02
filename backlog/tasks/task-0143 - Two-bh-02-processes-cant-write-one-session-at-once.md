---
id: TASK-0143
title: Two bh-02 processes can't write one session at once
status: To Do
assignee: []
created_date: '2026-10-18 12:15'
labels:
  - app
  - size-3
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found designing TASK-0136 (noted there, filed at the owner's word 2026-10-18). Nothing stops bh-02 --resume ID while another bh-02 still runs that session: both append to its transcript, rows.jsonl and the ui's history, interleaving two conversations in one file. The shell should hold the session for the run and refuse a second.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A running bh-02 holds its session directory exclusively (an advisory lock on a file in it, held for the run and released however the run ends, including a crash)
- [ ] #2 bh-02 --resume of a session another process holds refuses before any row starts, with an error naming the session and the process that holds it and what to do; a test runs two and sees the second refused
- [ ] #3 bh-02 sessions, bh-02 trajectory and bh-02 watch read a held session as before (they take no lock); scripts/check passes
<!-- AC:END -->
