---
id: TASK-0153
title: >-
  A transcript write failure (a full disk) ends bh-02 with a traceback instead
  of a recoverable failure
status: To Do
assignee: []
created_date: '2026-10-18 13:24'
labels:
  - agent
  - chat
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
FileTranscript raises the writer's OSError from append, flush and the row's leaving. chat:converse shows only an exception with kind and message (Recoverable) and re-raises the rest; bootstrap._await_chat propagates it and cli.py re-raises a non-Recoverable one. Read from the code, not run: a full disk during a reply therefore ends bh-02 with a traceback and the conversation in memory lost, where a TranscriptReplaced (TASK-0139) is shown and the chat carries on. Make a failed transcript write a recoverable failure that says which file, what failed, and what the person can do (free space, then /restart transcript), keeping the writer's rule that nothing after a failed write is written.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A transcript write that fails (a full disk) is shown to the person as a recoverable failure (kind and message) naming the file and /restart transcript, and the chat carries on
- [ ] #2 Tested from the loop with a failing write: the reply's error has kind and message, and nothing after the failed line reaches the file
<!-- AC:END -->
