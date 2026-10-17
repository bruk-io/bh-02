---
id: TASK-0132
title: >-
  Save and delete auto memories under a lock, so two sessions never lose a
  MEMORY.md line
status: To Do
assignee: []
created_date: '2026-10-17 14:00'
labels:
  - memory
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0068 (2026-10-17). The memory tool's save and delete read MEMORY.md, change their own line and write it back by a temporary file renamed over it (memory_cordis_plugin/directory.py, host_paths.write_beneath). The rename keeps a reader from seeing a torn file, but two sessions on one project (or two worktrees) saving at once both read the old index, and the last rename wins: the other's line is lost until that memory is saved again. Owner, 2026-10-17: use the platform's file lock. flock is advisory, which is enough here since every writer that matters is bh-02's own tool (a write the model makes through Python is not checked, the owner's earlier call). Lock the memory directory, opened through no link with host_paths.directory_beneath, not MEMORY.md, which the rename replaces; the lock goes with the descriptor, so a crashed session holds nothing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A save and a delete hold an exclusive flock on the memory directory (opened through no link) for the whole read, change and write of MEMORY.md
- [ ] #2 Two saves of different memories started at once, from two processes, both have their line in MEMORY.md afterwards; the test is seen failing without the lock
<!-- AC:END -->
