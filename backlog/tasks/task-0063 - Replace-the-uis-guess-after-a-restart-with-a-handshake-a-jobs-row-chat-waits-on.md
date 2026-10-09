---
id: TASK-0063
title: >-
  Replace the ui's guess after a restart with a handshake: a jobs row chat waits
  on
status: To Do
assignee: []
created_date: '2026-10-09 03:08'
labels:
  - commands
  - chat
  - tui
dependencies: []
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After a command restarts rows, the ui guesses which typed lines to hold back: the command's answer ends with a `restarting` event naming the rows, and the tui's bridge holds every line until they are up, or until `_LAPSE` (2 seconds) passes with none begun (`tui_cordis_plugin.ports`, `frame.Held`). `/restart ROW` and `/model` to the model already chosen announce nothing, so a line typed right after `/restart loop` can still start a turn the restart stops (CONTRACTS.md documents the gap). The restarts themselves run in a queue each command row keeps of its own (`cordis_helpers.perform` in the operator and in `/compact`). One row that queues every restart and says when the queue is empty would let `chat:session` wait on it before a line goes to the loop, and the ui's guess, its timer and the gap would go. Worth doing only after tracing every ui path that holds a line today. Found by the review against cordis of 2026-10-09 (the separation, duplicates and docs review).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every path that holds or sends a typed line during a restart is traced first and written in this task's notes (the bridge's hold, the composer, the approval modal, Ctrl-C, a command typed while held)
- [ ] #2 A `jobs` row (a capability) runs the restarts commands queue, one at a time, reports a failure through `output.notice`, and tells whether any is pending; the operator and the conversation row queue through it instead of a `perform` each
- [ ] #3 `chat:session` waits on it before sending a line to the loop, so a line typed during a restart reaches the new loop, never the old, and none is dropped
- [ ] #4 The `restarting` event's hold, `_LAPSE` and `frame.Held` are deleted, and CONTRACTS.md no longer documents the `/restart ROW` gap
- [ ] #5 A test types a line during each of `/clear`, `/compact`, `/model NAME` and `/restart loop` and sees it answered by the new loop
<!-- AC:END -->
