---
id: task-0025
title: >-
  In a Linux jail, git commit works as the person and the model knows what it
  can read
status: Done
assignee: []
created_date: '2026-09-30 01:36'
updated_date: '2026-09-30 03:35'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0019. The Linux jail reads by allowlist and has no home directory, so a jailed git commit fails unless the repository sets its own user.name/user.email, and the model isn't told that a Linux jail reads less than a darwin one (no home directory, only the system tree, the interpreter and the project). It then wastes steps on reads that can't succeed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A jailed cell on Linux can run git commit in the project and the commit carries the person's own name and email, without the jail reading the person's home directory
- [x] #2 The project context the model is given says, on Linux, what the jail can read and that the home directory is absent
- [x] #3 Verified in scripts/linux-jail-check; darwin unchanged; scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commits a571b4a, f5b2eb4. On Linux the worker gets GIT_AUTHOR_*/GIT_COMMITTER_* from user.name/user.email as git resolves them on the host for the project: no file written, nothing else of the config carried, and the repo's own identity still wins. Trade-off: a cell can read the name and email from its environment. darwin unchanged. The jail contract gains reads(), which the kernel forwards. context:project now depends on kernel and tells the model which trees the jail reads and that nothing else exists there, home directory included. Per-start directories are written as $TMPDIR so the system prompt stays stable across kernel restarts (a changed prompt restarts Claude Code). Tests: test_a_linux_jailed_git_commit_carries_the_person_s_own_name_without_their_home (real bwrap, red first; the stand-in global config's alias is absent in the jail), test_the_model_is_told_what_a_linux_jail_reads_and_that_the_home_directory_is_absent (red on Linux; on darwin nothing extra is said). Verified after merging into leftovers: scripts/check 1809 passed / 19 skipped, all green; scripts/linux-jail-check 83 passed; pytest -m e2e 16 passed (both live Claude Code tests incl.); a real bh-02 launch in a pty with the default jail answered after a cold start, /model sonnet, /model haiku and /clear (2.0-2.8 s).
<!-- SECTION:NOTES:END -->
