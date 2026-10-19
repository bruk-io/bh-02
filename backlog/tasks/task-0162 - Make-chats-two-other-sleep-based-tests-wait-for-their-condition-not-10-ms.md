---
id: TASK-0162
title: 'Make chat''s two other sleep-based tests wait for their condition, not 10 ms'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 20:33'
updated_date: '2026-10-19 00:06'
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
- [x] #1 Both tests wait (bounded) for the event they assert on instead of a fixed sleep
- [x] #2 They pass with the loop clock running ahead of real time, where they failed before, and pass under pytest -n auto --dist loadgroup
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Baseline (done): scratch plugin at /tmp/claude-0/-home-user/a0d5191d-f6a5-53e2-ae9a-0fb260cd6c48/scratchpad/skewclock.py (not in the repo) patches BaseEventLoop.time to add 5 ms on every read. At HEAD under it, test_the_stop_notice... fails at line 107 and test_what_a_command_holds... at line 220; the 17 other chat tests pass, including all of test_chat_wiring.py (also at 50 ms).
2. test_chat.py: _until (already there) waits for: the reply running (Endless records that it started) and the stop notice (the note as the last event) in test_the_stop_notice...; the reply running (model.seen) and commands.ran == ["!pytest"] after go is set in test_what_a_command_holds.... The one mid-reply check is an absence (no command runs during a reply): no event can be waited for, so it gets one loop turn (sleep(0), which uses no clock) instead of a timed sleep; a line read during the reply would run within that turn.
3. test_chat_wiring.py: the three asyncio.sleep(0.01) lines. Lines ~57 and ~90 precede a positive assertion: wait on that value. Line ~161 precedes an absence (first.seen == []) that is only meaningful after /clear's answer is shown; wait for that note on screen, then check. _until is copied into this module: importing it from test_chat would reach a private name of another test module, and a public helper would grow the shipped testing module for one caller.
4. Left alone: test_chat.py sleeps in test_a_command_running_when_the_person_leaves... and test_a_command_that_answers... are outside the named scope; they pass under the skew. Filed as a follow-up task if still unfixed.
Proof: each named test seen failing at HEAD under SKEW_MS=5 (done), passing after; the whole file passing under SKEW_MS=5 and 50; then no skew; then -n auto --dist loadgroup; then ruff format/check, mypy on the file, scripts/check chat-cordis-plugin (once, first run with gates and docs). Not run: full scripts/check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed (bh-02/plugins/chat-cordis-plugin/tests only). test_chat.py: test_the_stop_notice_carries_the_notes_rows_have_for_it waits (_until) for the reply to start (Endless now records that it started) and for the stop notes to be shown; test_what_a_command_holds_never_reaches_a_reply_already_running waits for the reply to start and, after the reply is released, for commands.ran == ['!pytest']. Its mid-reply check is an absence: no event shows a line was not run, so it gets one loop turn (asyncio.sleep(0), no clock) in place of a 10 ms sleep. The chat reads no line while a reply runs, so one turn is enough for a read during the reply to run the command. This is the one place criterion 1 is met by a yield instead of an event. test_chat_wiring.py: _until is copied in (importing test_chat's private name crosses test modules; a public helper would grow the shipped testing module for one caller). Its three asyncio.sleep(0.01) lines are changed: test_replacing_the_ui... waits for first.shown == ['to the first ']; test_what_a_command_left... waits for commands.ran == ['!git diff']; test_a_line_typed_during_a_restart... waits for /clear's note on screen before its first.seen == [] check. These three passed at HEAD under the 5 ms and 50 ms skew, so no failure was seen; they were changed because each was a fixed wait before a positive assertion. Two unnamed fixed sleeps in test_chat.py (test_a_command_running_when_the_person_leaves..., test_a_command_that_answers...) are filed as TASK-0168.
Evidence. Scratch plugin, outside the repo: /tmp/claude-0/-home-user/a0d5191d-f6a5-53e2-ae9a-0fb260cd6c48/scratchpad/skewclock.py patches asyncio's BaseEventLoop.time to add SKEW_MS (default 5) on every read. Before (HEAD), PYTHONPATH=<scratchpad> uv run pytest -p skewclock bh-02/plugins/chat-cordis-plugin/tests/test_chat.py -n auto --dist loadgroup: 2 failed, 10 passed. FAILED test_the_stop_notice_carries_the_notes_rows_have_for_it (test_chat.py:107, the stop was not yet shown) and test_what_a_command_holds_never_reaches_a_reply_already_running (test_chat.py:220, commands.ran == []). Serial at HEAD: the same two fail. After: the chat member's tests with SKEW_MS=5: 19 passed; with SKEW_MS=50: 19 passed; with no skew: 19 passed. The two test files with -n auto --dist loadgroup: 18 passed with skew 5, 18 passed without. scripts/check bh-02/plugins/chat-cordis-plugin: exit 0 (format 8 files, lint, types, tests 19 passed, gates (root, libs/brig, libs/cordis, libs/cordis-helpers, libs/host-paths), docs). ruff format --check and ruff check on the two files: clean. Not run: the full scripts/check (left for the reviewer). Not planted: a regression making the chat read lines during a reply, to see the absence guard fail.
<!-- SECTION:NOTES:END -->
