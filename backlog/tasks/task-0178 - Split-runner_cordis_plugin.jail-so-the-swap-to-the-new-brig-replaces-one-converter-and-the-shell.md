---
id: TASK-0178
title: >-
  Split runner_cordis_plugin.jail so the swap to the new brig replaces one
  converter and the shell
status: To Do
assignee: []
created_date: '2026-11-02T17:24:00Z'
labels:
  - runner
  - size-5
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the architecture review of the bh-02/brig seam, 2026-11-02 (TASK-0176). jail.py is about 1,400 lines with 33 exports, and its pure policy functions take and return the old brig's Spec and FsPolicy (spec_for returns a Spec; allowlisted, held and tripwired work on one), so the swap would rewrite nearly every signature. It also re-exports the old brig's group_alive, which app/tests/test_python_repl.py imports, and has two symlink walkers (_links_on_the_way and _linked_dirs) that return different sets for one interpreter.

Proposed, as a no-behaviour change against the old brig (like TASK-0176.06): policy.py, bh-02's own frozen Policy intent type with spec_for, the two lists, link_directories, readable_roots, told_reads and git_author, all pure and importing no brig; a bwrap-translation module (uncovered, mountable, held, tripwired); placeholders.py; a host-facts module (one link walk, the absent sets, the git identity); and the shell (BrigJail, _Jailed). One function converts Policy to the old brig's Spec, so the swap replaces that converter and the shell. Also: move the jail lock (/tmp/bh-02-jails-<uid>.lock) out of shared /tmp to under state_home, where another local user cannot create the name first (reasoned, not measured).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 spec_for returns bh-02's own Policy type, and exactly one function turns it into the old brig's Spec
- [ ] #2 No module but the shell and that converter imports brig
- [ ] #3 No behaviour changes: the runner's tests pass unchanged but for imports, and scripts/check passes
<!-- AC:END -->
