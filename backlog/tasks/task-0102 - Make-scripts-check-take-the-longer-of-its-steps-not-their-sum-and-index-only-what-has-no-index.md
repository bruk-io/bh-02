---
id: TASK-0102
title: >-
  Make scripts/check take the longer of its steps, not their sum, and index only
  what has no index
status: To Do
assignee: []
created_date: '2026-10-15 02:28'
labels:
  - scripts
  - gates
  - size-2
dependencies: []
priority: high
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-15). Measured 2026-10-14 on this machine (4 cores): a full scripts/check is about 640 s, all sequential: tests 433 s, gates 204 s, format, lint, types and docs under 3 s together. The gates are about 89 s of 37 separate 'uv run pypeeker index' calls (one per source path: 29 at the root, 2 per library) and about 117 s of the root gate's 'check --strict', most of it a pypeeker bug fixed upstream (the impurity sweep rebuilt the call graph per function; symbol lookups re-listed the index): bump the pin to the merged fix. pypeeker's check already re-indexes stale entries itself, so arch-check needs to index only a path with no index yet (a new member); scripts/arch-check's comment says why indexing exists (check against a missing index passes silently), which must stay true. The gates share nothing with the tests, so scripts/check can run them side by side.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The root pyproject pins pypeeker to the merged commit that caches the call graph and the indexed-file list; uv.lock regenerated with uv
- [ ] #2 scripts/arch-check indexes only paths that have no index (still failing on any indexing error), so a new member is still indexed before check; a test or a recorded run with a new empty member shows it
- [ ] #3 scripts/check runs the gates (and docs) at the same time as the tests and reports each step's result as now, exit code non-zero if any failed
- [ ] #4 A full scripts/check's wall time before and after is recorded in the notes, with each step's time; scripts/check passes
<!-- AC:END -->
