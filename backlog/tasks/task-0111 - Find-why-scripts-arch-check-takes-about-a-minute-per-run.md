---
id: TASK-0111
title: Find why scripts/arch-check takes about a minute per run
status: To Do
assignee: []
created_date: '2026-10-16 05:01'
labels:
  - gates
  - size-2
dependencies: []
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Measured 2026-10-16 from this session's subagent transcripts: 234 scripts/arch-check runs took 158.6 minutes in all (41 s on average), 23% of every tool call's time; TASK-0108's worker ran it 5 times for 5.4 minutes (about 65 s each). scripts/check runs the gates too, so the cost is paid again in every member and full check. Find where the time goes before changing anything: writing each gate's src, indexing, the index refresh of changed files, each gate's check --strict, or the per-library gates.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The time of each phase of scripts/arch-check (writing src, indexing, refreshing, each gate's check) is measured warm and cold on this repository and recorded in the notes
- [ ] #2 The phase or phases that take most of the time are named with why, and each change that would cut it is proposed with its measured saving, filed as its own task when it is more than a one-line change
<!-- AC:END -->
