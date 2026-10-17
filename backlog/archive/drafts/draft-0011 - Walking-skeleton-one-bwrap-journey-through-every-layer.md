---
id: DRAFT-0011
title: 'Walking skeleton: one bwrap journey through every layer'
status: Draft
assignee: []
created_date: '2026-10-17 17:45'
labels:
  - brig
  - size-5
dependencies:
  - DRAFT-0009
parent_task_id: TASK-0135
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

decision-0008's order, step 3: the thinnest real journey through domain, infra and presentation, built outside-in, so every later slice grows from working code (the owner's test rules: work outside-in).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Through brig's public API an embedder creates a bwrap jail, runs true in it, sees exit 0, and destroys it, and the teardown verifies that no process of the jail is left
- [ ] #2 The journey crosses every layer: the domain compiles the jail and yields the operation's effects, the bwrap driver in presentation performs them, and infra does the I/O with plain data
- [ ] #3 It has one unit test (the domain's compile, nothing mocked), one integration test (the journey with the world faked at infra's edge) and one e2e test (the journey against real bubblewrap)
- [ ] #4 just done passes, with every pypeeker rule from the scaffolding holding on the new code
<!-- AC:END -->
