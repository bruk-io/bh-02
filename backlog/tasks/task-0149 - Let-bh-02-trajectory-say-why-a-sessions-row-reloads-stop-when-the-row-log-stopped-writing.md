---
id: TASK-0149
title: >-
  Let bh-02 trajectory say why a session's row reloads stop, when the row log
  stopped writing
status: To Do
assignee: []
created_date: '2026-10-18 12:33'
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
- [ ] #1 The answer names where the stop is kept (or that nothing is kept) and why, against decision-0009's rule of no new file beside the transcript, and the owner has ruled on it.
<!-- AC:END -->
