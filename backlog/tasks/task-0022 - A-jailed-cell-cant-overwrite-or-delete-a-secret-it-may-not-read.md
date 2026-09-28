---
id: task-0022
title: A jailed cell can't overwrite or delete a secret it may not read
status: To Do
assignee: []
created_date: '2026-09-28 13:48'
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
- [ ] #1 spec_for denies writes to every secret that lies under a writable root (e.g. <project>/local.env), and a test pins it
- [ ] #2 A real jailed cell on darwin fails to write or replace the project's local.env, shown by a test that launches the jail
- [ ] #3 On Linux the same holds (scripts/linux-jail-check)
- [ ] #4 scripts/check passes
<!-- AC:END -->
