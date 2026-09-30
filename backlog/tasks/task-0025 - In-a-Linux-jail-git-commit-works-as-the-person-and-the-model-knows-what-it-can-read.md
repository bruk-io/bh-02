---
id: task-0025
title: >-
  In a Linux jail, git commit works as the person and the model knows what it
  can read
status: To Do
assignee: []
created_date: '2026-09-30 01:36'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0019. The Linux jail reads by allowlist and has no home directory, so a jailed git commit fails unless the repository sets its own user.name/user.email, and the model isn't told that a Linux jail reads less than a darwin one (no home directory, only the system tree, the interpreter and the project). It then wastes steps on reads that can't succeed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A jailed cell on Linux can run git commit in the project and the commit carries the person's own name and email, without the jail reading the person's home directory
- [ ] #2 The project context the model is given says, on Linux, what the jail can read and that the home directory is absent
- [ ] #3 Verified in scripts/linux-jail-check; darwin unchanged; scripts/check passes
<!-- AC:END -->
