---
id: task-0013
title: 'Arrange the repo by ownership, with member lists derived from the directories'
status: Done
assignee: []
created_date: '2026-09-23 01:43'
updated_date: '2026-09-23 02:13'
labels:
  - repo
  - gate
milestone: M2 Monorepo layout
dependencies:
  - task-0012
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
22 sibling directories, every member listed by hand in seven places, one 60-entry purity budget for everything, a 222-line root CLAUDE.md. Move to bh-02/ (+ bh-02/plugins), examples/warden (+ plugins), libs/ and derive everything from the layout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 libs/ holds cordis, cordis-helpers, brig; bh-02/plugins/ holds the harness family; examples/warden holds warden and its plugins; history kept (git mv)
- [x] #2 Adding a member is creating its directory: testpaths, mypy files, pypeeker src, first-party names and the plugin-layering units come from globs, and scripts/register-plugin is gone
- [x] #3 Cross-package gate rules stay at the root; each library's internal layering and purity budget live with it; scripts/arch-check runs every gate
- [x] #4 scripts/check runs format, lint, types, tests and gates, for the repo or one member
- [x] #5 The root CLAUDE.md is a map plus cross-cutting rules; area guidance lives in per-area CLAUDE.md files; each family's CONTRACTS.md sits with its app
- [x] #6 Nothing behaves differently: the full suite passes before and after
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Committed 16bb7be on bh-02. Moves kept history (git mv). Globs drive members/testpaths/mypy/ruff src; scripts/arch-check writes each gate's pypeeker src from [tool.arch-check]. Gates: root (pypeeker_rules/apps.py) + libs/cordis, libs/cordis-helpers, libs/brig. warden stays in the root gate: no pyproject may sit at examples/warden (uv resolves workspace sources against the nearest project). brig's ruff config now names src = ["src", "."] so its `tests.*` helpers sort as first-party. scripts/check: format, lint, types ok; 1421 passed, 8 skipped; all gates ok.
<!-- SECTION:NOTES:END -->
