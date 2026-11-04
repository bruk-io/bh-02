---
id: TASK-0184
title: host.key_envs is computed once from the default models file
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - models
  - credentials
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: bh_02/cli.py computes key_envs at boot from the models file's default path only, with the app's own parser (bootstrap.py), separate from the models plugin's. A layer pointing the model row at another models file, or an endpoint added mid-session, gives a key variable runner:confined won't refuse and ! commands pass through. Proposed: models:catalog provides key_envs() read fresh, and the runner and shell_command ask it at each start (the catalog depends only on loader, so no new reloads). Related unguarded rules: runs='memory'/'harness' honoured from any row (a pypeeker rule could restrict the literals), and system/asides contributors must not need the event loop.
<!-- SECTION:DESCRIPTION:END -->
