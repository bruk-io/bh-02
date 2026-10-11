---
id: TASK-0076
title: >-
  Set NO_PROXY empty for the egress proxy's workload, so an inherited one can't
  bypass the filter
status: Done
assignee:
  - '@claude'
created_date: '2026-10-10 21:58'
updated_date: '2026-10-11 17:54'
labels:
  - brig
  - size-1
dependencies: []
parent_task_id: TASK-0079
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`connect_proxy` means to set no exemption at all (libs/brig/src/brig/mech/connect_proxy.py:125: 'deliberately NOT set, not even for loopback'), but it leaves `NO_PROXY` unset rather than empty, and the launcher passes the host's environment through, so an inherited `NO_PROXY` reaches the workload. This container sets `NO_PROXY=localhost,127.0.0.1,...,169.254.0.0/16,...` (169.254.x.x is where cloud machines serve their metadata), and 6 egress tests fail here; all 11 pass with it unset (checked 2026-10-10). bh-02 is not affected: its jails have no network.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The workload's environment has `NO_PROXY` and `no_proxy` set empty whatever the launching environment holds
- [x] #2 The egress tests set `NO_PROXY` in the launching environment and pass; they fail before the fix
- [x] #3 `uv run pytest libs/brig -q` passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1 tests first: autouse fixture exporting NO_PROXY/no_proxy in launching env for the 2 egress integration files + unit test on Step.env; see them fail. 2 SPEC.md dated decision paragraph naming TASK-0076. 3 connect_proxy Step env={NO_PROXY:'',no_proxy:''} (launcher overlays jail.env over os.environ), fix comments. 4 run libs/brig, check, arch-check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-1 (2026-10-11): one environment change and a test that sets NO_PROXY; nothing unknown.

Changed: connect_proxy Step.env = NO_PROXY/no_proxy set empty (launcher overlays jail.env over os.environ); SPEC.md s10 dated amendment naming TASK-0076; comments; unit test test_the_workload_env_sets_no_proxy_empty_in_both_cases; autouse fixtures exporting NO_PROXY/no_proxy (incl. 127.0.0.1) in test_egress_decisions.py and test_connect_proxy_launch.py. Planted: with tests added and fix absent, 7 failed (the unit test + the 6 egress tests), 14 passed. After fix: those 3 files 21 passed, run WITH the environment NO_PROXY. Full libs/brig as root: 6 failed/775 passed (zombie class + root-only); under tini -s: 2 failed (test_bwrap_fs read carve-out, test_probe_runner failed_control -- the root-only class, TASK-0079.11), 779 passed. AC3 therefore NOT fully met natively: remaining failures are not egress. ruff format/check, mypy, arch-check --no-fix all exit 0. Did not run scripts/check or linux-jail-check.

Review (2026-10-11, a reviewer who did not do the work): CLOSE. AC1: the step's env overlays the launching environment for the workload and for exec (run/launcher.py, run/exec_.py); nothing later in the chain re-adds NO_PROXY; a conflicting step fails closed (EnvConflict). AC2: with this environment's NO_PROXY (127.0.0.1 in it) the three files give 21 passed; with the fix reverted in a scratch copy, 7 failed (the 6 egress plus the unit test). AC3, judged where brig's tests are meant to run (an unprivileged user, an init that reaps): as tester under tini -s, libs/brig 781 passed, 24 skipped, 0 failed; as root under tini, 2 failed, exactly TASK-0079.11's root-only pair; as root with this container's non-reaping PID 1, the zombie class (TASK-0077). ruff, mypy, arch-check exit 0. Nits taken by the orchestrator at close: the SPEC amendment carries its ruling number (decision-170) like every other ruling, and two comments rewrapped.
<!-- SECTION:NOTES:END -->
