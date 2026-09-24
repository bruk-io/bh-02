---
id: task-0002
title: >-
  Strip scripted demos and the CodeAct harness; keep __init__ files re-export
  only
status: Done
assignee: []
created_date: '2026-09-15 19:09'
updated_date: '2026-09-16 16:40'
labels:
  - bhh
  - cordis
  - pypeeker
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bhh should be just the Claude chat REPL. Remove the pre-scripted material and the unused CodeAct harness so nothing canned remains, and make every package `__init__.py` a pure re-export contract with no definitions, enforced by the architecture gate.

Scope chosen by the user: the CodeAct harness (Harness, Model, ScriptedModel, Turn, split_action, its demo and test), cordis's scripted session demo, and the chat tests' scripted fakes. Removing the fakes deletes bhh's offline tests of presenter swapping, error handling and shutdown; the user accepted that trade-off.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No CodeAct harness code, scripted model, or scripted demo remains in bhh or cordis
- [x] #2 The chat test fakes are gone and no test or config still refers to them or to removed modules (amended on close: the scripted CodeAct fakes are gone; bhh keeps two small Protocol fakes, `Echo` and `Silent` in `bhh/tests/conftest.py`, because they are what tests the presenter swap, the error path and shutdown without a login)
- [x] #3 Every package __init__.py contains only imports, a docstring and __all__
- [x] #4 The architecture gate fails when a class, function or other definition is added to an __init__.py, verified with a planted violation
- [x] #5 The REPL still runs (`uv run bhh --help`) and cordis's own tests still pass
- [x] #6 Docs (CLAUDE.md, cordis README) no longer describe the removed harness, demos or tests
- [x] #7 ruff, mypy and scripts/arch-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Closed 2026-09-16 after the cordis v2 rewrite and the functional-core refactor.

- The CodeAct harness (`Harness`, `Model`, `ScriptedModel`, `Turn`, `split_action`), cordis's scripted session demo, `cordis/examples/`, `bhh/examples/` and the old scripted tests are gone. Nothing canned remains; `bhh` is the Claude chat REPL.
- AC #2 was amended rather than met as written. The user accepted losing the offline tests when the task was scoped; the rewrite went the other way and kept two structural fakes (`Echo`, `Silent`) plus scripted SDK messages in `bhh/tests/test_edges.py`, since a replacement row is the design's own substitution mechanism and the tests need no network or login.
- Every `__init__.py` re-exports only; the custom `init-reexport-only` rule in `pypeeker_rules/bhh.py` enforces it and was verified with a planted definition.
- `uv run bhh --help` runs; 462 tests, ruff, mypy strict and `scripts/arch-check` pass.
- CLAUDE.md and both READMEs describe the current layout (cordis: effects <- component <- decisions <- runtime <- inspection, composition <- loader; bhh: chat / claude / repl / app / __main__).
<!-- SECTION:NOTES:END -->
