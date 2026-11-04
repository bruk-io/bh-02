---
id: DRAFT-0026
title: CONTRACTS.md's host row still lists key_envs and models_file
status: Draft
assignee: []
created_date: '2026-11-04T13:25:00Z'
labels:
  - docs
  - credentials
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0184 removed host.key_envs and host.models_file (bh_02.bootstrap._Host, run()), but bh-02/CONTRACTS.md line 39, the host row, still says the value has 'auto_memory: str, key_envs: Mapping[str, tuple[str, ...]] and models_file: str'. A plugin author reading the contract would depend on fields that no longer exist, and the credential path would look like it still runs through host. The docs step of scripts/check does not catch it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CONTRACTS.md's host row names only the fields _Host has, and points to models.key_envs() for the key variables
<!-- AC:END -->
