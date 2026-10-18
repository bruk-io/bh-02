---
id: TASK-0142
title: A call left unanswered by a crash is answered when the session resumes
status: To Do
assignee: []
created_date: '2026-10-18 12:15'
labels:
  - agent
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
Found designing TASK-0136 (noted there, filed at the owner's word 2026-10-18). The loop appends a step's assistant entry, with its calls, before it runs them; a stop answers every call (_INTERRUPTED, _NOT_RUN), but a process that dies mid-call answers none. A resumed session then sends the model a call with no result after it, which a provider rejects or the model answers again. The loop's next reply should answer such a call first, as it answers calls a stop interrupts, so the conversation is whole before any request.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Before the first request of a resumed conversation, every call in the transcript with no tool entry after it is answered with an entry saying bh-02 stopped before the call finished and it may have partly run (wording as _INTERRUPTED's), in the calls' order, with a call record (decision-0009) whose fields say no answer or run time was recorded
- [ ] #2 A test resumes a transcript cut after a step's calls (one call answered, one not) and shows the request the model receives has a result for every call; another shows a whole transcript is sent unchanged
- [ ] #3 The claude-code provider still resumes such a session (its reconcile rebuilds or accepts it; a test) ; scripts/check passes
<!-- AC:END -->
