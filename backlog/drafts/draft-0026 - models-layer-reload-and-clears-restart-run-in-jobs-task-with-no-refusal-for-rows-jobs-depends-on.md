---
id: DRAFT-0026
title: >-
  /model's layer reload and /clear's restart run in jobs' task with no refusal
  for rows jobs depends on
status: Draft
assignee: []
created_date: '2026-11-04T13:57:00Z'
labels:
  - commands
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0185. TASK-0185 makes /restart refuse jobs and every row it depends on (operations.py _jobs_needs), but two other paths run a loader change inside the jobs row's task with no such check: models switch.py:184 queues self.loader.reload, which applies the whole session layer (any edit to it, e.g. a hand edit of the ui row's config since the last reload, is applied there); and agent conversation.py:453/484 queue loader.restart of the conversation rows, which self-cancel if a layer makes jobs depend on one of them. Either reaches jobs, cancels half-way and leaves rows unmounted, the TASK-0185 failure. Fix in one place: share the refused set, or have cordis's Loader finish a begun restart/apply (the owner's open design question).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A queued reload or restart whose change set reaches the jobs row either finishes with every row back up or is refused with a reason
- [ ] #2 A test: a layer edit to the ui row followed by /model NAME leaves every row active
<!-- AC:END -->
