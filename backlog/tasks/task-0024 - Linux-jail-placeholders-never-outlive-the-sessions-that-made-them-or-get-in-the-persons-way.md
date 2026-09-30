---
id: task-0024
title: >-
  Linux jail placeholders never outlive the sessions that made them or get in
  the person's way
status: To Do
assignee: []
created_date: '2026-09-30 01:36'
labels: []
dependencies:
  - task-0023
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0019. bubblewrap needs a mount point for each absent write-denied path (.envrc, .vscode, .git/hooks, ...), so the Linux jail creates empty directories on the host and removes them when the last bh-02 jail of the user stops. If bh-02 crashes, they stay behind for good: the next session sees them as existing paths and never removes them. While a session runs they also get in the way on the host (in a project that isn't a git repo, a host git init fails), and deleting one mid-session quietly lifts that deny inside the jail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Placeholders left by a session that crashed are removed by the next bh-02 jail start once no other bh-02 jail is running, and only placeholders a jail made (never a path the person created); a test covers it
- [ ] #2 In a project that isn't a git repository, git init on the host succeeds while a Linux session runs, or the placeholder that blocks it is no longer created
- [ ] #3 brig-cordis-plugin's README says what a placeholder is, when it exists on the host, and that removing one mid-session lifts its deny
- [ ] #4 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
