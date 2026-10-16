---
id: TASK-0114
title: >-
  Resolve a function by its symbol id without scanning every symbol: find_symbol
  costs the impurity sweep 22 s a run (pypeeker, then bump the pin)
status: To Do
assignee: []
created_date: '2026-10-16 08:19'
labels:
  - gates
  - size-2
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. On a warm run scripts/arch-check --no-fix takes 115.6 s here; the root gate's check is 89% of that. no-impure-functions is 23.4 s of the gate's 106 s (in-process, 22%), and import-time-side-effects (8.8 s) pays the same cost for its project-call part.

Why: the impurity sweep (pypeeker/dsl/sweeps.py, _impurity_table) calls analysis.purity.impurities for each function, which builds an AnalysisContext per function it walks; AnalysisContext._resolve_function turns the symbol id into a symbol with SemanticQueryEngine.find_symbol(symbol_id), and find_symbol scans every symbol of every indexed file (all_indexes(), then a predicate on each of about 25,400 symbols) on every call. In the root gate's run that is 2,167 calls, 55 million predicate calls and 605,000 store.load calls; in the profile (cProfile, which doubles every figure) the calls are 60 of 205 s.

Measured saving: answering a full symbol id from a dict built once per engine from all_indexes() gives, for all 3,771 function and method symbols in the root index, the same _resolve_function result as the scan (no difference; 29.0 s of scan against 0.01 s). In the gate: no-impure-functions 23.4 s -> 5.5 s, import-time-side-effects 8.8 s -> 7.7 s, the gate's check 106.1 s -> 84.6 s in-process (median of 3), and 103.0 s -> 86.4 s for the real pypeeker check --strict command in three paired runs.

Constraint to keep: find_symbol's docstring promises that all_indexes() re-reads the store on every call, so a cache inside the engine would change what a long-lived engine sees after a save. The prototype avoided that by building the dict per engine inside the sweep's lifetime (a corpus is the indexes as they were when the run began); an upstream fix may instead add a by-id lookup on the engine that does not claim to re-read. A name that is not a symbol id must still go through the scan (a dotted-suffix match is deliberate).

This is a pypeeker change (pinned in the root dev dependencies): make it upstream, then bump the pin here as TASK-0102 did.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pypeeker (upstream) resolves the function an impurity walk asks about from its symbol id without a scan of every symbol, keeps find_symbol's contract that all_indexes() re-reads the store, and the root pin names the merged commit, uv.lock regenerated with uv
- [ ] #2 The root gate's no-impure-functions takes under 8 s on a warm run (23.4 s before, in-process timing, median of 3), recorded in the notes, and its findings on a planted impure function are the same as before
<!-- AC:END -->
