---
id: TASK-0118
title: >-
  Drop a gate's index entries that are outside its src: this checkout's root
  gate carries 54 of brig's and pays 7 s a run
status: To Do
assignee: []
created_date: '2026-10-16 08:20'
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
Found by TASK-0111. scripts/arch-check indexes a path only when it holds a file with no index entry, and pypeeker's check refreshes entries it already has and drops those whose source file is gone, but nothing ever drops an entry whose file still exists and is no longer in the gate's src. This checkout's root index holds 278 entries and the root src has 224 files: the 54 extra are libs/brig/src, left from when brig was in the root gate's src before it kept a gate of its own.

Cost, measured: with those 54 entries removed (the .pypeeker copied aside, the libs/ entries deleted, put back afterwards and checked file by file) the root gate takes 98.9 s against 106.1 s in-process (median of 3), 6.8%: the refresh reads fewer files (3.7 s -> 3.0 s) and every symbol lookup and the call graph, which read all indexed files and not only src, see 24% fewer symbols (no-impure-functions 23.4 s -> 19.9 s). It is paid on every run, by any checkout whose src has ever shrunk or a member moved; a fresh checkout has none.

The rules' own corpus is cut to src, but find_symbol and call_graph read the whole store, so an orphan entry is also code the gate does not police that its sweeps still see.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/arch-check removes a gate's index entries whose source is not under any of that gate's src paths (a pure function decides which, in the style of without_index), and a test shows an entry outside src is dropped and an entry inside src is kept
- [ ] #2 On a checkout whose root index has entries outside src, the root gate's time before and after is recorded in the notes (106.1 s and 98.9 s in-process on this one)
<!-- AC:END -->
