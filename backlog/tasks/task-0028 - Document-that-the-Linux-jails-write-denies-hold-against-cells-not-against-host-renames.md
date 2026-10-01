---
id: task-0028
title: >-
  Document that the Linux jail's write denies hold against cells, not against
  host renames
status: Done
assignee: []
created_date: '2026-09-30 14:48'
updated_date: '2026-10-01 02:33'
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
- [x] #1 brig-cordis-plugin's README says fs_write is graded enforced on Linux and names exactly what lifts a write deny mid-session (a host rename over the path, removing a placeholder) and how to restore it (/restart kernel)
- [x] #2 brig's own docs for the bwrap mechanism (SPEC.md or README, wherever fs_write grading is described) say the same, so brig's grade isn't read as covering host-side changes
- [x] #3 The session notice that names held paths also mentions that host renames lift write denies, or the notes say why that notice is the wrong place
- [x] #4 No grade changes; scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commit 1229be2. brig-cordis-plugin README, brig SPEC.md (§6, bwrap's grades), brig README and bwrap's fs_write detail text say the grade holds against cells, not the host. A host rename over a denied path (git config, git push -u, an editor's save) or removing a placeholder lifts that deny until a new jail starts (/restart kernel). test_a_linux_write_deny_ends_when_the_host_renames_over_it_until_a_new_jail measures it in a real jail with a host git config over .git/config; it pins a known limit, so it isn't red-first. No grade changed (Bruk, 2026-09-30). Session notice unchanged (AC3): it appears only when a secret is held, while this limit applies to every Linux session, and a blanket line on every session would be ignored. The targeted fix (re-hold, or say so when a denied path's file changes) is tracked separately. Verified after merging into leftovers: scripts/check 1821 passed / 26 skipped, all green; scripts/linux-jail-check 95 passed / 1 skipped; a live bh-02 launch with the default jail answered after a cold start, /model both ways and /clear (2.5-2.6 s), with no jail process left afterwards.
<!-- SECTION:NOTES:END -->
