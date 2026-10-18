---
id: TASK-0147
title: >-
  Stamp the time a row log's failed write happened, not the time the shell found
  it
status: To Do
assignee: []
created_date: '2026-10-18 12:33'
labels:
  - host-paths
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0145. host_paths.Appender keeps the first failed write's error but no time (the write runs on its thread), so the line the shell prints after exit says when the shell found the failure (the next line queued, or the close), not when the disk filled or the write failed. Record the time of the failure on the writer thread and say it through the Appender, so bootstrap._row_log can report the actual moment. Decision needed from the owner only if the Appender's API should change shape.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The Appender records when its first failed write happened, and a caller can read it (a test with a write that fails after other writes).
- [ ] #2 bootstrap._row_log reports that time, not the time the shell heard of the failure; the test in test_row_log.py that asserts the line is updated to match.
<!-- AC:END -->
