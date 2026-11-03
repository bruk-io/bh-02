---
id: TASK-0180
title: >-
  bruk-io/brig: pin the directories between a writable root and a protected
  path; sweep nested placeholders
status: To Do
assignee: []
created_date: '2026-11-03T04:48:00Z'
labels:
  - brig
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the Linux half of TASK-0176.07 (branch claude/swap-linux). Against the pinned brig (2132b3b) two gaps the old brig did not have. (1) The old brig's decision-168 bound every existing directory between a write root and a deny or mask over itself, so rename(2) refused it. The new one does not: an input can rename the directory a layer file, .git/config, a trusted config directory or the interpreter's link is in (project/uv, project/venv, home/xdg) and plant its own at the old name; the next uv run, bh-02 start or session on the host uses it. Planted: three xfail(strict) tests in bh-02 name it (test_runner_confined.py: refuses a rename of a directory on the way to the interpreter; test_python_repl.py: can't choose what a later session reads, moving the directory a git config is in, a layer file's directory). (2) placeholders.release forgets a directory it cannot remove (rmdir fails, OSError, continue) and still deletes the record, so when a crashed jail's record made .git and the next jail's made .git/hooks and .git/config, a sweep that reads the dead record first leaves .git for good (about half the runs of test_a_killed_bh_02_s_jail_ends_with_it...). Both are bruk-io/brig's board; this task is the filing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 brig pins the directories between a writable root and a write deny or mask, with a test that renames each and fails if one succeeds
- [ ] #2 brig's placeholder sweep keeps a directory it could not remove in the record, with a test that sweeps a dead record made before a live one's nested ones
- [ ] #3 bh-02's pin to brig moves to the commit that closes both and the four xfail tests are plain tests
<!-- AC:END -->
