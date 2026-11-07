---
id: TASK-0202
title: scripts/check's tests hang on a many-core Mac
status: Done
assignee:
  - '@claude'
created_date: '2026-11-07 04:27'
updated_date: '2026-11-07 04:58'
labels:
  - scripts
  - tests
  - darwin
  - size-2
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On a 28-core Mac (macOS 27.0.1, 2026-11-06) scripts/check's test step (pytest -n auto --dist loadgroup, so 28 workers) stalls: one worker goes silent around 4% and the 377 tests queued behind it never run; the run sat at 0% CPU for 28 minutes. With -n 8 the same suite finishes in 84 s. Three test_booting.py tests failed under -n auto and pass alone in 6 s. Earlier notes (TASK-0169.01, TASK-0170) blamed stray runs holding the jail lock; nothing held /tmp/bh-02-jails-501.lock during this hang. Until fixed, no 'scripts/check passes' criterion can be proven on this machine.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The hang is explained (which test or fixture, and why many workers trigger it)
- [x] #2 scripts/check completes on a 28-core Mac every time (three runs in a row), whatever the core count, and the worker count it uses is said where TEST_WORKERS is set
- [x] #3 Tests that fail only under load are fixed or filed, not retried away
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Cause (found by probe, single worker): under -n auto a test_booting.py run() hits its 2 s wait_for mid-boot; run() is cancelled inside boot(), before its try/finally, so the runtime is never shut down and ~26 row tasks stay on the loop; pytest-asyncio's Runner.close then cancels every task at once and a fiber whose _live task was cancelled before it first ran never resolves its inertia, so a parent's undo (retire -> settled) awaits it forever: teardown blocks at 0% CPU, the xdist worker goes silent and the work queued on it is stranded. 2. Fix bh_02.run: whatever ends boot, the runtime is shut down (boot inside the try). Regression test in test_booting.py: a run cancelled mid-boot leaves no task of its runtime pending; seen failing before the fix. 3. File the cordis mechanism (a _live task cancelled before it starts leaves inertia unresolved) as its own task. 4. scripts/check: TEST_WORKERS capped at min(8, cpu count), comment says why; adjust test_check_script if needed. 5. File the 2 s boot deadlines in test_booting.py as load-only failures. 6. Three testlock scripts/check runs; diff failures against filed tasks, file leftovers. Risk: shutdown inside a cancelled run adds up to 1 s (grace) to a cancelled run.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-06: Approved as the run's first task (Opus worker): nothing else can prove 'scripts/check passes' on this Mac until it is fixed. Fix the cause; a lower worker count is fine only if AC #1 explains the hang and AC #3's load-only failures are fixed or filed, not retried away.

Cause (AC #1). The captured -n auto log (pytest -v, 28 workers) shows gw24 report two results and go silent at 2%: its last was FAILED test_booting.py::test_an_unrelated_providers_background_work_does_not_keep_an_interactive_session_open (its 2 s wait_for timed out: 28 workers booting the shipped stack at once), and the one test never started was the next one handed to it; every other worker finished and the session never ended. Reproduced on one worker with no load: wait_for(run([*layers(), patch]), 0.02) on that test's patch hung in teardown, faulthandler (30 s) showing asyncio/runners.py _cancel_all_tasks under pytest-asyncio's _scoped_runner. A task dump after the timeout: run() had been cancelled inside boot(), before its try/finally, so the runtime was never shut down and 26 row tasks were left on the loop (cancelling=0). The loop's close then cancels them all at once; after that one task stays for ever, a parent's undo in Fiber.retire -> settled -> shield(inertia) (cordis runtime.py:119/99) whose child task ended without resolving its inertia (a task cancelled before its first step never enters _live's except). 0% CPU, worker silent, its queue stranded. Why many workers: only a deadline missed mid-boot cancels run() there, and only load makes the boot miss 2 s.

Fix: bh_02.run shuts the runtime down however the run ends, boot included (bootstrap.py). New test test_booting.py::test_a_run_cancelled_while_its_rows_start_leaves_no_row_running cancels run() at its first row's reload and asserts no task is left: with the fix reverted (git stash) it failed ('Left contains 35 more items', _live tasks); with it, test_booting.py 19 passed. The 0.02..1.0 s probe that hung before ran 10 cases in 2.75 s with the fix. The cordis half (a pre-start cancel leaving inertia unresolved) is filed as TASK-0203.

AC #2. scripts/check: TEST_WORKERS = str(min(8, os.cpu_count() or 1)), the comment says why (TASK-0202, 28 vs 8). New test test_check_script.py::test_the_tests_run_on_eight_workers_at_most_whatever_the_core_count: failed with TEST_WORKERS planted back to 'auto', passes with the cap (9 passed). Three 'testlock scripts/check' in a row: exit 1 each in 74 s, 72 s, 73 s; every step reported (format, lint, types, gates, docs, tokens ok; tests 15 failed/3795 passed/25 errors, then 16/3794/25 twice). Exit 1 is the filed failures, not a hang.

AC #3, failures under load or not filed before: the three 2 s boot deadlines in test_booting.py (fail at 28 workers, pass at 8: the cap hides them) -> TASK-0204; brig's run_id teardown running a missing /usr/bin/docker, an ERROR on whichever test ends each worker (8 a run, the 'flaky' warden/host-paths/brig ERRORs) -> TASK-0205; test_tui_working real-clock and test_channel_planted_link listener test, each failing in one run of three -> TASK-0206. The rest are filed: TASK-0197 (session from home), TASK-0198 (supervisor_link SEQPACKET, SIGRTMIN, exit_status, teardown_zombies), TASK-0199 (interpreter-deny chflags), TASK-0200 (six sub-agent wiring), TASK-0201 (trajectory name), TASK-0169.04 (keyed model key), TASK-0169.05 (xdist groups). Not verified: a run at 28 workers (this run's rules cap pytest at -n 8).

Correction to the AC #1 note: the captured pytest-v.log is not the 28-minute run the description reports. It is a later -n auto run that reached ~99% and was stopped at session finish (OSError: cannot send (already closed?)): gw24 went silent at 2% right after its timed-out booting test, and exactly one collected test never started (the log does not show which worker it was queued on, so it is not attributed to gw24 here). The description's run stranded 377 tests behind its silent worker. Same mechanism, two runs; how much work is stranded depends on how much the silent worker had queued when its test missed the deadline.

Check `scripts/check` exited 1

(4406 earlier lines omitted)
```text
FAILED bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py::test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop@jail-lock
FAILED bh-02/app/tests/test_real_launch.py::test_a_keyed_model_s_key_never_reaches_an_input_s_environment
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_retiring_a_child_while_it_replies_ends_the_call_with_no_report@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_unloading_the_agents_row_retires_every_child_it_holds@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_ctrl_c_stops_the_parent_s_reply_and_the_child_it_waits_on_from_the_tool@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_ctrl_c_stops_the_child_a_python_input_waits_on@jail-lock
FAILED bh-02/app/tests/test_trajectory_view.py::test_a_sub_agent_is_a_name_in_the_agents_directory_that_bh_02_makes_and_no_other
FAILED bh-02/app/tests/test_xdist_groups.py::test_every_test_file_that_starts_a_jail_is_in_a_group
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_agent_stop_ends_the_child_and_its_python_program@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_release_stops_the_children_s_programs_and_their_conversations_go_on@jail-lock
FAILED libs/brig/tests/integration/test_channel_planted_link.py::test_a_listener_that_left_after_listening_is_refused
FAILED libs/brig/tests/integration/test_exit_status_is_recorded_not_invented.py::test_a_pid_is_watched_until_its_status_is_recorded_so_no_one_sees_neither
FAILED libs/brig/tests/unit/test_teardown_zombies.py::test_teardown_fails_an_item_whose_table_it_cannot_read
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_descriptors_cross_both_ways
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_missed_deadline_calls_unresponsive_once_ends_the_link_and_ignores_the_late_reply
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_closed_socket_wakes_every_caller_waiting_on_it
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_the_hello_is_waited_for_and_a_socket_that_closes_first_is_gone
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_reply_nobody_waits_for_and_a_message_it_cannot_read_are_dropped_with_their_fds
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_link_nobody_holds_closes_its_end
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_close_is_idempotent_and_sends_end_of_file
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_replies_find_their_callers_by_id_whatever_order_they_come_in
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_an_error_reply_is_a_refusal_with_the_reason_and_its_descriptors_are_closed
ERROR examples/warden/plugins/warden-systray-cordis-plugin/tests/test_tray.py::test_no_names_is_a_placeholder_label
ERROR examples/warden/app/tests/test_warden_bootstrap.py::test_shutting_down_terminates_every_registered_process
ERROR examples/warden/app/tests/test_warden_bootstrap.py::test_a_command_that_cannot_spawn_fails_the_composition
ERROR examples/warden/plugins/warden-cordis-plugin/tests/test_process.py::test_spawns_the_command_and_terminates_it_on_exit
ERROR libs/brig/tests/unit/test_strategies.py::test_specs_strategy_can_emit_a_non_default_value_for_every_field[fs.read_allows]
ERROR libs/host-paths/tests/test_host_paths_appender.py::test_a_cancelled_flush_leaves_the_writes_to_finish
ERROR examples/warden/plugins/warden-systray-cordis-plugin/tests/test_systray_wiring.py::test_the_row_binds_a_zero_argument_factory_and_runs_nothing
ERROR libs/host-paths/tests/test_host_paths_appender.py::test_close_waits_for_the_last_write_then_closes_the_file_and_takes_no_more
16 failed, 3794 passed, 221 skipped, 25 errors in 75.65s (0:01:15)
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
INFO    -  Documentation built in 1.33 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

Review (reviewer agent), 2026-11-06: not closed, one blocker. The ACs hold: AC1 cause explained and fixed (boot inside run()'s try, rt.shutdown in finally) with a regression test; AC2 reviewer's full check through testlock completed in 75.65 s, every step reported (16 failed/3794 passed/25 errors, all other steps ok), TEST_WORKERS = min(8, cpu) with its reason; AC3 load-only failures filed as TASK-0203..0206, the rest map to filed tasks. Blocker: close-task refuses a bug without a recorded repro. The worker saw test_booting.py::test_a_run_cancelled_while_its_rows_start_leaves_no_row_running fail with the fix reverted, but that run is not recorded. Record it (revert bootstrap.py's change, record-check TASK-0202 --repro -- uv run pytest bh-02/app/tests/test_booting.py::test_a_run_cancelled_while_its_rows_start_leaves_no_row_running -q, restore), then send back for close. No other findings; no drafts filed.

Repro at 5c9be416d47e, test files: bh-02/app/tests/test_booting.py; command: `uv run pytest bh-02/app/tests/test_booting.py::test_a_run_cancelled_while_its_rows_start_leaves_no_row_running -q` exited 1

```text
F                                                                        [100%]
=================================== FAILURES ===================================
_______ test_a_run_cancelled_while_its_rows_start_leaves_no_row_running ________

composition = <function composition.<locals>.layer at 0x10a4f8eb0>

    async def test_a_run_cancelled_while_its_rows_start_leaves_no_row_running(
        composition: Callable[..., Path],
    ) -> None:
        """A run cancelled mid-boot (Ctrl-C, or a test's deadline) shuts its rows down before the
        cancellation goes on. Left on the loop, they were cancelled all at once when the loop closed,
        and a row whose task was cancelled before it began left its parent waiting on it forever: the
        hang that stalled a scripts/check worker (TASK-0202)."""
        patch = composition('[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n', one_reply=True)
        running: asyncio.Task[None] | None = None
    
        def cancel_once_a_row_starts(line: str) -> None:
            if running is not None and not running.cancelling() and line.startswith("reload "):
                running.cancel()
    
        running = asyncio.create_task(
            run([*layers(), patch], [Row("chat", config={"prompt": "hi"})], trace=cancel_once_a_row_starts)
        )
        (outcome,) = await asyncio.wait_for(asyncio.gather(running, return_exceptions=True), 10)
        assert isinstance(outcome, asyncio.CancelledError)
>       assert [task for task in asyncio.all_tasks() if task is not asyncio.current_task()] == []
E       AssertionError: assert [<Task pendin...card()]>, ...] == []
E         
E         Left contains 35 more items, first extra item: <Task pending name='Task-8' coro=<_live() running at /Users/brukhabtu/Documents/src/github.com/bruk-io/bh-02/libs/cordis/src/cordis/runtime.py:483> wait_for=<Future pending cb=[Task.task_wakeup()]> cb=[set.discard()]>
E         Use -v to get more diff

bh-02/app/tests/test_booting.py:182: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_booting.py::test_a_run_cancelled_while_its_rows_start_leaves_no_row_running
1 failed in 1.29s
```

Fix round 2026-11-06: repro recorded above. With bootstrap.py reverted to its pre-fix form (git show 749a2d1d~1), record-check --repro under testlock ran the test: 1 failed (35 tasks left on the loop), recorded. Fix restored (git checkout), same test through testlock: 1 passed in 1.25s. Back to review for close.

Check `scripts/check` exited 1

(4379 earlier lines omitted)
```text
FAILED bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py::test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file@jail-lock
FAILED bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py::test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_retiring_a_child_while_it_replies_ends_the_call_with_no_report@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_unloading_the_agents_row_retires_every_child_it_holds@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_ctrl_c_stops_the_parent_s_reply_and_the_child_it_waits_on_from_the_tool@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_ctrl_c_stops_the_child_a_python_input_waits_on@jail-lock
FAILED bh-02/app/tests/test_trajectory_view.py::test_a_sub_agent_is_a_name_in_the_agents_directory_that_bh_02_makes_and_no_other
FAILED bh-02/app/tests/test_xdist_groups.py::test_every_test_file_that_starts_a_jail_is_in_a_group
FAILED bh-02/app/tests/test_real_launch.py::test_a_keyed_model_s_key_never_reaches_an_input_s_environment
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_agent_stop_ends_the_child_and_its_python_program@jail-lock
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_release_stops_the_children_s_programs_and_their_conversations_go_on@jail-lock
FAILED libs/brig/tests/integration/test_exit_status_is_recorded_not_invented.py::test_a_pid_is_watched_until_its_status_is_recorded_so_no_one_sees_neither
FAILED libs/brig/tests/unit/test_teardown_zombies.py::test_teardown_fails_an_item_whose_table_it_cannot_read
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/unit/test_process_namespaces_pure.py - AttributeError: ...
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_an_error_reply_is_a_refusal_with_the_reason_and_its_descriptors_are_closed
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_closed_socket_wakes_every_caller_waiting_on_it
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_the_hello_is_waited_for_and_a_socket_that_closes_first_is_gone
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_descriptors_cross_both_ways
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_reply_nobody_waits_for_and_a_message_it_cannot_read_are_dropped_with_their_fds
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_link_nobody_holds_closes_its_end
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_close_is_idempotent_and_sends_end_of_file
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_missed_deadline_calls_unresponsive_once_ends_the_link_and_ignores_the_late_reply
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_replies_find_their_callers_by_id_whatever_order_they_come_in
ERROR examples/warden/plugins/warden-systray-cordis-plugin/tests/test_tray.py::test_no_names_is_a_placeholder_label
ERROR examples/warden/plugins/warden-cordis-plugin/tests/test_warden_registry.py::test_two_processes_cannot_share_a_name
ERROR examples/warden/plugins/warden-systray-cordis-plugin/tests/test_systray_wiring.py::test_the_row_binds_a_zero_argument_factory_and_runs_nothing
ERROR examples/warden/plugins/warden-cordis-plugin/tests/test_warden_wiring.py::test_a_supervised_row_enters_the_process_then_registers_it_under_its_name
ERROR libs/host-paths/tests/test_host_paths_appender.py::test_the_file_is_made_readable_by_its_owner_alone
ERROR examples/warden/app/tests/test_warden_bootstrap.py::test_a_command_that_cannot_spawn_fails_the_composition
ERROR examples/warden/plugins/warden-cordis-plugin/tests/test_warden_registry.py::test_each_registration_is_its_own_entry_and_its_remover_takes_only_that
ERROR libs/host-paths/tests/test_host_paths.py::test_the_config_home_is_the_variable_else_the_home_s_dot_config[environ3-expected3]
15 failed, 3795 passed, 221 skipped, 25 errors in 73.92s (0:01:13)
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
INFO    -  Documentation built in 1.31 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

Review (reviewer agent), 2026-11-06, closed. The blocker from the last round (no recorded repro) is resolved: record-check --repro at 5c9be416 shows test_a_run_cancelled_while_its_rows_start_leaves_no_row_running failing (35 tasks left) with the fix reverted. Reviewer's full check through testlock completed in 73.92 s with every step reported: 15 failed/3795 passed/25 errors, all of them failures already filed (TASK-0197..0206, TASK-0169.04/.05), and no files changed by the check. AC1-3 met as ticked. No findings; no drafts filed.
<!-- SECTION:NOTES:END -->
