---
id: task-0026
title: CI runs the Linux jail check on every push
status: Done
assignee: []
created_date: '2026-09-30 01:36'
updated_date: '2026-09-30 01:49'
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
- [x] #1 A GitHub Actions workflow runs brig's bwrap tests and the bh-02 jail tests on a Linux runner with real bubblewrap, on push and pull request
- [x] #2 The workflow has run green on GitHub at least once, with the run linked in the task notes
- [x] #3 What the runner needed (packages, sysctls, Python 3.15) is written in the workflow or its comments
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
.github/workflows/linux-jail.yml (b58d126, comment corrected after): on push and pull_request, ubuntu-24.04 runs scripts/linux-jail-check, the same script used locally (Docker container: Ubuntu 24.04, bubblewrap, uv, Python 3.15, non-root). The runner needed: setup-uv (the script is a PEP 723 uv script) and kernel.apparmor_restrict_unprivileged_userns=0 as a precaution (not tried without it). First run failed before any test: the script passed bsdtar-only --no-mac-metadata to GNU tar; fixed so those flags apply only on darwin. Green run: https://github.com/bruk-io/bh-02/actions/runs/36656730984 (68 passed, same as local). The git-pinned dev deps (mypy, pypeeker) are public, so no secrets needed.
<!-- SECTION:NOTES:END -->
