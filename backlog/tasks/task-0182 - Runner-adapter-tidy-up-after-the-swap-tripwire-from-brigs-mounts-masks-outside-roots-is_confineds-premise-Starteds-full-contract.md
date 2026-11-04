---
id: TASK-0182
title: >-
  Runner adapter tidy-up after the swap: tripwire from brig's mounts, masks
  outside roots, is_confined's premise, Started's full contract
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T03:32:00Z'
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
- [ ] #1 The tripwire is armed from brig's Jail.mounts, not a recomputed plan: every read-only mount beneath a writable one and every rename pin; a real-jail test renames a pinned directory on the host and the jail ends
- [ ] #2 CREDENTIALS masks under no readable or writable root are not passed to brig; a test shows fs_read for a typical project is no longer capped by them
- [ ] #3 is_confined accepts fs_write best_effort only when the runner's report also carries bh-02's own host_undo: tripwired (set by the confined runner that arms one); a report without it is not confined, with a test
- [ ] #4 runner.Started declares the whole contract CONTRACTS.md promises (interrupt, ended, reads, writes and the rest), and mypy holds both runners to it
- [ ] #5 Dead and duplicated code is gone: _WHOLE_HOST (use brig's WHOLE_HOST_READ_ONLY), the darwin denylist model and its notice branch, and the test that parses brig's private placeholder records; README's channel_exclusivity and endpoint lines, client.py's 'brig's trusted', and the stale brig commit in a test comment are corrected; tui shows a glyph for violated
- [ ] #6 scripts/check and scripts/linux-jail-check (both modes) pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: criteria written right after promotion (finish-moved for that reason only). The owner agreed today to keep fs_write best_effort counting as confined; criterion 1 closes the tripwire's known gap over brig's pins, criterion 3 makes the rule's premise explicit. bh-02 keeps its brig pin (1c7c8d4) here: moving it to brig's honest network grade is the capability-grants intent's work (TASK-0181).
<!-- SECTION:NOTES:END -->
