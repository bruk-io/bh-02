---
id: TASK-0124
title: Never choose a supervisor interpreter under a root the jail may write
status: To Do
assignee: []
created_date: '2026-10-16 13:48'
labels:
  - runner
  - security
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0084.02's close review. supervisor_interpreter(found, mounted) takes the first candidate (/usr/bin/python3, then <sys.base_prefix>/bin/python3) whose spelling and resolved target are under the Spec's read_allows, and read_allows include the project and the jail's other writable roots. If bh-02's base interpreter ever lay under one of them (a project opened at a directory that holds the uv-managed Python, such as the home directory), the jail's PID 1 would run an interpreter the model can write. Check first whether the runner's spec_for already denies writing it (bh-02/CLAUDE.md: what the host trusts, the jail keeps from the model); if it does, record that and add the test; if not, exclude candidates under a write root.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 supervisor_interpreter never returns a candidate whose spelling or resolved target is under a root the jail may write unless that path is denied to writes, shown by a test with the base interpreter under a writable root
- [ ] #2 The decision stays one pure function; the runner's existing tests pass
<!-- AC:END -->
