---
id: DRAFT-0028
title: >-
  The pytest basetemp under ~/.cache is shared by every run of a checkout and
  never cleared
status: Draft
assignee: []
created_date: '2026-11-04T17:33:00Z'
labels:
  - runner
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0181.02 set the root conftest's basetemp to $XDG_CACHE_HOME/bh-02-pytest/<checkout name>. pytest empties a given --basetemp at the start of each run, so two pytest runs in one checkout at once (scripts/check on a member while another run is going, a lead and a worker in the same tree) delete each other's tmp_path mid-test; pytest's default numbered dirs (pytest-of-<user>/pytest-N) never had that. Two checkouts with the same directory name in different places share one too. And what a run leaves stays in the person's ~/.cache with no cleanup: 67M after one review run here, one more directory for every worktree name, where /tmp was cleared by the host.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Two pytest runs in one checkout at once don't remove each other's tmp_path
- [ ] #2 A run's leftovers under the cache are bounded (pytest's keep-3 numbered dirs, or removed), and checkouts that share a name don't share a directory
<!-- AC:END -->
