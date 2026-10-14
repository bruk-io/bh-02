---
id: TASK-0091
title: >-
  Give the runner's start and stop tests a lock of their own, as the /release
  tests have
status: To Do
assignee: []
created_date: '2026-10-14 01:54'
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
- [ ] #1 Every runner test that asserts placeholders removed on stop or release builds its BrigJail with a lock under tmp_path; a run with another process holding the real lock passes them (recorded), and failed before
- [ ] #2 scripts/check passes
<!-- AC:END -->
