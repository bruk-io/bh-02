---
id: task-0032
title: On Linux the person can add their credential without stopping bh-02
status: To Do
assignee: []
created_date: '2026-09-30 14:48'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0023. When bh-02 has no local.env at a searched path under the project, a Linux jail holds that path with a read-only placeholder so a cell can't plant one. While the session runs, the person can't create their own credential there either; the session notice says to stop bh-02 first. Adding the credential mid-session should not require quitting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The person can create their credential file at a held path during a session, through a documented step (e.g. a command that releases the hold and restarts the kernel), without a cell getting a window to plant or read one
- [ ] #2 After that step the model row uses the new credential and the jail masks it
- [ ] #3 The session notice and README describe the step; scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
