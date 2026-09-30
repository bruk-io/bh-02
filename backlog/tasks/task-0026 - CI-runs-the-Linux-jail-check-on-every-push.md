---
id: task-0026
title: CI runs the Linux jail check on every push
status: To Do
assignee: []
created_date: '2026-09-30 01:36'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0019. The Linux jail has only been verified in a local Docker container (scripts/linux-jail-check) and never on a CI runner, so a regression in the bwrap path would go unnoticed on a mac-only workflow.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A GitHub Actions workflow runs brig's bwrap tests and the bh-02 jail tests on a Linux runner with real bubblewrap, on push and pull request
- [ ] #2 The workflow has run green on GitHub at least once, with the run linked in the task notes
- [ ] #3 What the runner needed (packages, sysctls, Python 3.15) is written in the workflow or its comments
<!-- AC:END -->
