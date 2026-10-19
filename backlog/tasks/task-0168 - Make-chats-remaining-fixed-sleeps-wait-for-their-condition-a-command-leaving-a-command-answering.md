---
id: TASK-0168
title: >-
  Make chat's remaining fixed sleeps wait for their condition (a command
  leaving, a command answering)
status: To Do
assignee: []
created_date: '2026-10-19 00:06'
labels:
  - chat
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while doing TASK-0162. In bh-02/plugins/chat-cordis-plugin/tests/test_chat.py, two tests still use asyncio.sleep(0.01) where they need an event: test_a_command_running_when_the_person_leaves_is_cancelled_and_the_chat_ends (sleep after the interrupt, then asserts the command has not been cancelled) and test_a_command_that_answers_runs_to_its_end_and_its_answer_is_shown (sleeps before the interrupt and before the command is released). Both pass with the loop clock 5 ms ahead on every read (the scratch plugin used under TASK-0162), so they are not failing yet; they carry the same fixed wait that failed the two tests TASK-0162 fixed. The _until helper in test_chat.py (copied into test_chat_wiring.py by TASK-0162) serves them. The negative (the command is not cancelled by Ctrl-C) has no event to wait for: name the one that must come first, or give it one loop turn as TASK-0162 did for test_what_a_command_holds_never_reaches_a_reply_already_running.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the two tests waits (bounded) for its event instead of a fixed 10 ms sleep, or says in a comment why an absence gets a loop turn instead
- [ ] #2 Both pass under the loop clock 5 ms ahead on every read and under pytest -n auto --dist loadgroup
<!-- AC:END -->
