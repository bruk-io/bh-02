---
id: task-0012
title: Commit the working tree in reviewable pieces
status: Done
assignee: []
created_date: '2026-09-23 01:43'
updated_date: '2026-09-23 01:56'
labels:
  - repo
milestone: M1 Commit the work so far
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The tree holds uncommitted warden work, the brig import, and task-0009/0010/0011. Commit them as separate, reviewable commits before anything moves.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 warden's changes are a commit of their own, containing nothing else
- [x] #2 brig's import is a commit of its own
- [x] #3 task-0009, task-0010 and task-0011 each land as their own commit(s)
- [x] #4 Every commit leaves pytest, ruff, mypy and scripts/arch-check green
- [x] #5 git status is clean afterwards
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Replayed the session's checkpoints (tracked-file patch + untracked tarball, each green when taken) in a separate worktree on a new branch `bh-02` (not the default branch). Commits: 944058d warden alone (the warden-only state reconstructed by removing brig from checkpoint 00; its diff stat matched the warden changes present at session start: CLAUDE.md 3, bhh.py 5, pyproject 21, uv.lock 80; 554 tests), 69501b7 brig (1327 tests incl. brig's), 71faa33 task-0009 (1387), 84d4508 task-0010 (1416), cd3a824 task-0011 (1421), c6b7763 milestones. Each state: pytest, ruff, mypy and arch-check green. Main's working tree was then byte-identical to cd3a824 plus the milestone files (checked through a temporary index), so the checkout was switched to bh-02 in place (symbolic-ref + reset) and the worktree removed. `main` is untouched at e59a0fd for the owner to merge. Note: the backlog MCP auto-commits task files as it goes, onto whatever branch is checked out.
<!-- SECTION:NOTES:END -->
