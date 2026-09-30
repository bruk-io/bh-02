---
id: task-0028
title: >-
  Document that the Linux jail's write denies hold against cells, not against
  host renames
status: To Do
assignee: []
created_date: '2026-09-30 14:48'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0023/0024. On Linux, bubblewrap enforces a write deny with a mount. If something on the host renames a new file over a denied path (a host git config rewrites .git/config that way; editors save by rename) or removes a placeholder, the mount detaches inside the jail and the deny is lifted until the kernel restarts. Decided 2026-09-30 (Bruk): fs_write stays graded enforced, because downgrading it would mark the jail as not confined and make every cell ask for approval. The limit must be written down where a reader of the grade will find it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 brig-cordis-plugin's README says fs_write is graded enforced on Linux and names exactly what lifts a write deny mid-session (a host rename over the path, removing a placeholder) and how to restore it (/restart kernel)
- [ ] #2 brig's own docs for the bwrap mechanism (SPEC.md or README, wherever fs_write grading is described) say the same, so brig's grade isn't read as covering host-side changes
- [ ] #3 The session notice that names held paths also mentions that host renames lift write denies, or the notes say why that notice is the wrong place
- [ ] #4 No grade changes; scripts/check passes
<!-- AC:END -->
