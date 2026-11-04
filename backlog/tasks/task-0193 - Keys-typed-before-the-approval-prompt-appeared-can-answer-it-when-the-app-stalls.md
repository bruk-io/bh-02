---
id: TASK-0193
title: >-
  Keys typed before the approval prompt appeared can answer it when the app
  stalls
status: To Do
assignee: []
created_date: '2026-11-04T16:59:00Z'
labels:
  - tui
  - approval
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0191's worker, 2026-11-04 (test_keys_typed_as_the_modal_comes_up_do_not_answer_it failed 3 of 8 runs under 12 CPU burners). The tui's ApprovalScreen arms on a 0.4 s wall-clock timer from mount, and its y/n/Escape bindings are judged when the key is processed, not when it was typed. When the app stalls, the grace timer can expire while keys typed before the modal came up are still queued, and they then answer it: a stray y typed ahead can approve a call the person never saw. The grace period exists to stop exactly that. Fix: judge each key by when it arrived (Textual's key event time, or a stamp taken where keys are read), against when the modal became visible.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A key that arrived before the approval modal was visible plus its grace period never answers it, however late it is processed; a test that holds the event loop while keys are queued, then releases it, shows the modal unanswered; repro recorded failing before the fix
- [ ] #2 A key that arrived after the grace period still answers at once
- [ ] #3 test_keys_typed_as_the_modal_comes_up_do_not_answer_it passes 50 of 50 under the load that failed it (12 CPU burners)
<!-- AC:END -->
