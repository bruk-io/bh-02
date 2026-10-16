---
id: TASK-0106
title: How should the REPL tell the model of the functions its startup files define?
status: Done
assignee: []
created_date: '2026-10-16 02:03'
updated_date: '2026-10-16 02:58'
labels:
  - python
  - size-2
  - finish-moved
dependencies: []
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
priority: medium
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner (2026-10-15/16) dropped @helper and the word helper: a startup file's public functions are just functions the model has, told by progressive disclosure. The python tool must make the model understand what they cost in context and how; a docstring convention gives examples; a check enforces it with no model. decision-0006 records the answer and supersedes decision-0004.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decision recorded
- [x] #2 The owner has accepted decision-0006 (its status is accepted), including the signature budget and point 7's checks
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: finish moved: the criterion named the proposed 1,500-character budget; the owner accepted decision-0006 with 600 instead.
- Decision recorded: backlog/decisions/decision-0006 (status accepted 2026-10-16 by the owner in conversation; Acceptance section says so). decision-0004 marked superseded.

Review (closing reviewer): CLOSE. AC1 met: decision-0006 has context, decision, consequences; task references it. AC2 met: status accepted, Acceptance records owner acceptance 2026-10-16 with 600-char budget (600 is the only budget stated; 1,500 appears only as the rejected proposal); decision-0004 status superseded. Spot checks true: client.py:389 runs the worker with -I; runner jail.py reads sys.base_prefix/sys.prefix. TASK-0107/0108/0109 match points 1-6 and 7. Findings: nit, no full check declared (.claude/checks.json absent) so record-check could not run; design task has no code. No drafts filed.
<!-- SECTION:NOTES:END -->
