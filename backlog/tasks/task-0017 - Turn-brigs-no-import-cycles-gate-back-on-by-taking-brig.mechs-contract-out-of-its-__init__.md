---
id: task-0017
title: >-
  Turn brig's no-import-cycles gate back on by taking brig.mech's contract out
  of its __init__
status: Done
assignee: []
created_date: '2026-09-28 12:26'
updated_date: '2026-09-28 12:40'
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
- [x] #1 no-import-cycles is listed in libs/brig/pyproject.toml's rules and scripts/arch-check passes
- [x] #2 brig.mech's public names are unchanged for importers (from brig.mech import ... still works)
- [x] #3 brig-layers (strict) still passes, and SPEC.md or CLAUDE.md name where the contract now lives if they named it before
- [x] #4 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commit cc21cca. The contract (Step, CompileCtx, EventSource, Mechanism, ...) moved verbatim to libs/brig/src/brig/mech/contract.py; brig/mech/__init__.py now only re-exports (same __all__, so from brig.mech import ... is unchanged). bwrap, env_scrub, rlimits, connect_proxy and seatbelt import from brig.mech.contract. no-import-cycles is back in libs/brig/pyproject.toml's rules. test_mech_events_purity pins contract.py (pure set) and __init__.py (brig.mech.* only); its docstring no longer argues the old shape is fine. SPEC.md, CLAUDE.md and README never named where the contract lived, so nothing there changed. scripts/arch-check exit 0; brig tests 774 passed / 8 skipped; mypy clean. Full scripts/check run at the end of the leftovers branch.
<!-- SECTION:NOTES:END -->
