---
id: DRAFT-0024
title: approval honours runs=memory and runs=harness from any row
status: Draft
assignee: []
created_date: '2026-11-04T13:22:00Z'
labels:
  - runner
  - approval
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Split from TASK-0184 (2026-11-04). runner_cordis_plugin/approval.py lets a call whose question says runs='memory' through unasked, jailed or not, and asks runs='harness' as a jailed call, whichever row asked. bh-02/CLAUDE.md says only the memory tool (memory:auto's) takes runs='memory', in a layer's row, and a new tool never takes the value for convenience; that holds by convention only. A guard: a pypeeker rule restricting the literals to the memory and subagents plugins, or approval checking which row registered the tool.
<!-- SECTION:DESCRIPTION:END -->
