---
id: TASK-0205
title: >-
  brig's leak sweep fails the last test of every worker on darwin: no
  /usr/bin/docker
status: To Do
assignee: []
created_date: '2026-11-07 04:50'
labels:
  - brig
  - tests
  - darwin
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In every scripts/check on macOS 27.0.1 (TASK-0202, 2026-11-06; 8 times a run) the run_id session fixture's teardown (libs/brig/tests/conftest.py:972, tests.oci_jail.leaked_containers) runs /usr/bin/docker, which is not there (Docker Desktop installs elsewhere), and raises FileNotFoundError. The teardown of a session fixture is reported against the last test a worker ran, so the ERROR lands on a different, unrelated test each run (warden, host-paths, brig unit tests), which reads as flakiness elsewhere. TASK-0198 covers brig's darwin suite but names neither the docker path nor the spill onto other members.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The sweep finds docker where it is (or skips the container arm with a reason when there is none) and a scripts/check on darwin reports no run_id teardown ERROR
<!-- AC:END -->
