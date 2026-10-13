---
id: TASK-0072
title: Stop the Backlog CLI rewriting config.yml on every command
status: Done
assignee: []
created_date: '2026-10-10 12:15'
updated_date: '2026-10-10 12:15'
labels:
  - backlog
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Backlog.md 1.53.0 upgrades a config with no `task_prefix` at the start of every command, read-only ones included (`ensureConfigMigrated`: a config without `prefixes` is saved again with `prefixes: {task: "task"}`), and its writer keeps only the keys it knows and the `project_name` its reader stripped of every quote character. So each command rewrote config.yml: `task_prefix` added, the legacy `milestones: []` dropped (milestones are files now), and the apostrophe gone from "Bruk Habtu's Harness".
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 config.yml has `task_prefix: "task"` and no `milestones` key
- [x] #2 A Backlog command leaves config.yml unchanged
- [x] #3 The project name shows with its apostrophe (a typographic one, which the reader leaves alone)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Done in e063b68 (2026-10-10) and logged after the fact, when the owner asked for the work to be on the board, so no separate reviewer closed it. Evidence: after the commit, `backlog task list` left the working tree clean; every Backlog command since (task and draft creates) has left config.yml untouched; `backlog config get projectName` prints "Bruk Habtu’s Harness". The quote stripping itself is Backlog.md's bug; reporting it is a draft of its own.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
config.yml now has `task_prefix: "task"`, no `milestones` key, and a typographic apostrophe in the project name, so the CLI's config upgrade never runs and nothing rewrites the file.
<!-- SECTION:FINAL_SUMMARY:END -->
