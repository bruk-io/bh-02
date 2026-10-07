---
id: TASK-0050
title: Don't let repeated Ctrl-C pile up prompt-reading threads
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 13:18'
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
- [x] #1 Stopping replies repeatedly during a slow prompt reading leaves at most one reading in flight
- [x] #2 Shutdown is not delayed by a reading a stopped reply left behind
- [x] #3 A test reproduces the pile-up before the fix
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Prompt readings and memory calls run one at a time on a daemon thread from agent:executor, a row that depends on nothing, so stopping reply after reply (with /clear or /model between) leaves at most one in flight, and a reading left running never delays exit. A failed reading left behind logs nothing. The boot test saw four readings at once before (4, 4, 4) and one after (1, 1, 1).
<!-- SECTION:FINAL_SUMMARY:END -->
