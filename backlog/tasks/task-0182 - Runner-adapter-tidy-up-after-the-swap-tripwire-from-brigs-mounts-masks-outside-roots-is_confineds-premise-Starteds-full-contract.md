---
id: TASK-0182
title: >-
  Runner adapter tidy-up after the swap: tripwire from brig's mounts, masks
  outside roots, is_confined's premise, Started's full contract
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T04:16:00Z'
labels:
  - runner
  - size-3
  - finish-moved
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 of the runner's seam with brig. (1) mounts.tripwired/held rebuild brig's mount plan by hand and miss brig's pins; arm the tripwire from Jail.mounts (or ask brig to export held paths). (2) allowlisted passes CREDENTIALS masks outside every root, so brig mounts them and fs_read stays best_effort for good; drop masks under no root (and brig's _kept should skip them). (3) is_confined accepts fs_write best_effort from any runner on the premise of the tripwire; add a bh-02 axis (host_undo: tripwired) and accept best_effort only with it. (4) runner.Started omits interrupt, ended, reads, writes that CONTRACTS.md promises and python's client uses; declare the full contract. (5) README says channel_exclusivity is violated only for /tmp roots; brig violates it for any writable root; tui has no glyph for violated. (6) duplicates and dead code: _WHOLE_HOST copies brig's WHOLE_HOST_READ_ONLY; interpreter link trees exist only for brig's interpreter check (brig should add its own interpreter's chain); ReadModel.DENYLIST and the darwin notice branch serve a seatbelt design that does not exist. (7) test_runner_confined parses brig's private placeholder records. Minor: README's endpoint location, client.py's 'brig's trusted', a stale brig commit in a test comment, UNENFORCED's limits/control, released_for in mounts.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The tripwire is armed from brig's Jail.mounts, not a recomputed plan: every read-only mount beneath a writable one and every rename pin; a real-jail test renames a pinned directory on the host and the jail ends
- [x] #2 CREDENTIALS masks under no readable or writable root are not passed to brig; a test shows fs_read for a typical project is no longer capped by them
- [x] #3 is_confined accepts fs_write best_effort only when the runner's report also carries bh-02's own host_undo: tripwired (set by the confined runner that arms one); a report without it is not confined, with a test
- [x] #4 runner.Started declares the whole contract CONTRACTS.md promises (interrupt, ended, reads, writes and the rest), and mypy holds both runners to it
- [x] #5 Dead and duplicated code is gone: _WHOLE_HOST (use brig's WHOLE_HOST_READ_ONLY), the darwin denylist model and its notice branch, and the test that parses brig's private placeholder records; README's channel_exclusivity and endpoint lines, client.py's 'brig's trusted', and the stale brig commit in a test comment are corrected; tui shows a glyph for violated
- [x] #6 scripts/check and scripts/linux-jail-check (both modes) pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1 mounts/tripwire: arm from Jail.mounts (RO beneath WRITABLE + writable pins); drop held/tripwired; 2 allowlisted drops masks under no root; 3 host_undo=tripwired in PLANNED and each confined start, is_confined requires it for fs_write best_effort; 4 Started gets interrupt/ended/reads/writes; 5 remove _WHOLE_HOST, ReadModel.DENYLIST, darwin notice branch, placeholder-parsing test, fix docs, tui violated glyph; 6 tests (planted failures), scripts/check, linux-jail-check both modes
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: criteria written right after promotion (finish-moved for that reason only). The owner agreed today to keep fs_write best_effort counting as confined; criterion 1 closes the tripwire's known gap over brig's pins, criterion 3 makes the rule's premise explicit. bh-02 keeps its brig pin (1c7c8d4) here: moving it to brig's honest network grade is the capability-grants intent's work (TASK-0181).

Claude 2026-11-04: (1) mounts.tripwired(Jail.mounts) = READ_ONLY mounts beneath a WRITABLE one + WRITABLE beneath WRITABLE (pins); jail.py arms Tripwire from it; mounts.held/old tripwired and ReadModel gone. Real-jail test renames pinned dir 'a' (deny a/b/c) on the host, jail ends. (2) allowlisted drops masks under no readable/writable root; real-jail test: fs_read enforced for a typical project. (3) HOST_UNDO='host_undo': 'tripwired' in PLANNED and every confined start's report; is_confined requires it for fs_write best_effort (test_best_effort_writes_are_not_confined_without...). (4) runner.Started now declares interrupt, ended, reads, writes; mypy strict green, test asserts isinstance(started, Started). (5) removed _WHOLE_HOST, ReadModel/DENYLIST, darwin notice branch, placeholder-record parsing (replaced by ps-seen jail groups); README endpoint+channel_exclusivity lines, client.py 'brig's trusted', stale brig commit in test comment fixed; tui glyph ! for violated (+test). Planted failures seen: with pins dropped from tripwired, masks filter removed and the is_confined guard disabled, 7 tests failed (pin-rename, typical-project reads, approval, mask/tripwire unit tests); restored, all pass. Fixed app test test_a_jailed_input_cannot_read_under_the_sessions_state_directory (a secret outside every root is now absent, not an empty dir: listdir raises). Checks: scripts/check for runner (with gates+docs), tui, python, app (--no-gates --no-docs) exit 0; scripts/arch-check --no-fix exit 0; scripts/linux-jail-check and --as-root both exit 0 (364 passed, 1 skipped, 1 xfailed each; no DRAFT-0026 flake). AC6 left unticked: the full scripts/check is the reviewer's.

Check `scripts/check` exited 0

(10 earlier lines omitted)
```text
== tests
bringing up nodes...
bringing up nodes...

........................................................................ [  2%]
........................................................................ [  5%]
....s................................................................... [  8%]
..x..................................................................... [ 11%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 19%]
........................s............................................... [ 22%]
........................................................................ [ 25%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 36%]
............s..s........................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 47%]
........................................................................ [ 50%]
........................................................................ [ 52%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 94%]
........................................................................ [ 97%]
.......................................................................  [100%]
2586 passed, 6 skipped, 1 xfailed in 174.88s (0:02:54)
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
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 4.02 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
