---
id: TASK-0162
title: 'Make chat''s two other sleep-based tests wait for their condition, not 10 ms'
status: To Do
assignee: []
created_date: '2026-10-18 20:33'
labels:
  - chat
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found fixing DRAFT-0008 under TASK-0148. With an event loop whose clock runs 5 ms ahead on every read (a scratch pytest plugin, as a stalled machine does), two more chat tests fail the way test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on did: bh-02/plugins/chat-cordis-plugin/tests/test_chat.py::test_the_stop_notice_carries_the_notes_rows_have_for_it (sleep, interrupt, sleep, then reads screen.events) and ::test_what_a_command_holds_never_reaches_a_reply_already_running (sleeps before asserting model.seen and commands.ran). They pass alone and will fail scripts/check under -n auto on a busy machine. TASK-0148 fixed the first test with an _until(condition) helper in test_chat.py; the same helper serves these. test_chat_wiring.py also has asyncio.sleep(0.01) lines to check.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Both tests wait (bounded) for the event they assert on instead of a fixed sleep
- [ ] #2 They pass with the loop clock running ahead of real time, where they failed before, and pass under pytest -n auto --dist loadgroup
<!-- AC:END -->
