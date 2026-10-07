---
id: task-0033
title: On Linux a cell can't write .git/config after a host git command rewrites it
status: Done
assignee: []
created_date: '2026-10-01 02:33'
updated_date: '2026-10-02 03:26'
labels: []
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0028. Common host git commands (git config, git push -u, git remote add) rewrite .git/config by rename. On Linux that detaches the jail's read-only mount, so for the rest of the session a cell can write .git/config, including core.hooksPath or an alias, which runs code on the host the next time the person uses git. The deny is meant to stop exactly that. Measured by test_a_linux_write_deny_ends_when_the_host_renames_over_it_until_a_new_jail; fs_write stays graded enforced (Bruk's decision), so the fix must make the deny hold again rather than change the grade.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After a host git config (or any rename over .git/config) mid-session, a jailed cell's next write to .git/config is refused; a real-bwrap test shows it
- [x] #2 The same holds for every write-denied path a host tool commonly rewrites by rename (at least .git/config and the layer files); the notes list which paths are covered and how
- [x] #3 No cell gets a window between the host rename and the deny holding again, or the window is measured and stated in the README
- [x] #4 darwin unchanged; scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commits a11f70e, bc84fa7. Rejected, each measured in the container: read-only .git with writable carve-outs (a jailed git commit fails: can't create .git/index.lock, read-only file system); re-mounting from outside (setns into the jail's mount namespace gives EPERM, since bwrap nests it in a user namespace bh-02 has no rights in); ending on config.lock creation (no measurable gain, and it would blame the host for a cell's own git config). Built: brig_cordis_plugin/tripwire.py watches, with inotify, the directory of every held path and kills the jail's processes on the first replace, move-away, remove or create of one. The kernel client notices a worker that died between cells and starts a new one before the next cell, and that jail holds the path again. The person is told why ('the kernel was started again, because something on the host replaced or removed .../.git/config'); a running cell ends with 'the kernel process ended during this cell because ...'. The Jailed contract gains ended() (CONTRACTS.md). fs_write stays enforced. Cost: the kernel's variables are lost whenever the host rewrites a held path mid-session (git config, git push -u, a layer saved by rename, editing local.env). Window from host rename to jail gone, two runs of 20: idle median 0.9-2.3 ms, worst 1.4-10 ms; with another thread busy, median 20-72 ms, worst 35-186 ms. A background program retrying in a tight loop gets a write in 19-20 of 20 times, and also through git's own .git/config.lock, which git renames into place. A cell that isn't running at that moment never gets in. The README says this and advises stopping the reply or /release before such host commands. Second hole found and fixed in brig (decision-168, SPEC.md §6): a cell could rename .git away (taking the mounts with it) and plant a new .git/config with core.hooksPath. bwrap now binds every existing directory between the project and a denied path over itself, so those directories can't be renamed or removed but stay writable, and a jailed git commit still works. Cost: os.rename across such a directory and the rest of the project fails with EXDEV (mv and shutil.move copy instead). darwin: seatbelt denies the path itself, so nothing can be planted (measured), and a host git config lifts nothing (real seatbelt test). All new Linux tests were red first, and the pinning tests were red with pinning off. Verified after merging into leftovers: scripts/check 1830 passed / 31 skipped, all green; scripts/linux-jail-check 108 passed / 2 skipped; a live bh-02 launch with the default jail answered after a cold start, /model both ways and /clear (2.3-3.0 s).
<!-- SECTION:NOTES:END -->
