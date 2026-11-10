---
id: TASK-0207
title: >-
  Confined runner subagent test fails to boot under scripts/linux-jail-check
  (test_a_child_s_python_shares_the_session_s_jail_only_where_they_are_kept_apart)
status: Done
assignee: []
created_date: '2026-11-07 05:39'
updated_date: '2026-11-10 16:58'
labels:
  - subagents
  - linux
  - tests
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On Linux under scripts/linux-jail-check (Docker, Ubuntu 24.04, bubblewrap 0.9.0, discovered while verifying TASK-0200's fix on Linux), bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner fails before any python program runs: _booted's assertion that every row's loader status is 'active' fails with {'loop': 'inactive', ...}. darwin always skips this test (no /usr/bin/bwrap), so it has not been seen failing there; it is unrelated to TASK-0200 (_running's liveness check), which never reaches this test's model, approval or runner:confined rows. Full run: testlock scripts/linux-jail-check -- bh-02/plugins/subagents-cordis-plugin -q -> 137 passed, 1 failed (only this test).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The cause of the loop row's inactive status under runner:confined in this container is named
- [x] #2 The test passes under scripts/linux-jail-check, or is shown to need an environment this container cannot give (and says so by skipping, named)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-07: TASK-0200's AC3 was narrowed to leave this test's Linux failure to this task; TASK-0200 no longer waits on it. This task now owns the only known failure in the subagents plugin's tests on Linux.

Check `scripts/check` exited 0

(33 earlier lines omitted)
```text
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 46%]
........................................................................ [ 48%]
...s.......s.ssssssssssssssssssssssssssssssssssssssssssssssssssss....... [ 50%]
ssssssssssssssssssssss.ss...ssssssssssssssssssss.s....ss....s........s.. [ 52%]
.....s.........................................s........................ [ 53%]
.............................................................s.sssss.sss [ 55%]
sssssssssssssssssss.ssssssssssssssssssssssssssssssssssssssssssss...s.s.. [ 57%]
.......................................sssssssssssssssss.s.......s....s. [ 59%]
........................................................................ [ 60%]
........................................................................ [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 72%]
.........................s.............................................. [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
........................................                                 [100%]
3876 passed, 268 skipped in 71.68s (0:01:11)
   ok
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
INFO    -  Documentation built in 1.32 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

No repro: the defect was in the test itself (its fake _Host lacked key_envs and models_file, made required by TASK-0169.05, a1d94488), so the failing test was the bug and its fix (TASK-0074, c60d5fe2) had to edit it; no separate failing test can exist on main. Before the fix it failed under linux-jail-check (137 passed, 1 failed, per the description).

Review (reviewer agent, 2026-11-10): closed. #1 met: cause named in the No repro note. #2 met: scripts/linux-jail-check -- bh-02/plugins/subagents-cordis-plugin -> 138 passed, 0 failed (bubblewrap 0.9.0, Python 3.15.2); the renamed test alone: 1 passed. Full check exited 0: 3876 passed, 268 skipped. Title still names the old test (test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner); renaming it to test_a_child_s_python_shares_the_session_s_jail_only_where_they_are_kept_apart is right, but the reviewer's guardrail blocks title edits, so it is left for the owner. No other findings, no drafts.
<!-- SECTION:NOTES:END -->
