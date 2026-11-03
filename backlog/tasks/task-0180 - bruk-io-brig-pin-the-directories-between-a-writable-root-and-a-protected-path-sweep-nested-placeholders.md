---
id: TASK-0180
title: >-
  bruk-io/brig: pin the directories between a writable root and a protected
  path; sweep nested placeholders
status: Done
assignee: []
created_date: '2026-11-03T04:48:00Z'
updated_date: '2026-11-03T05:33:00Z'
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
- [x] #1 brig pins the directories between a writable root and a write deny or mask, with a test that renames each and fails if one succeeds
- [x] #2 brig's placeholder sweep keeps a directory it could not remove in the record, with a test that sweeps a dead record made before a live one's nested ones
- [x] #3 bh-02's pin to brig moves to the commit that closes both and the four xfail tests are plain tests
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed in bruk-io/brig and closed there by reviewers: the pins are brig TASK-0001.31 (deny or mask) and TASK-0001.33 (a readable root nested in a writable one, found while fixing .31); the sweep is TASK-0001.32. brig is pinned to 0237986 (claude/embedder-gaps), which also gives ChannelDirectoryCreateFailed a message that says what to check. The four xfail(strict) tests are plain tests and pass; the killed-bh-02 test no longer tolerates a left .git (6/6 runs clean); the runner README's known gaps are down to darwin. scripts/check at this commit: exit 0, 2577 passed, 6 skipped.

Check `scripts/check` exited 0

(10 earlier lines omitted)
```text
== tests
bringing up nodes...
bringing up nodes...

........................................................................ [  2%]
........................................................................ [  5%]
....s................................................................... [  8%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 19%]
.......................s................................................ [ 22%]
........................................................................ [ 25%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 36%]
....s..s................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 47%]
........................................................................ [ 50%]
........................................................................ [ 53%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 75%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 89%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 97%]
.............................................................            [100%]
2577 passed, 6 skipped in 152.25s (0:02:32)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02-swap/site
INFO    -  Documentation built in 4.94 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

No repro: the failures are brig's, and their repros are recorded failing before the fix on brig's board (TASK-0001.31 #2, TASK-0001.32 #3, TASK-0001.33 #2). bh-02's side was the four xfail(strict) tests, which xfail-passed against 2132b3b (strict, so they failed as expected) and now run as plain tests and pass at 0237986.

Closed by review. Full check (record-check --tier full): exit 0, 2577 passed, 6 skipped. #1 and #2: brig TASK-0001.31/.32/.33 closed by reviewers with repros recorded failing before the fix; pinned 0237986 contains them. #3: pin moved, the four xfail(strict) markers removed with test bodies unchanged; the killed-jail test was strengthened (no .git exception), not weakened. No findings.
<!-- SECTION:NOTES:END -->
