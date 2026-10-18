---
id: TASK-0138
title: 'Retire turn in scripts/model-friction: it counts replies'
status: To Do
assignee: []
created_date: '2026-10-18 04:15'
labels:
  - scripts
  - naming
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-0009 retires "turn". TASK-0136.02 renamed every use under bh-02/ and docs/bh-02/; scripts/model-friction (outside that scope) still has the `interrupted` signal's text "a turn the person stopped mid-input", the `Totals.turns` field and the `turns` counter in main, all of which mean a reply (a user message that is not feedback). Prose and names only: no behaviour change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/model-friction has no turn: the signal text says reply, Totals.turns is Totals.replies, and the counter is named for what it counts
- [ ] #2 scripts/model-friction --json and its report print what they printed before (the report already says replies)
<!-- AC:END -->
