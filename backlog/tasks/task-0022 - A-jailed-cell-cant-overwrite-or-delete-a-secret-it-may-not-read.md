---
id: task-0022
title: A jailed cell can't overwrite or delete a secret it may not read
status: Done
assignee: []
created_date: '2026-09-28 13:48'
updated_date: '2026-09-28 13:56'
labels: []
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found during task-0019: on darwin a jailed cell cannot read the project's local.env (the Claude credential) but can overwrite it, which would destroy or replace the credential bh-02 hands to Claude Code. A path the jail hides from reading should also be protected from writing when it lies under a writable root.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 spec_for denies writes to every secret that lies under a writable root (e.g. <project>/local.env), and a test pins it
- [x] #2 A real jailed cell on darwin fails to write or replace the project's local.env, shown by a test that launches the jail
- [x] #3 On Linux the same holds (scripts/linux-jail-check)
- [x] #4 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commit a7ab43c. spec_for (brig_cordis_plugin/jail.py) adds every read-denied path under a writable root (hide + secrets, e.g. <project>/local.env) to write_denies; test_jail.py::test_the_spec_denies_what_would_reach_outside_the_jail_later pins it. A real darwin jail: app/tests/test_python_cells.py::test_a_jailed_cell_cannot_read_the_project_s_own_local_env_but_reads_beside_it now also tries overwrite, append, os.remove and os.replace over it; all DENIED and the file is unchanged. The test failed with the spec_for change reverted. Linux: bwrap's read mask (--ro-bind /dev/null) already refuses writes and unlink, so allowlisted() drops a write deny that duplicates a read deny, since a write deny on an absent local.env would make bwrap create a local.env directory on the host for the session (test_on_linux_the_policy_reads_by_allowlist_and_keeps_every_deny). scripts/linux-jail-check: 68 passed, including the same four write attempts DENIED. scripts/check: 1788 passed, 14 skipped, all green. Still possible on Linux, as before: a cell can create local.env in a project that has none (it isn't masked when absent; fs_read reports best_effort).
<!-- SECTION:NOTES:END -->
