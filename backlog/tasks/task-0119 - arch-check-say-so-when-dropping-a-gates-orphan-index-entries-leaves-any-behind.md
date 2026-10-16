---
id: TASK-0119
title: >-
  arch-check: say so when dropping a gate's orphan index entries leaves any
  behind
status: To Do
assignee: []
created_date: '2026-10-16 12:14'
labels:
  - gates
  - scripts
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0118's close review. scripts/arch-check's drop_entries unlinks orphan index entries by pypeeker's storage layout (.pypeeker/index/<path>.json, what IndexStore.remove unlinks) with missing_ok, since pypeeker has no command for it. If pypeeker's layout changes, the drop becomes a silent no-op: the orphans come back and the gate slows again with nothing said. After the drop, read indexed() again and fail the gate, naming the entries, if any it meant to drop is still listed; the docstring says why.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After dropping, scripts/arch-check fails the gate with a message naming the entries if any entry it dropped is still indexed, and a test shows it with an index whose entry file is not where the layout says
- [ ] #2 drop_entries' docstring says what a layout change would do and that the check catches it
<!-- AC:END -->
