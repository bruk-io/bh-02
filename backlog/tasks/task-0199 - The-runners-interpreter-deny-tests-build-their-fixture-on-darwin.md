---
id: TASK-0199
title: The runner's interpreter-deny tests build their fixture on darwin
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-07 04:27'
updated_date: '2026-11-07 06:15'
labels:
  - runner
  - darwin
  - tests
  - size-1
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0079.34's re-run (macOS 27.0.1, 2026-11-06), with and without Claude Code's sandbox: test_runner_confined.py's test_a_jail_denies_the_interpreter_bh_02_runs_on_when_it_lies_in_the_project, test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file and test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop fail in their fixture: shutil.copy2 of the uv Python into the project raises PermissionError EPERM (copystat's flags; a plain copy2 to a fresh temp dir works). No jail starts, so the denies they guard are untested on darwin. TASK-0169.04's notes called these 'host sandbox' failures; they are not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The three tests build their interpreter on darwin and pass; each still fails if the deny it guards is removed (seen failing)
- [x] #2 The runner plugin's tests pass on macOS and Linux
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) Reproduce the darwin fixture failure (testlock uv run pytest the three tests), confirm it's shutil.copy2's copystat->chflags EPERM on /usr/bin/true's 'restricted' SIP flag, even to a fresh temp dir (not a destination issue). 2) Replace the three shutil.copy2 call sites (in _a_python_in, _a_uv_python_in, and inline in test_the_walk_to_the_interpreter...) with a shared helper _stood_in_for_an_interpreter: shutil.copy + chmod(0o755), which skips copystat. 3) Re-run the three tests, confirm pass. 4) Plant the removal of the deny each test guards (jail.py's spec_for denies list) and confirm each fails on a real assertion, not a fixture error; revert. 5) Run scripts/check for the runner plugin and scripts/linux-jail-check for AC #2. Risk: the darwin fixture fix might mask that a test no longer exercises its guard (the interpreter-file deny overlaps the link-holder deny in one fixture's layout) - checked by planting removal of each deny line separately.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause confirmed: shutil.copy2's copystat() re-raises chflags's EPERM on darwin because /usr/bin/true (used as the fake interpreter file by shutil.which('true') or '/bin/true') carries SIP's 'restricted' st_flags, which a copy cannot take -- even into a fresh tempfile.mkdtemp() dir (checked directly, not just via pytest), so the task note's parenthetical about a fresh temp dir working was about a different source file, not this one. Fix: added a shared test helper _stood_in_for_an_interpreter(src, dst) = shutil.copy (no copystat) + dst.chmod(0o755), used at the three call sites (_a_python_in line ~292, _a_uv_python_in line ~395, and inline in test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop line ~448). Ran: testlock uv run pytest <the three tests> -q -> 3 passed (previously: PermissionError: [Errno 1] Operation not permitted on copystat's chflags, as captured before the fix).

Planted removals in jail.py's spec_for denies list, each reverted immediately after (confirmed the file matched the original before moving to the next plant):
- Commented out the holders entry -> all three tests failed on real assertions, not fixture errors: test_a_jail_denies_the_interpreter_bh_02_runs_on_when_it_lies_in_the_project failed at test_runner_confined.py line 335 (the link's own directory is denied assertion); test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file failed at line 429; test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop failed at line 468 (seen failing: testlock uv run pytest on the three tests -> 3 failed).
- Commented out the interpreter entry alone -> the three tests still passed (checked: testlock uv run pytest on the three tests -> 3 passed), because _a_python_in's layout puts the interpreter file in the same directory as the base's python3 link, which the holders entry already denies -- no coverage gap, a redundancy of this fixture's layout. The interpreter-file deny itself is guarded by the pre-existing pure test test_the_interpreter_bh_02_runs_on_is_denied_where_an_input_could_write_it (spec_for direct, no links given), which failed at line 267 with the same plant in (seen failing, exit code 1, assertion on _denied(spec, interpreter)); a direct spec_for call with the same host and interpreters confirmed the file was not denied with the plant in, and was denied once reverted.
All plants reverted before committing; the only change left in jail.py afterward is none -- only the test file changed.
Note on the task description: the claim that a plain copy2 to a fresh temp dir works did not reproduce for /usr/bin/true (SIP's restricted flag) -- checked directly with tempfile.mkdtemp, copy2 failed there too. The description's claim likely refers to a different source file; recorded here for the record.

This session (base c0a7d480, worktree wf_a31c136d-eaf-10) picked this task up from an earlier attempt's uncommitted patch (same fix: shutil.copy + chmod(0o755) in _stood_in_for_an_interpreter, applied at the three call sites) and verified its claims independently rather than trusting them:
- Reverted the three call sites to shutil.copy2 and ran the three tests via testlock uv run pytest: 3 failed, all with "PermissionError: [Errno 1] Operation not permitted" inside shutil.py's copystat -> chflags on the fake interpreter file (test_the_walk_to_the_interpreter...'s traceback shown; same shape for all three) -- reproduces the task's description exactly. Restored the fix (git checkout --) and re-ran: 3 passed in 0.26s.
- Re-did the per-deny plants in jail.py's spec_for (`*interpreter,` / `*holders,` in the denies list), each alone, each reverted before the next (git diff empty after each revert):
  - `*interpreter,` alone commented out: the three tests still passed (testlock uv run pytest, 3 passed), and test_the_interpreter_bh_02_runs_on_is_denied_where_an_input_could_write_it failed (AssertionError at test_runner_confined.py:267, `assert _denied(spec, interpreter)` false) -- confirms the inherited notes' claim that the interpreter-file deny is redundant in these three fixtures' layout and is actually guarded by the pure spec_for test, not these three.
  - `*holders,` alone commented out: all three fixture tests failed on real assertions (not fixture errors) -- test_a_jail_denies_the_interpreter_...'s and test_a_jail_denies_the_directory_of_each_link_...'s `_denied(..., "planted")` assertions, and test_the_walk_to_the_interpreter_...'s `assert all(_denied(spec, f"{project}/{way}/planted") ...)` -- confirming the holders deny is what these three tests actually guard.
  - Confirmed `git diff bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/jail.py` empty after reverting each plant, before moving to the next and before committing.
- AC #2 (not covered by the prior attempt): testlock scripts/check bh-02/plugins/runner-cordis-plugin -> format/lint/types/gates/docs all ok, tests "80 passed, 33 skipped in 6.01s". testlock scripts/linux-jail-check -> "327 passed, 2 skipped in 71.98s", covering the runner plugin and brig's bwrap/e2e suites in the Ubuntu/bubblewrap container. Both green: AC #2 checked.
Only test_runner_confined.py changed; jail.py is unchanged from main (verified via git diff, empty).

Check `scripts/check` exited 1

(3805 earlier lines omitted)
```text
>       assert outcome is teardown.KillOutcome.FAILED, detail
E       AssertionError: pid 1234 now names a different process (start time does not match the one recorded at launch); nothing was signalled
E       assert <KillOutcome.ALREADY_GONE: 'ALREADY_GONE'> is <KillOutcome.FAILED: 'FAILED'>
E        +  where <KillOutcome.FAILED: 'FAILED'> = <enum 'KillOutcome'>.FAILED
E        +    where <enum 'KillOutcome'> = teardown.KillOutcome

libs/brig/tests/unit/test_teardown_zombies.py:115: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_python_repl.py::test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s@jail-lock
FAILED bh-02/app/tests/test_trajectory_view.py::test_a_sub_agent_is_a_name_in_the_agents_directory_that_bh_02_makes_and_no_other
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
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_replies_find_their_callers_by_id_whatever_order_they_come_in
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_descriptors_cross_both_ways
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_closed_socket_wakes_every_caller_waiting_on_it
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_reply_nobody_waits_for_and_a_message_it_cannot_read_are_dropped_with_their_fds
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_close_is_idempotent_and_sends_end_of_file
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_link_nobody_holds_closes_its_end
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_an_error_reply_is_a_refusal_with_the_reason_and_its_descriptors_are_closed
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_the_hello_is_waited_for_and_a_socket_that_closes_first_is_gone
ERROR libs/brig/tests/integration/test_supervisor_link.py::test_a_missed_deadline_calls_unresponsive_once_ends_the_link_and_ignores_the_late_reply
ERROR examples/warden/plugins/warden-systray-cordis-plugin/tests/test_tray.py::test_no_names_is_a_placeholder_label
ERROR examples/warden/plugins/warden-cordis-plugin/tests/test_warden_registry.py::test_two_processes_cannot_share_a_name
ERROR examples/warden/plugins/warden-systray-cordis-plugin/tests/test_tray.py::test_names_come_back_sorted
ERROR examples/warden/plugins/warden-cordis-plugin/tests/test_warden_wiring.py::test_the_registry_row_binds_one_processes_value_and_runs_nothing
ERROR libs/host-paths/tests/test_host_paths_appender.py::test_a_link_at_the_name_is_refused_not_followed[True]
ERROR libs/host-paths/tests/test_host_paths_appender.py::test_an_appender_with_nothing_queued_flushes_and_closes_at_once
ERROR examples/warden/plugins/warden-cordis-plugin/tests/test_process.py::test_spawns_the_command_and_terminates_it_on_exit
ERROR libs/cordis/tests/test_invariants.py::test_invariants_hold_when_operations_interleave[115]
5 failed, 3805 passed, 221 skipped, 25 errors in 71.20s (0:01:11)
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
INFO    -  Documentation built in 1.26 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

Review (reviewer, not the worker): NOT CLOSED. close-task refused because a bug closes only with its repro recorded, and none is. To close: the worker runs record-check TASK-0199 --repro against the three tests with copy2 restored (a repro that fails before the fix), or appends a note starting 'No repro:' that says why. Otherwise the review passes. The diff is test-only and jail.py is unchanged. AC#1 is met by the notes' revert/plant evidence. The interpreter-file deny is guarded by the pure spec_for test, which is accepted. AC#2 is met: the runner plugin gave 80 passed/33 skipped when the reviewer re-ran it on macOS, and linux-jail-check gave 327 passed. The full check is red with 5 failed and 25 errors, none in the runner plugin. They are darwin failures in brig, warden, host-paths, cordis and the app, already tracked by TASK-0198, TASK-0205, TASK-0170 and TASK-0079.15, and are unrelated. No drafts filed.
<!-- SECTION:NOTES:END -->
