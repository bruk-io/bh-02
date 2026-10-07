---
id: task-0034
title: >-
  A layer file the person saves by rename can't then be rewritten by a cell and
  applied by the loader
status: Done
assignee: []
created_date: '2026-10-01 02:33'
updated_date: '2026-10-02 03:26'
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
- [x] #1 After the person saves a layer file by rename mid-session, a jailed cell's write to it is refused, or the loader refuses a change it can't attribute to the person; a real-bwrap test shows the cell's rewrite is not applied
- [x] #2 The person's own edits to the layer file still apply while the session runs (the reload feature keeps working)
- [x] #3 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commit dad2fb4, on 0033's tripwire and directory pinning. With a real cordis loader: the person's save of a layer file by rename applies (reload keeps working); the next cell's rewrite is refused and never applied; a cell can't swap the layer's directory (red with pinning off). A loader-side attribution check was skipped: no sound way exists to tell the person's change from a cell's, since the cell writes as the same uid and the config.lock route leaves nothing changed after the rename. The 0033 window applies: a cell program running at the moment of the person's rename can get one write in. Verified after merging into leftovers: scripts/check 1830 passed / 31 skipped, all green; scripts/linux-jail-check 108 passed / 2 skipped; a live bh-02 launch with the default jail answered after a cold start, /model both ways and /clear (2.3-3.0 s).
<!-- SECTION:NOTES:END -->
