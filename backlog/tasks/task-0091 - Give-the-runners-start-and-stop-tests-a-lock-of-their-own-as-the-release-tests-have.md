---
id: TASK-0091
title: >-
  Give the runner's start and stop tests a lock of their own, as the /release
  tests have
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-14 01:54'
updated_date: '2026-10-14 02:37'
labels:
  - runner
  - tests
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Noticed by TASK-0085's worker (2026-10-14). TASK-0085 gave BrigJail a keyword-only lock and the /release tests a lock under tmp_path, so another jail of the same user can't fail them. The runner's start and stop tests in bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py that assert a jail's placeholders are removed on stop still take the shared /tmp/bh-02-jails-{uid}.lock, so a live jail elsewhere (an overlapping run, a bh-02 session) fails them the same way. test_release_never_stops_a_program... asserts no freed path and may keep the real lock.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every runner test that asserts placeholders removed on stop or release builds its BrigJail with a lock under tmp_path; a run with another process holding the real lock passes them (recorded), and failed before
- [x] #2 scripts/check passes
- [x] #3 A test holds the tmp lock shared from another process, calls release, and shows the placeholders stay held and the answer says another session holds them (the shared-lock rule end to end)
- [x] #4 test_release_never_stops_a_program_its_owner_did_not_and_says_it_still_holds uses a tmp lock too; the runner README's lock sentence is wrapped like the rest of the file; BrigJail's docstring names /tmp/bh-02-jails-<uid>.lock rather than the private _LOCK
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) baseline with a root holder of the real lock (/tmp/bh-02-jails-0.lock, LOCK_SH): confined tests fail where cleanup is asserted. (2) Give each BrigJail that starts a jail and asserts placeholder cleanup on stop/release/failed start a lock under tmp_path, and the refused-start stand-in script its lock as argv (the stand-in is a separate bh-02, so it keeps the real lock where it is not asserted). Stand-ins that assert nothing about cleanup keep the real lock. (3) Add a test: another process holds the tmp lock SH, stop, release keeps the placeholder and says another session holds it; after the holder is gone, release frees it. Plant: release sweeping a different lock must fail it. (4) Docstring names the path; README lock paragraph rewrapped to 100 columns. Risks: a stand-in process with the real lock; proof under the real holder. NOTE: this plan was written after the edits in step 2 had begun (the --plan step was skipped first).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Orchestrator, 2026-10-14: TASK-0085's close review's should-fix items and nits added before work began; still size-1 (one small test and mechanical edits in the same files).

Changed: runner tests (test_runner_confined.py) build BrigJail with lock=str(tmp_path / "jails.lock") in the tests that assert placeholder cleanup: test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds, test_release_never_stops... (AC4), test_a_killed_bh_02_s_jail_ends_with_it..., test_the_sweep_leaves_a_record_whose_process_group_still_runs (2 jails), test_the_sweep_removes_what_a_jail_left_whose_group_is_only_zombies, test_a_placeholder_is_made_and_marked_before_bubblewrap_starts, test_a_jail_that_fails_to_launch_leaves_nothing_on_the_host, test_a_refused_start_s_error_crosses..., test_a_jail_start_cancelled_while_it_launches..., test_a_record_with_unmarked_paths..., test_placeholders_a_crashed_session_left..., and test_a_refused_first_start_destroys... (its subprocess stand-in takes the lock as argv[4]). Not changed, because they assert no placeholder cleanup on stop/release and passed under the holder: test_a_linux_jail_ends_when_the_host_renames_over..., test_each_start_keeps_what_it_is..., test_an_input_creating_the_project_s_own_absent_local_env..., test_a_linux_jail_lets_an_input_write_its_project_s_auto_memory..., test_git_init_on_the_host..., test_a_second_jail_s_carve_out... . Stand-in subprocess scripts (_KILLED_WITH_A_BACKGROUND_INPUT, _crashed_in, _CRASH_AT_LAUNCH) keep the real lock: they stand for another bh-02 session.
New test: test_release_keeps_what_another_session_holds_on_the_shared_lock_until_it_is_gone: a child process holds the tmp lock LOCK_SH (_HOLDS_THE_LOCK_SHARED); the started jail is stopped; release() says '<path> stays held: another bh-02 session of yours is running a jail' and the placeholder is_dir; after the child is killed, release() frees it.
jail.py: BrigJail docstring names /tmp/bh-02-jails-<uid>.lock (rewrapped to 100 columns). README runner: the lock paragraph (When they go: ...) rewrapped to 100 columns.
EVIDENCE (root, uv run; holder = python3 LOCK_SH on /tmp/bh-02-jails-0.lock, pid 1703 then 3806):
(a) baseline, unchanged code, holder alive: runner test_runner_confined.py: 13 failed, 37 passed, 1 skipped (exit 1). Failing: the secret-replace test, the killed-session test, both sweep tests, the placeholder-made-before-bwrap test, the launch-fail test, both refused-first-start cases, both refused-start-error cases, the cancelled-launch test, the unmarked-paths test, the crashed-session test.
(b) git stash (HEAD code and tests), holder alive: the same 13 failed (exit 1). git stash pop restored all three files.
(c) change, holder alive (single holder pid 3806): test_runner_confined.py 51 passed, 1 skipped (exit 0). runner plugin tests (bh-02/plugins/runner-cordis-plugin): 66 passed, 1 skipped (exit 0).
(d) planted: jail.py _swept opened self._lock + '.other' (release sweeps a different lock), holder alive: the new test fails: 'Nothing holds .../local.env until something starts...', assert is_dir() False (exit 1). jail.py restored, sha256 checked OK.
Checks (root): scripts/arch-check exit 0; uv run mypy exit 0 (184 files, no issues); scripts/check exit 1 at first (lint E501 on the BrigJail docstring line, 112 > 110: rewrapped); scripts/check exit 0 after: format 618 files ok, lint ok, types ok, tests 2528 passed, 31 skipped (364.80s), gates ok, docs ok.
Holder: pid 3806 killed; it is a zombie (PID 1 does not reap), with no open fds; no sleep(900) process is running. /tmp/bh-02-jails-0.lock is left as the file it was.
Not run: the tester-user run (not used: root runs); scripts/linux-jail-check (not required by the criteria, not run); libs/brig and libs/cordis were not touched, so their suites run only through scripts/check.
<!-- SECTION:NOTES:END -->
