---
id: TASK-0184
title: host.key_envs is computed once from the default models file
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T12:39:00Z'
labels:
  - models
  - credentials
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: bh_02/cli.py computes key_envs at boot from the models file's default path only, with the app's own parser (bootstrap.py), separate from the models plugin's. A layer pointing the model row at another models file, or an endpoint added mid-session, gives a key variable runner:confined won't refuse and ! commands pass through. Proposed: models:catalog provides key_envs() read fresh, and the runner and shell_command ask it at each start (the catalog depends only on loader, so no new reloads). Related unguarded rules: runs='memory'/'harness' honoured from any row (a pypeeker rule could restrict the literals), and system/asides contributors must not need the event loop.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The runner refuses, and ! withholds, every key variable of every endpoint the model row can reach: the default models file, the row's models file and its extra endpoints; repro test: a layer pointing the model row at another file whose key is { env = 'OTHER_KEY' } with runner.toml listing OTHER_KEY is refused
- [ ] #2 The set is read fresh at each start, so an endpoint added mid-session counts; tested
- [ ] #3 The draft's related unguarded rules move to drafts of their own
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
