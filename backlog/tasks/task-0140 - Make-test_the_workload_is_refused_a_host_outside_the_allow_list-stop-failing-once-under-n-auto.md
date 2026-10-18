---
id: TASK-0140
title: >-
  Make test_the_workload_is_refused_a_host_outside_the_allow_list stop failing
  once under -n auto
status: To Do
assignee: []
created_date: '2026-10-18 05:33'
labels:
  - brig
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In one full scripts/check run (3638 passed, 1 failed, 118 skipped, under -n auto --dist loadgroup) libs/brig/tests/integration/test_connect_proxy_launch.py::test_the_workload_is_refused_a_host_outside_the_allow_list failed: the workload's urlopen of http://127.0.0.1:<port>/x raised ConnectionRefusedError (the test expects the proxy's own 403, line 256). The next full run passed (3639 passed), and the file passes alone 5 of 5 runs, so it is flaky and not tied to any change. It does not touch host_paths. Found while fixing TASK-0136.06; not part of it. First look: whether the workload reached 127.0.0.1 directly (so the origin was already closed or its port reused) instead of through the proxy, and whether the proxy's port file was read before the proxy listened.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause of the one-off ConnectionRefusedError is found and named in the notes
- [ ] #2 The test, or the code it exercises, is changed so the run cannot fail this way, and the test is seen failing (planted) before the fix and passing after
- [ ] #3 scripts/check libs/brig passes
<!-- AC:END -->
