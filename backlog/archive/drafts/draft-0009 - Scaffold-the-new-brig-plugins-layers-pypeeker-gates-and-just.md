---
id: DRAFT-0009
title: 'Scaffold the new brig: plugins, layers, pypeeker gates and just'
status: Draft
assignee: []
created_date: '2026-10-17 17:45'
labels:
  - brig
  - size-3
dependencies:
  - DRAFT-0008
parent_task_id: TASK-0135
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

decision-0008's order, step 2 (with the docs in a task of their own): everything the walking skeleton is built inside. The settings file comes first, so every later session has the owner's plugins (TASK-0135 criterion 2).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02's .claude/settings.json registers the knowhere marketplace (bruk-io/knowhere), enables philosophy@knowhere, authoring-kit@knowhere and c4-architecture@knowhere, and approves the likec4 server; it lands in this task's first commit
- [ ] #2 .mcp.json declares the likec4 server at a pinned @likec4/mcp version, with docs/brig/architecture as its workspace
- [ ] #3 src/brig holds empty domain, infra and presentation packages, and tests holds unit, integration and e2e
- [ ] #4 brig's pypeeker gate runs decision-0008's rules 1 to 7, 12 and 14 (brig-layers, brig-pure-domain with no-impure-functions, brig-slices, brig-test-layers, brig-no-patching, the house rules, brig-class-forms, brig-vocabulary, brig-one-writer) with check --strict, and scripts/arch-check passes on the skeleton
- [ ] #5 Each new pypeeker rule has a test that plants a violation of it and sees the rule report it
- [ ] #6 libs/brig/justfile is brig's entry point: just --list shows every recipe with what it does, each command written once; rust-just is a dev dependency
- [ ] #7 just check runs only the unit and integration tests the change reaches (the diff against main, plus uncommitted and untracked files), and nothing else
- [ ] #8 just done runs ruff, mypy, every pypeeker rule, every test in all three layers with the integration suite twice in one process, the docs build and the architecture lint; it reports every step whole and every failure in one pass, and lists by name any e2e test it could not run
- [ ] #9 CI runs brig's just done, and it passes on the skeleton
<!-- AC:END -->
