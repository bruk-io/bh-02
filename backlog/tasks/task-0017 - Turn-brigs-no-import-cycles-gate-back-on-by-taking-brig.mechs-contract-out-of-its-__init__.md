---
id: task-0017
title: >-
  Turn brig's no-import-cycles gate back on by taking brig.mech's contract out
  of its __init__
status: To Do
assignee: []
created_date: '2026-09-28 12:26'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
brig's own architecture gate runs with no-import-cycles off, because brig.mech's submodules import their contract back from brig.mech/__init__, which newer pypeeker reports as a cycle. brig should be held to the cycle rule again, and its __init__ should only re-export.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 no-import-cycles is listed in libs/brig/pyproject.toml's rules and scripts/arch-check passes
- [ ] #2 brig.mech's public names are unchanged for importers (from brig.mech import ... still works)
- [ ] #3 brig-layers (strict) still passes, and SPEC.md or CLAUDE.md name where the contract now lives if they named it before
- [ ] #4 scripts/check passes
<!-- AC:END -->
