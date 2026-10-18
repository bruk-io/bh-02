---
id: TASK-0146
title: 'Lint and format scripts/model-friction (unsorted imports, six long lines)'
status: To Do
assignee: []
created_date: '2026-10-18 12:20'
labels:
  - scripts
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/model-friction has no .py suffix, so the PostToolUse hook and the root ruff config never check it. Run on the file, ruff check --no-fix reports 7 findings (unsorted imports, 6 lines over 110 characters) and ruff format --check wants two lines wrapped. All pre-existing, none from TASK-0138, which found them and left them alone (scope). Fix formatting and lint only: no behaviour change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 uv run ruff check --no-fix scripts/model-friction exits 0
- [ ] #2 uv run ruff format --check scripts/model-friction exits 0
- [ ] #3 scripts/model-friction --json over the same sessions prints what it printed before
<!-- AC:END -->
