---
id: DRAFT-0022
title: >-
  Runner adapter tidy-up after the swap: tripwire from brig's mounts, masks
  outside roots, is_confined's premise, Started's full contract
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - runner
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 of the runner's seam with brig. (1) mounts.tripwired/held rebuild brig's mount plan by hand and miss brig's pins; arm the tripwire from Jail.mounts (or ask brig to export held paths). (2) allowlisted passes CREDENTIALS masks outside every root, so brig mounts them and fs_read stays best_effort for good; drop masks under no root (and brig's _kept should skip them). (3) is_confined accepts fs_write best_effort from any runner on the premise of the tripwire; add a bh-02 axis (host_undo: tripwired) and accept best_effort only with it. (4) runner.Started omits interrupt, ended, reads, writes that CONTRACTS.md promises and python's client uses; declare the full contract. (5) README says channel_exclusivity is violated only for /tmp roots; brig violates it for any writable root; tui has no glyph for violated. (6) duplicates and dead code: _WHOLE_HOST copies brig's WHOLE_HOST_READ_ONLY; interpreter link trees exist only for brig's interpreter check (brig should add its own interpreter's chain); ReadModel.DENYLIST and the darwin notice branch serve a seatbelt design that does not exist. (7) test_runner_confined parses brig's private placeholder records. Minor: README's endpoint location, client.py's 'brig's trusted', a stale brig commit in a test comment, UNENFORCED's limits/control, released_for in mounts.py.
<!-- SECTION:DESCRIPTION:END -->
