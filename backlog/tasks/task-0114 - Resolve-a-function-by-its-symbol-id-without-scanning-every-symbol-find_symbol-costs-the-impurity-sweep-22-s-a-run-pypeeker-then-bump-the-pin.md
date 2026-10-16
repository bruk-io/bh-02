---
id: TASK-0114
title: >-
  Resolve a function by its symbol id without scanning every symbol: find_symbol
  costs the impurity sweep 22 s a run (pypeeker, then bump the pin)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 08:19'
updated_date: '2026-10-16 13:16'
labels:
  - gates
  - size-2
dependencies: []
modified_files:
  - src/pypeeker/query/engine.py
  - src/pypeeker/query/__init__.py
  - src/pypeeker/analysis/context.py
  - src/pypeeker/analysis/purity.py
  - src/pypeeker/dsl/sweeps.py
  - tests/test_index_cache_freshness.py
  - tests/test_module_id_collisions.py
  - storage-transaction-architecture.md
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
- [x] #1 pypeeker (upstream) resolves the function an impurity walk asks about from its symbol id without a scan of every symbol, keeps find_symbol's contract that all_indexes() re-reads the store, and the root pin names the merged commit, uv.lock regenerated with uv
- [x] #2 The root gate's no-impure-functions takes under 8 s on a warm run (23.4 s before, in-process timing, median of 3), recorded in the notes, and its findings on a planted impure function are the same as before
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
Design choice, made before any code: a snapshot taken once per sweep (the prototype's way), not an engine-level lookup rebuilt on store change. find_symbol and SemanticQueryEngine keep no new state, so the contract (all_indexes() re-reads the store on every call; a long-lived engine sees a save) holds by construction. The snapshot has the lifetime the sweep already gives the call graph: memoised on the Corpus, which is the indexes as they were when the run began and is replaced after every change (check --fix's residual run, each --fix-until-clean round). An engine-level table rebuilt "when the store changes" needs a change signal that does not exist: a revision on IndexStoreLike plus IndexStore and OverlayIndexStore (every overlay write path would have to bump it, and a missed one is a stale answer), or re-loading every index on every lookup to compare them (about 600k store.load calls a run, which the scan already pays besides its predicate).
Work, in the pypeeker worktree (base 7905d24, the commit bh-02 pins):
1. SemanticQueryEngine.symbol_table(): one pass over all_indexes(), {symbol id: symbols in find_symbol order}; a fresh snapshot per call, the engine keeps nothing; the caller owns how long it lives.
2. AnalysisContext.for_function(..., symbols=) and impurities(..., symbols=), parallel to graph=: _resolve_function takes the first FUNCTION/METHOD the table holds under the id; any name it holds no function under (bare name, dotted suffix, a class's id, an id saved since) goes through find_symbol as before, so the deliberate dotted-suffix match and the not_a_function error stay.
3. dsl/sweeps.py _impurity_table: the table in corpus.memo next to the call graph, passed with graph=.
4. Tests in tests/test_index_cache_freshness.py (the file that proves the other two caches): the sweep makes no find_symbol call; by-id resolution equals the scan for every id, bare name and suffix of a fixture project (duplicates included); a save after the table exists is seen by the engine and by a fresh corpus's sweep; the sweep's findings are unchanged.
5. scripts/verify-repo.sh once (pytest, ruff, self-lint).
6. Measure criterion 2 here, then notes and ticks.

### Risks
An id that is exact for a function but also the dotted suffix of an earlier function's id (b:f against a.b:f): the scan returns the earlier symbol, the table the function the id names. That is a correction, not a preservation: documented in storage-transaction-architecture.md and pinned by a test, and flagged in the notes. The baseline here is lower than TASK-0111's 23.4 s (the index has 224 entries, not 278), so before and after are measured fresh, interleaved, on a shared machine.

### Proof
Tests that guard the contract are seen failing (no-scan test on the base; sweep not passing the table; engine keeping its table; table's functions taken last-first) and passing with the change. Criterion 2: in-process timing of no-impure-functions (and import-time-side-effects) on bh-02's root corpus, base 7905d24 against the change, interleaved, median of 3, machine shared; findings on a planted impure function (scratch copy of bh-02, never committed) the same before and after. Criterion 1's last clause (root pin, uv.lock) is the orchestrator's: left unticked.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0114 worker notes. The change is upstream, in pypeeker: branch wt-0114 of /home/user/pypeeker/.claude/worktrees/pp-0114, one commit ae3f719 on 7905d24 (the commit bh-02 pins). Nothing in bh-02 changed but this board. The root pin and uv.lock are the orchestrator's, so criterion 1 stays unticked.

## What changed in pypeeker
- SemanticQueryEngine.symbol_table(): one pass over all_indexes(), every symbol under its full id (a tuple per id, in find_symbol's order, because ids are not unique: proj/dup.py and proj/dup/__init__.py, three `over:twice:x` parameters in one file). A snapshot; the engine keeps nothing, so find_symbol still re-reads the store on every call.
- AnalysisContext.for_function(..., symbols=) and impurities(..., symbols=), next to graph=. A function or method the table holds under the id is taken from it; any other name (bare name, dotted suffix, a class's id, an id saved since) goes through find_symbol as before.
- dsl/sweeps.py _impurity_table takes the table once in the corpus memo (key ("sweep", "symbol-table")), next to the call graph: the lifetime of the indexes the run began with. A fresh corpus after a change takes a fresh table.
- Choice, and why (also in the plan): a per-sweep snapshot, not an engine-level table rebuilt when the store changes. The engine has no change signal (it would need a revision on IndexStoreLike, IndexStore and OverlayIndexStore, and a missed bump in an overlay write path is a stale answer), and re-loading every index per lookup to compare them is the 605,000 store.load calls the scan already pays. The snapshot keeps the contract by construction: no state was added to the engine.
- One deliberate difference from the scan, documented in storage-transaction-architecture.md and pinned by a test: a full id that is also the dotted suffix of an EARLIER function's id (`b:f` against `a.b:f`, both functions; the dotted-suffix match is deliberate in find_symbol) used to resolve to the earlier one (the walk asked about b:f analysed a.b:f's body); with the table it names its own function. Where the table and the scan both have one candidate, or only exact-id candidates, they elect the same symbol (tested for every id, bare name and suffix of a fixture project, including the kind-preferring duplicate `app.dup.mod:go`, a two-function duplicate and overload duplicates). The orchestrator may want to look at this one.

## Proof (pypeeker)
- scripts/verify-repo.sh: pytest 3868 passed, ruff passed, self-lint passed (2 low-confidence hits hidden, both in refactor/batch.py, not mine). One existing test (test_module_id_collisions.py) calls the private _resolve_function; its second argument stays optional and it now also asserts the table elects the same symbol.
- Planted checks seen failing (tests/test_index_cache_freshness.py, 23 tests, all pass on the change): on the base the no-scan test fails with 21 find_symbol calls for the 6-function sweep; with the sweep not passing the table, the no-scan test and the b:f test fail; with the engine keeping its table, the save-after-the-table test fails; with the table's functions taken last-first, the equivalence test and the two-function duplicate test fail. Each plant reverted (git diff clean of them).

## Criterion 2: timing, bh-02's root corpus, in-process
Driver (scratch, not committed): one shared Corpus over the root gate's 224 index entries, ensure_fresh first, every rule of [tool.pypeeker].rules in the gate's order, each timed (TASK-0111's method). Before = pypeeker 7905d24 (git worktree under /tmp/claude-0, put first on PYTHONPATH of this checkout's venv, pypeeker.__file__ checked each run); after = the change (editable). Three pairs back to back, interleaved before/after, each its own process, under tini, MACHINE SHARED with other workers (load average 1.4 to 5 during the runs), so the figures are noisy.

| rule, seconds | before (3 runs) | median | after (3 runs) | median |
|---|---|---|---|---|
| no-impure-functions | 14.1, 18.9, 13.2 | 14.1 | 6.0, 6.3, 6.2 | 6.2 |
| import-time-side-effects | 8.0, 8.0, 7.8 | 8.0 | 7.3, 8.2, 7.6 | 7.6 |

no-impure-functions is under 8 s (6.2 s median, 6.0 to 6.3 in the three runs). An extra before run gave 14.3 s. The before is 14.1 s, not TASK-0111's 23.4 s: this index has 224 entries (TASK-0111's had 278, 54 of them orphans TASK-0118 since drops), so the scan was shorter and the saving smaller than the 23.4 to 5.5 prototype; the sweep makes no find_symbol call now (counted: 0 calls on the root corpus). Whole-gate sum of rules, median of 3: 82.1 s before, 72.8 s after (one after run hit a noisy 92.4 s, in no-hidden-global-mutation, 60 s against 41 s, a rule this change does not touch).
Findings on the real root corpus: empty before and after in all 7 runs (the gate is clean), so that comparison alone proves little; hence the plant.
Planted impure function, scratch copy of this checkout (/tmp/claude-0/bh02-plant, never committed): in memory_cordis_plugin/touch.py a function printing, a caller of it and a method calling it; in rules.py a caller in another module, and a module-level call of that caller. Both runs (before and after) give the same 4 no-impure-functions findings (the print, the three transitive ones, message for message) and the same 1 import-time-side-effects finding (the module-level project call resolving to an impure project function), compared as (path, line, rule, message) lists: identical.

Not run: scripts/check and scripts/arch-check (nothing outside the board changed in this repository). Not done, for the orchestrator: merge and push the pypeeker branch, bump the root pin, regenerate uv.lock, then tick criterion 1.

modified_files above are pypeeker's paths (repository /home/user/pypeeker, commit ae3f719), not this repository's; this repository changed only its board.

Pin part of criterion 1 (orchestrator, 2026-10-16): the pypeeker change landed as part of brukhabtu/pypeeker PR #148 (CI green), squash-merged as 67b0a1b0121fa48d89c6cecaa82624592bfa8386. The commits reviewed were 04e2249 (TASK-0113), f6ea736 (TASK-0114) and 8fd3239 (TASK-0117) on pypeeker branch ccr-8cdd69a0-gt1lov (the workers' wt-* commits 7370f98, ae3f719 and 184d2ac re-applied without change). bh-02 commit 2bcfefe pins pypeeker@67b0a1b; uv.lock regenerated with `uv lock` (pypeeker 7905d240 -> 67b0a1b0, nothing else).
- After the pin, on a quiet machine: scripts/arch-check --no-fix exit 0 in 56.4, 49.9, 49.8 s (TASK-0111 measured 115.6 s warm before any of TASK-0113..0118).
- Full scripts/check: exit 0 in 208 s; format, lint, types, tests (3186 passed, 31 skipped), gates (all five ok), docs, tokens.
<!-- SECTION:NOTES:END -->
