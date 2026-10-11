---
id: TASK-0077
title: >-
  Count a zombie as gone in teardown and liveness, so a jail ends cleanly where
  PID 1 doesn't reap
status: Done
assignee:
  - '@claude'
created_date: '2026-10-10 21:58'
updated_date: '2026-10-11 18:52'
labels:
  - brig
  - size-2
dependencies: []
parent_task_id: TASK-0079
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Teardown decides a process group is gone by listing its members with `/bin/ps` (libs/brig/src/brig/run/teardown.py), which lists zombies too, and brig reaps only the leader it parented. Where PID 1 doesn't reap (this container's `process_api`, Docker without `--init`), a killed child stays a zombie in the group, so a dead jail can read as surviving. In such a container 5 kill, teardown and probe tests fail (checked 2026-10-10); that brig's own kill report is fooled the same way is read from the code, not run.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Teardown and liveness count a zombie member as gone (process state Z on Linux and darwin)
- [x] #2 A test plants a zombie in a jail's group under a PID 1 that doesn't reap, and the kill reports the jail ended; it fails before the fix
- [x] #3 brig's kill, teardown and probe tests pass in a container whose PID 1 doesn't reap
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) Spec first: SPEC.md section 9 decision-171 paragraph. 2) teardown membership scan reads stat and skips Z (pure _live_group_members); _identity.is_zombie (/proc on Linux, ps stat elsewhere) used by identity_holds so Handle.alive() counts a zombie as gone. 3) Test: subreaper fixture makes the test process a PID 1 that never reaps; plant a zombie in the jail group, kill() must report ENDED; seen failing with src stashed. 4) Make the suite's own observers (conftest sweeps, kill_group, teardown_exec) count Z as gone. 5) Run brig as root bare, as tester under tini, scripts/check, arch-check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-2 (2026-10-11): process state differs between Linux and darwin, and the test needs a PID 1 that doesn't reap.

Changed: SPEC.md section 9 (decision-171, implementing task TASK-0077); brig/run/teardown.py (pure _live_group_members; scan is ps -Ao pid=,pgid=,stat=, Z rows dropped); brig/run/_identity.py (is_zombie: /proc/<pid>/stat on Linux, ps -o stat= elsewhere; identity_holds returns False for a zombie, so Handle.alive() does); handle.py docstring; tests: new unit test_teardown_zombies.py, new integration test_kill_counts_a_zombie_the_init_never_reaps_as_gone (non_reaping_init fixture: PR_SET_CHILD_SUBREAPER makes the test process an init that never reaps, so it reproduces PID 1 not reaping under any real PID 1), suite observers (conftest registry and ps sweeps, test_kill_group, test_teardown_exec) count Z as gone. Evidence: planted check seen FAILING with the src change stashed (test_kill_counts_a_zombie... failed, as did the 2 kill_group tests) and passing after. Baseline root-without-tini integration run of kill_group/teardown_exec: 4 zombie failures; after the fix: none. Full uv run pytest libs/brig as root without tini: 783 passed, 2 failed (test_bwrap_fs read_carve_out, test_probe_runner failed_control: both the root-only DAC class, TASK-0079.11; the probe_runner failure is NOT zombie related). As tester under tini: libs/brig 785 passed, 24 skipped. scripts/arch-check --no-fix exit 0; mypy clean. scripts/check as root exit 1 with 6 failures: those 2 plus 4 bh-02 tests of the zombie class outside brig (runner-cordis-plugin test_runner_confined x2, app test_python_repl x2), which pass under tini as tester; follow-up task created for them. Not run: scripts/linux-jail-check.

Fix round after review 1 (one new commit on 0ee7e55). (1) conftest _only_zombies_in now needs at least one ps row, all Z; unit test plants no-rows/live-row groups; seen FAILING with the old all(...) restored, passing after. (2) New integration test test_kill_ends_a_live_member_of_a_group_whose_leader_is_a_zombie (leader parented by a non-waiting process, member sleeper still running, subreaper fixture; kill_jail on a namespace handle). It passes as is; with teardown's first group check scratch-reverted to read the leader via identity_holds it failed (seen in the run: 2 failed, the unit one and this one), then reverted, not in the repo. Handle.alive() docstring now says it answers for the leader only. (3) subreaper fixture yields a list; only planted pids are reaped. (4) docstring widths fixed. (5) TASK-0079.12 description corrected, priority medium. Re-runs: kill_group/teardown_exec/probe_runner/wait_ready as root without tini: 29 passed, 1 failed (test_probe_runner, the TASK-0079.11 root-only class). tester under tini: libs/brig 787 passed, 24 skipped. ruff, mypy clean; arch-check --no-fix exit 0.

Review 2 (2026-10-11, the reviewer who did not do the work): CLOSE. The namespace handle is a faithful test of Handle.kill() (kill() is only _kill_jail(self); a zombie leader can only exist for a rehydrated handle, which is the path covered). The planted revert (teardown's first group check reading the leader through identity_holds) fails the new test on 'the live member survived kill()', both controls passing; the tightened sweep also flags the survivor. As root without tini, kill_group/teardown_exec/probe_runner plus the zombie unit tests: 27 passed, 1 failed (TASK-0079.11's root-only control); as tester under tini, libs/brig 787 passed, 24 skipped; ruff, mypy, arch-check exit 0. Taken by the orchestrator at close: the zombie-leader test's finally also SIGKILLs the group, so a member kill() missed can't outlive the test; teardown.py's module docstring reflowed under the house width. kill_group 8 passed after.
<!-- SECTION:NOTES:END -->
