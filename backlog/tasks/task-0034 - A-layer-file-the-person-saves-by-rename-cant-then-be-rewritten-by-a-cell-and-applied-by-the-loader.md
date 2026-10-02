---
id: task-0034
title: >-
  A layer file the person saves by rename can't then be rewritten by a cell and
  applied by the loader
status: In Progress
assignee: []
created_date: '2026-10-01 02:33'
updated_date: '2026-10-02 01:37'
labels: []
dependencies:
  - task-0033
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0028. A --patch layer file inside the project is write-denied to cells. On Linux, once the person saves it with an editor that saves by rename, the mount detaches and a cell can rewrite it, and the loader's watcher applies the rewrite, reshaping the running program from inside the jail. The layer files are the composition's own; a cell must never change them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After the person saves a layer file by rename mid-session, a jailed cell's write to it is refused, or the loader refuses a change it can't attribute to the person; a real-bwrap test shows the cell's rewrite is not applied
- [ ] #2 The person's own edits to the layer file still apply while the session runs (the reload feature keeps working)
- [ ] #3 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
