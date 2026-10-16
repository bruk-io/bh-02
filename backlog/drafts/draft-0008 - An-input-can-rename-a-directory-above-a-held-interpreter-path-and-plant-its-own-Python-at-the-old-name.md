---
id: DRAFT-0008
title: >-
  An input can rename a directory above a held interpreter path and plant its
  own Python at the old name
status: Draft
assignee: []
created_date: '2026-10-16 23:20'
labels:
  - runner
  - security
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0127 (not probed: the reviewer may not run bwrap plants). The Linux jail holds the interpreter's file (TASK-0126) and each link's directory (TASK-0127) by mounts, but rename(2) refuses only a dentry that is itself a mount point; an ancestor of one can be renamed and its mounts move with it. With the project at the home directory, an input could mv ~/.local/share/uv aside and build ~/.local/share/uv/python/cpython-3.15-<platform>/bin/python3.15 of its own; the next uv run on the host runs it. Same for every directory between a writable root and a deny.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 In a real bwrap jail with the project at the home layout, an input cannot rename any directory on the way from a writable root to bh-02's interpreter, and a test plants it, seen failing first
<!-- AC:END -->
