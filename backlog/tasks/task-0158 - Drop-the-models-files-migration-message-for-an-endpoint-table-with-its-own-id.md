---
id: TASK-0158
title: Drop the models file's migration message for an endpoint table with its own id
status: To Do
assignee: []
created_date: '2026-10-18 19:09'
labels:
  - models
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner's no-compatibility rule (root CLAUDE.md, Conventions), decided 2026-10-18 after TASK-0157. named.py _endpoint_problem refuses an endpoint table that has its own id with a message written for the move from one model per table to endpoints with nested models (TASK-0104.01). It exists only to recognise that old shape. Dropped, such a table gets the generic error for a built-in provider (id is not a setting of the endpoint), and a factory provider (module:attribute) takes a stray id as it takes any other setting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 _endpoint_problem has no check for an id on an endpoint table, and no message, docstring or doc page describes the old one-model-per-table shape
- [ ] #2 The test files that used an old-shape table as their broken models file use another broken table, and still prove what they proved (each test's assertion is about its own subject, not the old shape)
- [ ] #3 A test shows an endpoint table with an id on a built-in provider is refused with the generic error; scripts/check passes
<!-- AC:END -->
