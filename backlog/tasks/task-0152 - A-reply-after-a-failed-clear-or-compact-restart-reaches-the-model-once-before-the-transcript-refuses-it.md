---
id: TASK-0152
title: >-
  A reply after a failed /clear or /compact restart reaches the model once
  before the transcript refuses it
status: To Do
assignee: []
created_date: '2026-10-18 13:24'
labels:
  - agent
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0139 made a transcript whose file was replaced under it refuse every entry, as TranscriptReplaced naming /restart transcript. The check runs on the appender's writing thread, so the refusal surfaces at the first append made after the thread has run it: in a reply that is the step's entry, after the model step (the person's message and the model's answer from the old conversation are shown first, then the notice). Only that first message after the failed restart gets this; every later append is refused at once. Find the cheapest way to refuse it before the model is asked (for example the loop awaiting the transcript's health at the start of a reply without a disk wait, or a check the transcript can make without a stat on the event loop), without a flush per entry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reply begun after a /clear or /compact whose restart failed is refused before the model is asked: the scripted model sees no request, and the error is the TranscriptReplaced that names /restart transcript
- [ ] #2 A reply over a transcript whose file was not replaced costs the event loop no wait on a disk, and the flush-count tests in test_loop.py still hold or change for a stated reason
<!-- AC:END -->
