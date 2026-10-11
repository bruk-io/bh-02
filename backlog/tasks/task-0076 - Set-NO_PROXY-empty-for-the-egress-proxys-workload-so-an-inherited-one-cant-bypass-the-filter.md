---
id: TASK-0076
title: >-
  Set NO_PROXY empty for the egress proxy's workload, so an inherited one can't
  bypass the filter
status: To Do
assignee: []
created_date: '2026-10-10 21:58'
updated_date: '2026-10-11 15:30'
labels:
  - brig
  - size-1
dependencies: []
priority: medium
type: bug
parent_task_id: TASK-0079
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`connect_proxy` means to set no exemption at all (libs/brig/src/brig/mech/connect_proxy.py:125: 'deliberately NOT set, not even for loopback'), but it leaves `NO_PROXY` unset rather than empty, and the launcher passes the host's environment through, so an inherited `NO_PROXY` reaches the workload. This container sets `NO_PROXY=localhost,127.0.0.1,...,169.254.0.0/16,...` (169.254.x.x is where cloud machines serve their metadata), and 6 egress tests fail here; all 11 pass with it unset (checked 2026-10-10). bh-02 is not affected: its jails have no network.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The workload's environment has `NO_PROXY` and `no_proxy` set empty whatever the launching environment holds
- [ ] #2 The egress tests set `NO_PROXY` in the launching environment and pass; they fail before the fix
- [ ] #3 `uv run pytest libs/brig -q` passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-1 (2026-10-11): one environment change and a test that sets NO_PROXY; nothing unknown.
<!-- SECTION:NOTES:END -->
