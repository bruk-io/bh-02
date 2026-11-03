---
id: DRAFT-0009
title: >-
  brig test_a_launch_scoped_helper_that_never_exits fails on a stale jail-dir
  record missing 'namespaces'
status: Draft
assignee: []
created_date: '2026-10-18 21:23'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In a full scripts/check on 2026-10-18 (TASK-0152 review), libs/brig/tests/integration/test_helpers.py::test_a_launch_scoped_helper_that_never_exits_fails_instead_of_hanging failed with JailDirInUse: /tmp/bh20363-0/procs/945c0e16c4363d18/record.json is missing key(s) namespaces. Either an earlier run left a record in an older format in a reused /tmp jail directory, or the record is read before it is fully written. It passed on the previous full run.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test passes on repeated full scripts/check runs, or the cause of the leftover/partial record is found and fixed
<!-- AC:END -->
