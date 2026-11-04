---
id: DRAFT-0025
title: >-
  system and asides contributors must not need the event loop, and nothing
  checks it
status: Draft
assignee: []
created_date: '2026-11-04T13:22:00Z'
labels:
  - agent
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Split from TASK-0184 (2026-11-04). The prompt is read and asides asked on the executor thread, one call at a time, and must not need the event loop (bh-02/CLAUDE.md, the agent plugin's README); a contributor that awaits or schedules on the loop from there deadlocks or misbehaves, and nothing but prose stops one. A guard: a test that runs every shipped system and asides contributor on a thread with no running loop, or a pypeeker rule against asyncio in those contributors.
<!-- SECTION:DESCRIPTION:END -->
