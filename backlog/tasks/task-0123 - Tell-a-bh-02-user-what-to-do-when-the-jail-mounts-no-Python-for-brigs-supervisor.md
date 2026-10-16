---
id: TASK-0123
title: >-
  Tell a bh-02 user what to do when the jail mounts no Python for brig's
  supervisor
status: To Do
assignee: []
created_date: '2026-10-16 13:48'
labels:
  - runner
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0084.02's close review. When no interpreter the jail mounts is found, brig's InterpreterNotMounted reaches the runner row's boot diagnosis unchanged, and its advice ('build the mechanism with strict_linux(python=...)') is for code that embeds brig, not for a bh-02 user, whose steps are to install python3 or run with --no-jail, as the runner's missing-bwrap error already says. cordis prints the exception's repr, so a note added with add_note would not show: the runner has to raise its own error naming those steps, with brig's as its cause.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A host whose jail mounts no usable interpreter fails the runner row with a message that tells the person to install python3 or run with --no-jail, and names brig's reason, shown by the app-level test TASK-0084.02 added
- [ ] #2 brig is unchanged
<!-- AC:END -->
