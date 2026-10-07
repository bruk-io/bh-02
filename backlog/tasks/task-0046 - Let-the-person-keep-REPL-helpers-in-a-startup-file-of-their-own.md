---
id: TASK-0046
title: Let the person keep REPL helpers in a startup file of their own
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
labels:
  - kernel
dependencies: []
priority: low
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The kernel runs one startup file, the project's `.bh-02/kernel.py`. A person who wants the same helpers (show, search, refs) in every project has to copy them into each repo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The kernel runs a list of startup files: the person's own (outside the project) and then the project's
- [ ] #2 `~` is expanded on the host side, and each file is readable inside the jail
- [ ] #3 The model is told that only the project's file is its to edit
- [ ] #4 Tests cover both files, a missing one, and a failing one
<!-- AC:END -->
