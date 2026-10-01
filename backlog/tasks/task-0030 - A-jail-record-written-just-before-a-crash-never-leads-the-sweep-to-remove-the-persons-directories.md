---
id: task-0030
title: >-
  A jail record written just before a crash never leads the sweep to remove the
  person's directories
status: Done
assignee: []
created_date: '2026-09-30 14:48'
updated_date: '2026-10-01 02:33'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0024. A Linux jail writes its record (the placeholders it will make) before bubblewrap starts, and marks each placeholder only once the jail is up. If bh-02 crashes between the two, the record holds paths without marks, and the next sweep removes any empty directory at those paths, which could be one the person created in the meantime.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The sweep removes a directory only when it can prove the jail made it; a record with unmarked paths removes nothing it can't prove
- [x] #2 A test writes such a record, has the person create an empty directory at one of its paths, and shows the sweep leaves it
- [x] #3 A crash in that window still leaves nothing behind that stays forever, or the notes say what remains and why that's acceptable
- [x] #4 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commits aadca1b, 85a4bec. A record entry with no mark proves nothing and is left alone. The jail now makes its placeholders itself before bwrap starts: write the record naming each path by the mark it will carry, mkdir, mark at once, rewrite the record. A launch that fails or is cancelled removes what it made; a cancelled start waits for the launch thread before closing fds. Tests (red first): test_a_record_with_unmarked_paths_removes_nothing_it_can_t_prove (the person's empty directory is left), test_a_placeholder_is_made_and_marked_before_bubblewrap_starts, test_a_jail_that_fails_to_launch_leaves_nothing_on_the_host, test_a_jail_start_cancelled_while_it_launches_ends_what_the_launch_started. Two existing tests changed on purpose (the old behaviour removed path-only entries). _place and _clear_up joined the purity budget. What can remain (AC3): an empty unmarked directory if bh-02 dies between mkdir and setting the xattr (two syscalls), or, without xattrs, between mkdir and the record rewrite. It's never removed automatically, because the alternative risks removing the person's own directory, and a later jail binds it read-only, so the deny still holds. The README says to remove it by hand. The no-xattr fallback has not run in a real jail. Verified after merging into leftovers: scripts/check 1821 passed / 26 skipped, all green; scripts/linux-jail-check 95 passed / 1 skipped; a live bh-02 launch with the default jail answered after a cold start, /model both ways and /clear (2.5-2.6 s), with no jail process left afterwards.
<!-- SECTION:NOTES:END -->
