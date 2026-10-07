---
id: TASK-0050
title: Don't let repeated Ctrl-C pile up prompt-reading threads
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
labels:
  - agent
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop reads the prompt and runs memory functions with asyncio.to_thread. A stopped reply leaves its thread running to the end, so stopping replies repeatedly while a slow prompt is read can queue several readings in the default executor and delay shutdown.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Stopping replies repeatedly during a slow prompt reading leaves at most one reading in flight
- [ ] #2 Shutdown is not delayed by a reading a stopped reply left behind
- [ ] #3 A test reproduces the pile-up before the fix
<!-- AC:END -->
