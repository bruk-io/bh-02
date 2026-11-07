---
id: TASK-0209
title: >-
  On darwin a tree renamed onto an absent pin, or a write root renamed into
  another, carries files past a carve-out
status: To Do
assignee: []
created_date: '2026-11-07 19:34'
labels:
  - security
  - brig
  - darwin
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0197 (decision-207), measured with sandbox-exec on macOS 27.0.1 under brig's profile shape. Seatbelt judges a rename by its source and destination paths only. decision-207 pins each EXISTING directory between a write root and a carve-out (file-write-unlink on its literal path), which refuses renaming it away or over it. Two shapes stay open: (1) a directory between a root and a carve-out that is ABSENT (bh-02 run from a home with no ~/.config: ~/.config/bh-02 is a trusted carve-out) - a workload makes x/bh-02/startup.py and renames x onto ~/.config, planting a file at the carve-out's path; a rename's destination is checked as file-write-create, which a pin cannot deny without refusing mkdir there. On Linux the runner holds the topmost absent ancestor; on darwin nothing does. (2) A write root renamed whole into another write root (the project into the jail's scratch), edited there and renamed back: no pin lies between root and carve-out for it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each shape is reproduced by a test on darwin that fails before the fix and is seen failing with the fix removed
- [ ] #2 On darwin neither shape lets a jailed input put a file at a write_denies path; brig's SPEC.md rules the remedy (decision-N)
- [ ] #3 Linux unchanged: scripts/linux-jail-check passes
<!-- AC:END -->
