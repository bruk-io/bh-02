---
id: task-0024
title: >-
  Linux jail placeholders never outlive the sessions that made them or get in
  the person's way
status: Done
assignee: []
created_date: '2026-09-30 01:36'
updated_date: '2026-09-30 03:35'
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
- [x] #1 Placeholders left by a session that crashed are removed by the next bh-02 jail start once no other bh-02 jail is running, and only placeholders a jail made (never a path the person created); a test covers it
- [x] #2 In a project that isn't a git repository, git init on the host succeeds while a Linux session runs, or the placeholder that blocks it is no longer created
- [x] #3 brig-cordis-plugin's README says what a placeholder is, when it exists on the host, and that removing one mid-session lifts its deny
- [x] #4 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commits fdb4a0e, f5b2eb4. Each Linux jail writes a record under $XDG_STATE_HOME/bh-02/jails/ before bwrap runs (its placeholders, then bwrap's process group) and marks each placeholder with xattr user.bh-02.placeholder=<jail id>, falling back to inode + ctime. A jail that takes the lock exclusively at start sweeps stale records, removing only empty directories still marked as that jail's and skipping any record whose process group is alive. A killed bh-02 can leave its bwrap running with its mounts, and removing its placeholders let a background program write .claude/settings.json on the host (measured, then fixed). The xattr exists because overlayfs reused an inode for a directory the person recreated. An absent deny with an absent parent is held at the topmost absent ancestor, so in a non-git project the jail holds .git/ itself and a host git init works. README and GLOSSARY explain placeholders, and that removing one mid-session lifts its deny. Real-bwrap tests: test_placeholders_a_crashed_session_left_are_removed_by_the_next_jail_and_only_those (red first), test_git_init_on_the_host_works_while_a_jail_runs_in_a_project_that_is_no_repository (red first), test_a_killed_session_s_jail_that_lives_on_keeps_its_placeholders (red against the first sweep). Open: a killed session's jail with a live background program is never ended; a crash between writing the record and starting bwrap leaves a paths-only record, whose empty directories the next sweep removes. Verified after merging into leftovers: scripts/check 1809 passed / 19 skipped, all green; scripts/linux-jail-check 83 passed; pytest -m e2e 16 passed (both live Claude Code tests incl.); a real bh-02 launch in a pty with the default jail answered after a cold start, /model sonnet, /model haiku and /clear (2.0-2.8 s).
<!-- SECTION:NOTES:END -->
