---
id: DRAFT-0008
title: Delete the old brig from libs/brig
status: Draft
assignee: []
created_date: '2026-10-17 17:45'
labels:
  - brig
  - size-1
dependencies: []
parent_task_id: TASK-0135
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

decision-0008 ("Where it is built"): brig is rebuilt in `libs/brig` from empty, and the old brig is read from git history, never kept beside the new one. This is the order's first step. bh-02 may be broken from here until its runner moves to the new API (TASK-0135 criterion 17).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Nothing of the old brig is left in libs/brig: its source, tests, SPEC.md, README.md, WORKFLOW.md, MILESTONES.md, pypeeker rules and scripts are deleted, in one commit
- [ ] #2 libs/brig is an empty package named brig (requires-python >=3.15, no dependencies, an empty src/brig/__init__.py and py.typed), so uv sync --all-packages still succeeds
- [ ] #3 The commit message names the commit the old brig is read from (d297a50) and that bh-02 is expected to be broken until its runner moves
<!-- AC:END -->
