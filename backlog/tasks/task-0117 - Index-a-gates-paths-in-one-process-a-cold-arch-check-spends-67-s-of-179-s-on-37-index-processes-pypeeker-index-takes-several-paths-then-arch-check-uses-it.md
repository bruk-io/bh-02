---
id: TASK-0117
title: >-
  Index a gate's paths in one process: a cold arch-check spends 67 s of 179 s on
  37 index processes (pypeeker index takes several paths, then arch-check uses
  it)
status: To Do
assignee: []
created_date: '2026-10-16 08:20'
labels:
  - gates
  - scripts
  - size-2
dependencies: []
priority: high
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. A fresh checkout or worktree has no .pypeeker (it is git-ignored), so scripts/arch-check indexes every path first. Cold, scripts/arch-check --no-fix takes 178.9 s here against 115.6 s warm, and 67.0 s of it is indexing: 61.7 s for the root gate's 29 paths (224 files), 3.2 s for brig, 0.9 s for cordis, 0.6 s each for cordis-helpers and host-paths.

Why: arch-check runs one pypeeker index PATH process per path, and each process reconciles the cross-file symbol tree before it exits (indexer.index_path with a tree store, then treebuild.load_or_rebuild), which deserialises every index entry written so far, since the process has no cache from the last one. The calls take longer as the index grows, from 0.7 s for the first root path to 3.8 s for the last: the cost grows with paths times files.

Measured saving: one process that indexes the same 29 paths with index_path (no tree store) and then reconciles the tree once took 4.1 s (4.09, 4.08, 4.18) against 60.5 s for the per-path processes in the same scratch copy (59.9, 60.5, 61.2), and the resulting .pypeeker (every index entry and tree.json) is identical, file for file (diff -r). Saving on a cold run: about 56 s for the root gate, the largest of the five.

TASK-0102 rejected calling pypeeker's Python API from the script (it couples a script to pre-1.0 internals), so the change is upstream: pypeeker index takes several paths (one reconcile at the end), and arch-check passes it every path of a gate that has no index entry in one call. A script-only way that needs no upstream change is not known; if there is one, say so here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pypeeker (upstream) indexes several paths in one call and reconciles the tree once, and the root pin names the merged commit, uv.lock regenerated with uv
- [ ] #2 scripts/arch-check indexes the paths of a gate that have no index entry in one call per gate, still failing on any indexing error; the index it writes cold is identical to the one the per-path calls wrote, and a cold run's indexing time is recorded in the notes (67.0 s before; 61.7 s of it the root gate)
<!-- AC:END -->
