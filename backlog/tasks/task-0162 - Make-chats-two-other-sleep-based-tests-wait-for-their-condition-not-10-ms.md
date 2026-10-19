---
id: TASK-0162
title: 'Make chat''s two other sleep-based tests wait for their condition, not 10 ms'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 20:33'
updated_date: '2026-10-19 00:17'
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
Round 2, review finding 1 only: close-task refuses a bug without a repro. No code or test file changes; the fix is one 'No repro:' note (the form board.py accepts), with the reason the repro cannot be committed (the skew plugin is a process-wide fault injector, lives in the scratchpad, and the fixed tests pass without it). Steps: (1) copy the pre-fix test_chat.py (c6ebc32^) into the scratchpad and run its two named tests with and without the skew plugin, to put real results in the note; (2) append the note, starting its line with 'No repro:'; (3) run board-check close TASK-0162 to see the gate passes, without closing; (4) squash to one commit from e08c2fd. Round 1's plan is in git history at e08c2fd. Proof: the two pre-fix runs and the board-check output, in the notes. Criteria 1 and 2 stay as ticked; no Done.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed (bh-02/plugins/chat-cordis-plugin/tests only). test_chat.py: test_the_stop_notice_carries_the_notes_rows_have_for_it waits (_until) for the reply to start (Endless now records that it started) and for the stop notes to be shown; test_what_a_command_holds_never_reaches_a_reply_already_running waits for the reply to start and, after the reply is released, for commands.ran == ['!pytest']. Its mid-reply check is an absence: no event shows a line was not run, so it gets one loop turn (asyncio.sleep(0), no clock) in place of a 10 ms sleep. The chat reads no line while a reply runs, so one turn is enough for a read during the reply to run the command. This is the one place criterion 1 is met by a yield instead of an event. test_chat_wiring.py: _until is copied in (importing test_chat's private name crosses test modules; a public helper would grow the shipped testing module for one caller). Its three asyncio.sleep(0.01) lines are changed: test_replacing_the_ui... waits for first.shown == ['to the first ']; test_what_a_command_left... waits for commands.ran == ['!git diff']; test_a_line_typed_during_a_restart... waits for /clear's note on screen before its first.seen == [] check. These three passed at HEAD under the 5 ms and 50 ms skew, so no failure was seen; they were changed because each was a fixed wait before a positive assertion. Two unnamed fixed sleeps in test_chat.py (test_a_command_running_when_the_person_leaves..., test_a_command_that_answers...) are filed as TASK-0168.
Evidence. Scratch plugin, outside the repo: /tmp/claude-0/-home-user/a0d5191d-f6a5-53e2-ae9a-0fb260cd6c48/scratchpad/skewclock.py patches asyncio's BaseEventLoop.time to add SKEW_MS (default 5) on every read. Before (HEAD), PYTHONPATH=<scratchpad> uv run pytest -p skewclock bh-02/plugins/chat-cordis-plugin/tests/test_chat.py -n auto --dist loadgroup: 2 failed, 10 passed. FAILED test_the_stop_notice_carries_the_notes_rows_have_for_it (test_chat.py:107, the stop was not yet shown) and test_what_a_command_holds_never_reaches_a_reply_already_running (test_chat.py:220, commands.ran == []). Serial at HEAD: the same two fail. After: the chat member's tests with SKEW_MS=5: 19 passed; with SKEW_MS=50: 19 passed; with no skew: 19 passed. The two test files with -n auto --dist loadgroup: 18 passed with skew 5, 18 passed without. scripts/check bh-02/plugins/chat-cordis-plugin: exit 0 (format 8 files, lint, types, tests 19 passed, gates (root, libs/brig, libs/cordis, libs/cordis-helpers, libs/host-paths), docs). ruff format --check and ruff check on the two files: clean. Not run: the full scripts/check (left for the reviewer). Not planted: a regression making the chat read lines during a reply, to see the absence guard fail.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 44%]
........................................................................ [ 46%]
.........................................................ss...ssss.s..ss [ 48%]
.s.....ssss.ss.s.s.s.s..s..s.ssss.s.........s........................... [ 50%]
........................................................................ [ 51%]
........................................................................ [ 53%]
......................ss.sssssssssssssssssssss.sssssssssssssssssssssssss [ 55%]
sssssssssssssssssss.............................ssssssssss...s.....s.... [ 57%]
........................................................................ [ 59%]
........................................................................ [ 60%]
......................................................................ss [ 62%]
s.................................................s..................... [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
..........................................................               [100%]
3902 passed, 118 skipped in 200.03s (0:03:20)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 4.41 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review: not closed. Full scripts/check exit 0 and both criteria are met on the evidence, but close-task refuses: a bug needs its repro recorded (record-check TASK-0162 --repro -- <test>) or a 'No repro:' note. The repro uses a scratch skew-clock plugin outside the repo, so the worker should record a No repro: note saying so (or commit the plugin as a fixture).

No repro: the failure needs the event loop's clock to run ahead of real time, as a stalled machine's does. The only thing in this work that does that is a scratch plugin kept outside the repo, /tmp/claude-0/-home-user/a0d5191d-f6a5-53e2-ae9a-0fb260cd6c48/scratchpad/skewclock.py (not committed). It patches asyncio's BaseEventLoop.time to add SKEW_MS (default 5) on every read, so it is a process-wide clock fault loaded with `-p skewclock`, not a test. The chat tests do not load it, and without it the pre-fix tests pass, so `record-check --repro -- <test>` would refuse the run as a repro that passed. A committed fixture would need a repro test that fails at the pre-fix code and is left unchanged by the fix; the fix edits test_chat.py, so the repro would have to be a new test file covering the same two behaviours. That is more than this fix, so the repro is the skewed run recorded below. Limit: nothing in the suite guards these two waits, so a return to a fixed sleep passes unless the run is under the plugin.

Round 2 re-run, to check the claims above: the pre-fix test_chat.py (git show c6ebc32^:bh-02/plugins/chat-cordis-plugin/tests/test_chat.py, copied to /tmp/claude-0/-home-user/a0d5191d-f6a5-53e2-ae9a-0fb260cd6c48/scratchpad/repro/test_chat_prefix.py), its two named tests (-k "stop_notice_carries_the_notes or what_a_command_holds_never"), from /home/user/bh-02 with uv run pytest -q -o asyncio_mode=auto -p no:cacheprovider:
- with the plugin (PYTHONPATH=/tmp/claude-0/-home-user/a0d5191d-f6a5-53e2-ae9a-0fb260cd6c48/scratchpad/repro, -p skewclock): 2 failed, exit 1: test_chat_prefix.py:107 (the stop notice not yet shown) and :220 (commands.ran == []).
- without the plugin: 2 passed, exit 0.
No code or test file changed in this round.

Round 2 close gate: board-check close TASK-0162 printed 'ok: TASK-0162 can close' and exited 0 (run before the task was closed; the task is still In Progress, close-task was not run, the reviewer closes it). Changed in round 2: this task's notes and its implementation plan only. Commits from the backlog CLI for those edits are squashed into one commit on top of e08c2fd.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 44%]
........................................................................ [ 46%]
.......................................................s.ss...ssss.s.s.. [ 48%]
..ss..ss...s.s.s.s..ss.s.s..ssssss..............s....................... [ 50%]
........................................................................ [ 51%]
........................................................................ [ 53%]
........................ssssssssssssssssssssssssssssssssssssssssssssssss [ 55%]
sssssssssssssssssss..............................sssssssss..s....s...... [ 57%]
.s........................................................s............. [ 59%]
........................................................................ [ 60%]
......................................................................ss [ 62%]
s....................................................................... [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
..........................................................               [100%]
3902 passed, 118 skipped in 193.93s (0:03:13)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 3.92 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
