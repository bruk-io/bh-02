---
id: TASK-0149
title: >-
  Let bh-02 trajectory say why a session's row reloads stop, when the row log
  stopped writing
status: To Do
assignee: []
created_date: '2026-10-18 12:33'
updated_date: '2026-10-18 19:32'
labels:
  - app
  - size-2
dependencies: []
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0145, a design question for the owner. The shell now prints once, after the app exits, that rows.jsonl stopped being written (TASK-0145). A trajectory read later (bh-02 trajectory) still shows its reloads missing with no sign why, because the line is only on the terminal that ran the app and the file cannot hold a line once it has failed. Answer: where the stop should be kept so that the trajectory can say it (decision-0009 keeps no new file beside rows.jsonl; a line in events.jsonl or the transcript are the candidates), and whether a trajectory that is missing rows should say so at all. Answer the question; no code.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The answer names where the stop is kept (or that nothing is kept) and why, against decision-0009's rule of no new file beside the transcript, and the owner has ruled on it.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ruled 2026-10-18 by Fable, at the owner's request ("for 1 and 2, ask fable"): nothing new is kept. The shell's after-exit line (TASK-0145) is the record of the stop, and it also goes to --trace FILE as a report: line (cli.py, around 283-288). The trajectory says only what its files prove.
Why: events.jsonl is the ui's alone (history.py), written by the ui on the event loop, and the trajectory does not read it (viewing.py reads transcripts and rows.jsonl). The shell learns of the stop in a listener or at close, after the ui is gone, and has no writer for the ui's file. The transcript is what the model is sent (request_for), and the loop is its one writer through its Appender; a shell entry would need a role request_for skips, a format change in two packages, and a second writer to the conversation's file. A failure that stops rows.jsonl (ENOSPC, the directory gone, EIO) stops its siblings too, the transcript among them, whose failed write is raised and shown.
Recorded in decision-0009, Row reloads (commit fcadab0). Follow-ups on the board: TASK-0160 (bh-02 trajectory says when a session has no rows.jsonl) and TASK-0161 (bh-02 watch ends its follow once the session no longer runs).
<!-- SECTION:NOTES:END -->
