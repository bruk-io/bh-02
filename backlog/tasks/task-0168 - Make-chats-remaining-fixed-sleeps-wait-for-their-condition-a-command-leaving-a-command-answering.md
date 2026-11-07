---
id: TASK-0168
title: >-
  Make chat's remaining fixed sleeps wait for their condition (a command
  leaving, a command answering)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-19 00:06'
updated_date: '2026-11-07 07:04'
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
- [x] #1 Each of the two tests waits (bounded) for its event instead of a fixed 10 ms sleep, or says in a comment why an absence gets a loop turn instead
- [x] #2 Both pass under the loop clock 5 ms ahead on every read and under pytest -n auto --dist loadgroup
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) Read chat.py/testing.py to confirm: in both tests the fixed sleep follows typed.interrupt() while a *command* (not a reply) runs via _unless_closed, which never reads input.interrupted(); so Ctrl-C has no observable effect there -- same 'absence, no event' shape TASK-0162 handled with a bare asyncio.sleep(0) + comment for test_what_a_command_holds_never_reaches_a_reply_already_running.
2) test_a_command_running_when_the_person_leaves_is_cancelled_and_the_chat_ends: keep the existing wait for commands.started (already an event, already bounded) before interrupt(); replace the lone sleep(0.01) after interrupt() with asyncio.sleep(0) plus a comment naming why there is no event to wait for.
3) test_a_command_that_answers_runs_to_its_end_and_its_answer_is_shown: the first sleep(0.01) (before interrupt) waits for Slow.run to have started waiting on go -- give Slow its own asyncio.Event (self.started), set at the top of run(), and wait on it instead of sleeping. The second sleep(0.01) (before commands.go.set()) is the same absence as step 2: replace with asyncio.sleep(0) + comment.
4) Run the two tests directly, then with a scratch pytest plugin that skews BaseEventLoop.time forward 5ms per read (recreating TASK-0162's repro) to prove they still pass, then the member's test suite under -n 8 --dist loadgroup, then scripts/check for the member (through testlock).
5) Tick AC1/AC2 with the command output as evidence; append notes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: bh-02/plugins/chat-cordis-plugin/tests/test_chat.py only.

test_a_command_running_when_the_person_leaves_is_cancelled_and_the_chat_ends: the sleep(0.01) after typed.interrupt() replaced with asyncio.sleep(0) plus a comment naming why there is no event to wait for: a running command is raced only against input.closed() in _unless_closed, never input.interrupted(), so nothing ever wakes to read the interrupt.

test_a_command_that_answers_runs_to_its_end_and_its_answer_is_shown: gave the local Slow fake its own asyncio.Event (self.started), set at the top of run() before awaiting go; the first sleep(0.01) (before interrupt) replaced with await asyncio.wait_for(commands.started.wait(), 1). The second sleep(0.01) (before commands.go.set()) is the same absence as the first test (interrupt has no waiter while a command runs): replaced with asyncio.sleep(0) and the same comment.

Evidence per criterion.
AC1: both tests now wait on a real event (commands.started) or say in a comment why an absence gets one loop turn instead of a fixed sleep (no second event remains unexplained).
AC2: built a local, uncommitted pytest plugin recreating TASK-0162's repro (scratchpad skewplugin/skewclock.py: patches asyncio.BaseEventLoop.time to add SKEW_MS on every read). Planted check: ran the PRE-FIX test file (git checkout HEAD -- test_chat.py) under the plugin at 5ms and 50ms skew -- both tests passed (2 passed in 0.11s / 0.10s each run): confirms the task text's own claim that they are not failing yet, so this is a consistency fix to the fixed-wait shape, not a flake fix; no new repro test was added (TASK-0162 ruled that out of scope for the same reason: a repro would need a new test file covering the same two behaviours, which is more than this fix). Then restored the fix and reran: whole test_chat.py (12 tests) under -p skewclock at 5ms and 50ms: 12 passed each time. Full member suite under 'uv run pytest bh-02/plugins/chat-cordis-plugin -q -n 8 --dist loadgroup' (machine rules cap -n at 8, so this stands in for the AC's -n auto): 19 passed. scripts/check bh-02/plugins/chat-cordis-plugin: exit 0 (format, lint, mypy, 19 tests, every gate, docs all ok). All runs went through the machine's testlock. No scripts/arch-check run: nothing outside this one member changed.

Not verified: the full repo-wide scripts/check (left for the reviewer, per standing rules).

Noted but out of scope (not filed as a task, no action needed): because nothing consumes interrupted() while a command runs, Typed._interrupt stays set into whatever reply follows in these two tests; it doesn't affect any assertion here (Echo's reply doesn't suspend) and may be an artifact of the Typed test fake rather than the real input row — flagging only, not chasing it under this task.

Check `scripts/check` exited 1

(122 earlier lines omitted)
```text
>       assert [s.rsplit("\n", 1)[-1] for s in said] == ["DENIED"] * len(inputs), said
E       AssertionError: ['(/private/var/folders/rf/f34xmczn4659gm98hrsprydc0000gn/T/pytest-of-brukhabtu/pytest-978/popen-gw0/test_a_session_ru...me/xdg/bh-02/startup.py ran first: no public functions)
E         DENIED', 'DENIED', 'DENIED', 'DENIED', 'DENIED', 'WROTE', ...]
E       assert ['DENIED', 'D... 'WROTE', ...] == ['DENIED', 'D...'DENIED', ...]
E         
E         At index 5 diff: 'WROTE' != 'DENIED'
E         Use -v to get more diff

bh-02/app/tests/test_python_repl.py:980: AssertionError
_____________ test_a_listener_that_left_after_listening_is_refused _____________
[gw2] darwin -- Python 3.15.0 /Users/brukhabtu/Documents/src/github.com/bruk-io/bh-02/.venv/bin/python

run_id = '2a8d334ea14840c7a91c02f3034f2e41'
jail_dir = '/private/tmp/bg-uz0kq6b2'

    @pytest.mark.integration
    def test_a_listener_that_left_after_listening_is_refused(run_id: str, jail_dir: str) -> None:
        """The kernel names the process that called `listen`; one that has since
        exited is no vouching peer, even when the socket's holder is in the
        group (the safe direction for a daemon that forks after `listen`)."""
        jail = _create(jail_dir, confined=False)
        reservation = jail.channel("ctl")
        left = os.path.join(jail_dir, "own", "left")
        body = f"python3 -c '{_FORK_AFTER_LISTEN}' {reservation.bound_path} {left}; sleep 60"
        process = jail.start(workload_argv(run_id, body), channel=reservation)
        try:
            deadline = time.monotonic() + _READY_S
            while not os.path.exists(left):
                assert time.monotonic() < deadline, "the listener never left"
                time.sleep(0.02)
>           with pytest.raises(EndpointRefused, match="has left"):
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E           Failed: DID NOT RAISE EndpointRefused

libs/brig/tests/integration/test_channel_planted_link.py:271: Failed
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_python_repl.py::test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s@jail-lock
FAILED libs/brig/tests/integration/test_channel_planted_link.py::test_a_listener_that_left_after_listening_is_refused
2 failed, 3851 passed, 231 skipped in 70.81s (0:01:10)
   FAILED: tests
== gates
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
INFO    -  Building documentation to directory: /Users/brukhabtu/src/github.com/bruk-io/bh-02/site
INFO    -  Documentation built in 1.28 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```
<!-- SECTION:NOTES:END -->
