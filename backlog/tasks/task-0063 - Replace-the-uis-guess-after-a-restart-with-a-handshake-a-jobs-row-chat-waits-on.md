---
id: TASK-0063
title: >-
  Replace the ui's guess after a restart with a handshake: a jobs row chat waits
  on
status: Done
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 19:40'
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
- [x] #1 Every path that holds or sends a typed line during a restart is traced first and written in this task's notes (the bridge's hold, the composer, the approval modal, Ctrl-C, a command typed while held)
- [x] #2 A `jobs` row (a capability) runs the restarts commands queue, one at a time, reports a failure through `output.notice`, and tells whether any is pending; the operator and the conversation row queue through it instead of a `perform` each
- [x] #3 `chat:session` waits on it before sending a line to the loop, so a line typed during a restart reaches the new loop, never the old, and none is dropped
- [x] #4 The `restarting` event's hold, `_LAPSE` and `frame.Held` are deleted, and CONTRACTS.md no longer documents the `/restart ROW` gap
- [x] #5 A test types a line during each of `/clear`, `/compact`, `/model NAME` and `/restart loop` and sees it answered by the new loop
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Traced first (before the change), every path that holds or sends a typed line during a restart:
1. The composer (App.send): a line is drawn at once (or under a streaming reply, at its end), then Bridge.submit hands it to the oldest waiting reader, else keeps it; when kept and `waiting_on` names rows, a note says it waits for them.
2. The bridge's hold: a command's answer ended with `restarting` (/clear, /compact, /model NAME), which TuiOutput.show handed to Bridge.announce; from then until those rows were `active` (frame.Held, through the `inactive` inside a restart) submit kept every line even with a reader there, and line() kept even a kept line back; a row announced that never began lapsed after _LAPSE (2 s). /restart ROW and /model to the current model announced nothing, so a line typed right after /restart loop went to the old chat row's read and could start a turn the restart stopped.
3. The chat row (converse): reads a line, runs a command until it answers (cancelled if the input closes), or runs a turn until it ends or Ctrl-C; a restart of the loop reloads it, cancelling whatever it was doing.
4. The approval modal: a question queues and shows a modal; the composer is under it, so a line can't be typed until it is answered; Ctrl-C withdraws or declines open questions.
5. Ctrl-C: a turn listening is interrupted; with a line handed out and no turn listening (a turn starting, or a command running) one Ctrl-C is held for the next interrupted() and dropped at the next read, and a moment later the app says a command is running.
6. A command typed while held: kept like any line, so it ran on the new rows once the hold let go.
7. `cleared`: the transcript drops the old conversation but draws again the kept lines not yet read.
8. The app ending: Bridge.end settles readers with None, interrupts, answers questions no.

What changed: commands:jobs binds `jobs` (Jobs: put(job, failed), pending(), settled()), its worker cordis-helpers' perform over the value's queue; each job reports its own failure through output.notice worded by the command (failed(why)). The operator (/restart), the conversation row (/clear, /compact) and the switch row (/model NAME) queue there instead of a perform each, and no longer need output for it. chat:session depends on `jobs` and awaits settled() before every read, so the restart reloads it while it waits with no line in hand; a line typed meanwhile stays in the bridge and the new row reads it. The bridge no longer holds anything: Held, held_after, holding, _LAPSE and the lapse timer are gone; `restarting` stays as information (now /restart sends it too), and the bridge keeps the announced rows until the next read only to name them in the waiting note. update-layer adds a jobs row to a layer that fills chat:session or commands:operator itself. Tests: the jobs value (order, a failure told, settled), the chat row (a line typed during a restart reaches the new loop; fails without the wait), and a real launch typing a line in the same burst as /compact and as /restart loop (fails 3 of 3 without the wait); the existing real-launch tests cover /clear and /model NAME.
<!-- SECTION:NOTES:END -->
