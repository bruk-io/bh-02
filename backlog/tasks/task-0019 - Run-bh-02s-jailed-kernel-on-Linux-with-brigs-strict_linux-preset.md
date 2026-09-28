---
id: task-0019
title: Run bh-02's jailed kernel on Linux with brig's strict_linux preset
status: Done
assignee: []
created_date: '2026-09-28 12:26'
updated_date: '2026-09-28 13:48'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
brig:jail only runs on darwin (seatbelt); elsewhere it refuses and points at kernel:unjailed. brig already has a Linux stack (strict_linux: bwrap, rlimits, env scrub), but it reads by allowlist and has never run under bh-02, whose kernel needs the interpreter's whole tree readable. A Linux user should get the same jail guarantees as a darwin user.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 On Linux with bwrap, brig:jail starts the kernel and a cell can import the standard library and project code and write under the project root
- [x] #2 In the Linux jail a cell cannot write the layer files, the host's import paths or brig's self-modify list, cannot read local.env or the sessions' state, and has no network
- [x] #3 Verified by a real bwrap run (e.g. in a Linux container), not only by compile-path unit tests; the run is reproducible from a script or documented command
- [x] #4 darwin behaviour is unchanged and scripts/check passes on darwin
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commits a3df5b0..31e91b4, merged into leftovers. brig: read carve-outs under an allowlist Spec (decision-164; a carve-out that exists is hidden by bwrap, an absent one drops fs_read to best_effort and names the path); only write carve-outs a writable tree reaches are mounted (decision-165; mounting others exposed paths the allowlist left out); the jail's own root is remounted read-only last (decision-166; writes outside the writable roots used to land in the scratch root). Plugin: on Linux spec_for is allowlisted (/usr /bin /sbin /lib /lib64 /etc, the interpreter incl. the uv venv's symlinked dir, the worker, the writable roots) with every read and write deny kept. It refuses with a message naming kernel:unjailed when bwrap is missing or the platform is unsupported. The empty placeholders bwrap creates are cleaned up only when no other bh-02 jail of the same user is running (test). A .git file (worktree/submodule) is made read-only instead of .git/hooks (test). Both tests fail with their fix reverted. Verified by me after the merge: scripts/linux-jail-check -> 68 passed (Ubuntu 24.04 container, real bwrap, non-root; docker needs seccomp/apparmor/systempaths=unconfined and --init). scripts/check on darwin -> 1788 passed, 14 skipped, all steps green. Known limits, Linux only: placeholders exist on the host while a session runs (a host git init in a non-repo project fails meanwhile) and can be left after a crash, and deleting one mid-session lifts that deny; a secret created after the kernel starts is readable until it restarts; there is no home directory in the jail, so git commit needs repo-level user.name/email. Never compared with a CI runner.
<!-- SECTION:NOTES:END -->
