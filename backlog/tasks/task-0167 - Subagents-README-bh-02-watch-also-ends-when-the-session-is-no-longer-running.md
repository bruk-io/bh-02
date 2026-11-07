---
id: TASK-0167
title: 'Subagents README: bh-02 watch also ends when the session is no longer running'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 23:55'
updated_date: '2026-11-07 07:09'
labels:
  - subagents
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The subagents README's 'Watching a child' bullet (around line 235) says bh-02 watch follows a log 'until agent_end'. TASK-0161 made the follow also end, saying so, once the session is no longer running (the pid in running.lock is gone); docs/bh-02/reference/command-line.md says that, the README does not. Found while doing TASK-0163, which is about the log-stopped note's Ctrl-C wording only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The subagents README's watch bullet names both ends: agent_end, and the session no longer running (saying so), as docs/bh-02/reference/command-line.md does
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Edit the subagents README's 'Watching a child' bullet for bh-02 watch to name both ends (agent_end, and session no longer running per running.lock), matching docs/bh-02/reference/command-line.md wording. Doc-only change; no tests needed beyond grep verification. Then tick AC1 with evidence.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Edited bh-02/plugins/subagents-cordis-plugin/README.md's Watching a child section, bh-02 watch bullet: changed 'follows it until agent_end (--once stops...)' to 'follows it until agent_end, or until the session is no longer running (the pid in its running.lock is gone), saying so (--once stops...)', matching docs/bh-02/reference/command-line.md's wording for the same ending. Verified with sed -n 236,238p on the README showing the new text naming both ends.

Ran scripts/check bh-02/plugins/subagents-cordis-plugin through the machine's testlock (gates: root, libs/brig, libs/cordis, libs/cordis-helpers, libs/host-paths, docs all ok; tokens skipped, no bh-01 dist beside this repo). Test step: 6 failed, 131 passed, 1 skipped, all 6 failures in test_agents_wiring.py (test_retiring_a_child_while_it_replies_ends_the_call_with_no_report, test_unloading_the_agents_row_retires_every_child_it_holds, test_ctrl_c_stops_the_parent_s_reply_and_the_child_it_waits_on_from_the_tool, test_ctrl_c_stops_the_child_a_python_input_waits_on, test_agent_stop_ends_the_child_and_its_python_program, test_release_stops_the_children_s_programs_and_their_conversations_go_on), all at the same assertion in helper _up(): assert all(_running(pid) for pid in pids), failing right after the child's python program is spawned -- a process or jail timing issue unrelated to this doc-only change.

Confirmed pre-existing and unrelated: temporarily set the README edit aside (not under version control at that moment) and reran test_agent_stop_ends_the_child_and_its_python_program alone via testlock on the unmodified tree at the starting commit c0a7d480f56aee27924c2fc61bf6ed0299e96246, same failure in 0.34s. Restored the README edit afterward; only README.md is modified in the working tree now. Left 'scripts/check passes' unticked (not asked by this task's AC) for the reviewer, since the member's test step has these pre-existing, unrelated failures.

Check `scripts/check` exited 1

(122 earlier lines omitted)
```text
>       assert [s.rsplit("\n", 1)[-1] for s in said] == ["DENIED"] * len(inputs), said
E       AssertionError: ['(/private/var/folders/rf/f34xmczn4659gm98hrsprydc0000gn/T/pytest-of-brukhabtu/pytest-990/popen-gw0/test_a_session_ru...me/xdg/bh-02/startup.py ran first: no public functions)
E         DENIED', 'DENIED', 'DENIED', 'DENIED', 'DENIED', 'WROTE', ...]
E       assert ['DENIED', 'D... 'WROTE', ...] == ['DENIED', 'D...'DENIED', ...]
E         
E         At index 5 diff: 'WROTE' != 'DENIED'
E         Use -v to get more diff

bh-02/app/tests/test_python_repl.py:980: AssertionError
_____________ test_a_listener_that_left_after_listening_is_refused _____________
[gw5] darwin -- Python 3.15.0 /Users/brukhabtu/Documents/src/github.com/bruk-io/bh-02/.venv/bin/python

run_id = '7851ea8508be40b199aae54029537fee'
jail_dir = '/private/tmp/bg-6u_b_ew0'

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
2 failed, 3851 passed, 231 skipped in 69.93s (0:01:09)
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

Review: closed. AC1 met: README watch bullet (commit 7a4085d5) names both ends, agent_end and the session no longer running (pid in running.lock gone), saying so, matching docs/bh-02/reference/command-line.md. Full check: all gates, docs, tokens ok; tests 2 failed / 3851 passed (test_python_repl home-session jail test, brig test_channel_planted_link left-listener test), both outside this doc-only change's area; the worker's 6 test_agents_wiring failures did not recur in the full run. No findings filed.
<!-- SECTION:NOTES:END -->
