---
id: TASK-0154
title: >-
  /compact of a resumed session whose last call a crash left unanswered sends
  that call with no result
status: To Do
assignee: []
created_date: '2026-10-18 13:55'
labels:
  - agent
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found doing TASK-0142, which answers a call a crash left unanswered at the loop's next reply (loop.py _unanswered_calls, _LOST). /compact does not go through a reply: conversation.py compact_conversation reads the transcript file itself and asks the model for a summary over asked(messages) = request_for(messages) plus its ask, so a session resumed after a process died mid-call, and compacted before the next message, sends the model a call with no result after it, which a provider rejects or the model answers again. The summary request should have a result for every call, worded and recorded as TASK-0142's answers are (_LOST, a call record of the time alone), without changing the entries already in the file.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A test runs /compact over a transcript cut after a step's calls (one answered, one not) and shows the summary request the model receives has a result for every call, in the calls' order, worded as the loop's _LOST answer
- [ ] #2 A test shows /compact over a whole transcript sends the request it sent before, unchanged
- [ ] #3 scripts/check passes
<!-- AC:END -->
