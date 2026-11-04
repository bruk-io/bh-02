---
id: DRAFT-0027
title: key_envs() drops the variable of a key table that has another problem
status: Draft
assignee: []
created_date: '2026-11-04T13:25:00Z'
labels:
  - models
  - credentials
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
models:catalog.key_envs() (catalog.py) uses key_spec(), which returns None for any key table _read_key rejects, so key = { env = "MY_KEY", ttl_ms = 5 } or one with an unknown field counts no variable. Its docstring and CONTRACTS.md say 'whatever else is wrong with a table', and the removed bootstrap.key_variables counted any string env. The provider refuses such a key, so bh-02 sends nothing, but the person has named MY_KEY as a key: if it is also in runner.toml the jail gets it and ! passes it to the model's output. That fails open on a credential rule, where the rest of the change fails closed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 key_envs() counts a string key.env whatever else is wrong with its key table; tested with ttl_ms on an env key and with an unknown field
<!-- AC:END -->
