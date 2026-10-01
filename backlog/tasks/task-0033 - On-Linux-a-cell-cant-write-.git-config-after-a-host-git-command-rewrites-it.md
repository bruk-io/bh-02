---
id: task-0033
title: On Linux a cell can't write .git/config after a host git command rewrites it
status: To Do
assignee: []
created_date: '2026-10-01 02:33'
labels: []
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0028. Common host git commands (git config, git push -u, git remote add) rewrite .git/config by rename. On Linux that detaches the jail's read-only mount, so for the rest of the session a cell can write .git/config, including core.hooksPath or an alias, which runs code on the host the next time the person uses git. The deny is meant to stop exactly that. Measured by test_a_linux_write_deny_ends_when_the_host_renames_over_it_until_a_new_jail; fs_write stays graded enforced (Bruk's decision), so the fix must make the deny hold again rather than change the grade.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After a host git config (or any rename over .git/config) mid-session, a jailed cell's next write to .git/config is refused; a real-bwrap test shows it
- [ ] #2 The same holds for every write-denied path a host tool commonly rewrites by rename (at least .git/config and the layer files); the notes list which paths are covered and how
- [ ] #3 No cell gets a window between the host rename and the deny holding again, or the window is measured and stated in the README
- [ ] #4 darwin unchanged; scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
