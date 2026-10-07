---
id: task-0029
title: 'A Linux jail whose bh-02 was killed is ended, not left running'
status: Done
assignee: []
created_date: '2026-09-30 14:48'
updated_date: '2026-10-01 02:33'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0024. If bh-02 is killed (SIGKILL, crash) while a cell's background program runs, its bubblewrap jail keeps running with its mounts. The next session's sweep correctly leaves it and its placeholders alone, but nothing ever ends it, so a program the person thought stopped with bh-02 keeps running with project write access.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A jail's processes end when the bh-02 that started them dies, however it dies; a real-bwrap test kills bh-02 with SIGKILL while a cell's background program runs and shows the program gone
- [x] #2 After that, the next session's sweep removes the dead jail's placeholders and record
- [x] #3 darwin gets the same guarantee (a real seatbelt test), or the notes say why it already holds
- [x] #4 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commit 550fe84. brig ties a jail's life to its launcher (SPEC.md §8, decision-167): bh-02 holds one end of a pipe, and a watcher in the jail's process group holds the other and SIGKILLs the group on EOF. The kernel closes bh-02's end however bh-02 dies, SIGKILL included. Not bwrap --die-with-parent: bwrap's parent is brig's detached exit wrapper, which outlives bh-02, and the parent-death signal follows the launching thread (a worker thread here). Tests: libs/brig/tests/integration/test_tether.py (SIGKILLed launcher -> group gone; an untethered control survives; SIGINT doesn't end the watcher; kill still verifies the group empty). test_a_killed_bh_02_s_jail_ends_with_it_and_the_next_jail_removes_what_it_left (real bwrap: a real cell's setsid background program is gone after SIGKILL, and the next sweep removes the placeholders and record). test_a_killed_bh_02_s_seatbelt_jail_ends_with_it_but_not_a_program_that_left_its_group (real seatbelt). Red-first was shown by deliberate breaks, then reverted. darwin limit (AC3 met by giving the reason): seatbelt has no namespace, so a program that leaves the group (setsid, a double-forking daemon) survives a killed bh-02, and a normal stop and /restart kernel too (brig's teardown is group-shaped). Measured before and after; documented in the README; tracked as its own task. --no-jail background programs also outlive a killed bh-02 (out of scope). Verified after merging into leftovers: scripts/check 1821 passed / 26 skipped, all green; scripts/linux-jail-check 95 passed / 1 skipped; a live bh-02 launch with the default jail answered after a cold start, /model both ways and /clear (2.5-2.6 s), with no jail process left afterwards.
<!-- SECTION:NOTES:END -->
