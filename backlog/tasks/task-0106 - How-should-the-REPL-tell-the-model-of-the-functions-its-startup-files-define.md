---
id: TASK-0106
title: How should the REPL tell the model of the functions its startup files define?
status: To Do
assignee: []
created_date: '2026-10-16 02:03'
labels:
  - python
  - size-2
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
- [ ] #1 Decision recorded
- [ ] #2 The owner has accepted decision-0006 (its status is accepted), including the 1,500-character budget and point 7's check
<!-- AC:END -->
