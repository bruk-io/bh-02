---
id: TASK-0111
title: Find why scripts/arch-check takes about a minute per run
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 05:01'
updated_date: '2026-10-16 08:23'
labels:
  - gates
  - size-2
dependencies: []
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Measured 2026-10-16 from this session's subagent transcripts: 234 scripts/arch-check runs took 158.6 minutes in all (41 s on average), 23% of every tool call's time; TASK-0108's worker ran it 5 times for 5.4 minutes (about 65 s each). scripts/check runs the gates too, so the cost is paid again in every member and full check. Find where the time goes before changing anything: writing each gate's src, indexing, the index refresh of changed files, each gate's check --strict, or the per-library gates.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The time of each phase of scripts/arch-check (writing src, indexing, refreshing, each gate's check) is measured warm and cold on this repository and recorded in the notes
- [x] #2 The phase or phases that take most of the time are named with why, and each change that would cut it is proposed with its measured saving, filed as its own task when it is more than a one-line change
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Written after the measurements; no code was edited, so there is no code proof.
1. Time each phase of scripts/arch-check --no-fix by running the steps the script runs from a scratch driver: warm x3, cold x3 (each .pypeeker renamed aside, restored and compared).
2. Split the root gate's check into refresh and per-rule time in-process; read the pypeeker calls behind the biggest (cProfile, rule sources).
3. Measure each candidate saving with a run-time prototype or a reverted local edit, never an edit to pypeeker or a commit to scripts/arch-check; check the result is the same on planted violations.
4. Time scripts/check's own steps, full and member, to say whether the gates step is the slowest.
5. File what is bigger than one line as its own sized task with its measurement; record the table and the answers in the notes; tick the criteria.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0111 worker notes. A spike: no file changed but the board's (scripts/arch-check is as it was; I edited it locally for one measurement and reverted it, git status clean).

## Answer

Warm, scripts/arch-check --no-fix takes 115.6 s here; 89% of it is the root gate's `pypeeker check --strict`, and 82% of that is four rules: no-hidden-global-mutation (42%), no-impure-functions (22%), print-input (9%) and import-time-side-effects (8%). Writing each gate's src and listing what has no index entry take 0.04 s together, and the per-gate refresh 5.6 s: not where the time goes. Cold (no .pypeeker) it takes 178.9 s: indexing adds 67.0 s (37 `pypeeker index PATH` processes, each re-reading every index entry written so far to reconcile the symbol tree), and the check is 4 s faster on the smaller index.

Machine: 4 cores, 16 GB, Python 3.15.0b4, pypeeker 7905d24, nothing else running. This container is slower than the ~65 s runs of TASK-0108's worker (about 1.8x); the shares carry over, the seconds do not.

## How it was measured

Phases: a scratch driver (not committed) imports scripts/arch-check's own functions (gates, sync_src, indexed, sources, without_index, index, pypeeker) and times each call, running the same steps in the same order, `check --strict` as a subprocess exactly as the script does. 3 runs warm, 3 cold (each gate's .pypeeker renamed aside in its own directory, each run started with none, the originals put back and compared by sha256 and by size/mtime/mode of every file: identical, 624 paths). The whole script also ran under `time` five times (116.1, 113.5, 115.9, 114.1, 115.6 s), so the driver's total (115.6) is the script's. `uv run --quiet` costs 0.04 s a call (0.24 s against 0.20 s for the bare entry point): not a factor. Refresh and per-rule times are in-process (pypeeker's own indexer.ensure_fresh and the rules of app/check_run.run_check over one shared Corpus, each timed), 3 runs; they sum to 106.1 s against 102.7-103.0 s for the real command (3% harness overhead), so savings below are in-process deltas unless marked.

## Table: scripts/arch-check --no-fix, seconds, median of 3

| phase | warm | share | cold | share |
|---|---|---|---|---|
| write each gate's src (5 gates) | 0.01 | <0.1% | 0.01 | <0.1% |
| list which paths have no index entry (5 gates) | 0.03 | <0.1% | 0.01 | <0.1% |
| index paths with no entry, root (29 paths) | 0 | 0 | 61.7 | 34.5% |
| index, brig / cordis / cordis-helpers / host-paths | 0 | 0 | 3.2 / 0.9 / 0.6 / 0.6 | 1.8 / 0.5 / 0.3 / 0.3% |
| check --strict, root | 102.7 | 88.9% | 99.6 | 55.6% |
| check --strict, brig | 8.6 | 7.4% | 8.4 | 4.7% |
| check --strict, cordis | 3.0 | 2.6% | 3.0 | 1.7% |
| check --strict, cordis-helpers / host-paths | 0.46 / 0.63 | 0.4 / 0.5% | 0.50 / 0.49 | 0.3 / 0.3% |
| total (runs: 115.6, 117.6, 115.0 / 178.9, 177.5, 179.5) | 115.6 | 100% | 178.9 | 100% |

Refresh (the stale-entry re-index `check` does first, in-process, 3 repeats of ensure_fresh alone, included in the check rows above): root 3.4 s warm (3.7 s in the rule-timing runs; 278 entries, and 3.0 s with only the 224 that are in src), brig 2.0, cordis 0.2, cordis-helpers 0.01, host-paths 0.02. It deserialises every index file; the rules then reuse those in the process cache, so it is a load cost paid once, not a separate waste. Index calls by position: the first root path takes 0.7 s, the last 3.8 s (cost grows with entries written so far).

Inside the root gate's check, per rule (in-process, one shared Corpus, so a rule that first touches a memoised sweep pays for it), seconds and share of the 106.1: no-hidden-global-mutation 44.7 (42.2%), no-impure-functions 23.4 (22.1%), print-input 9.8 (9.2%), import-time-side-effects 8.8 (8.3%), under-exposed-access 7.1 (6.6%), refresh 3.7 (3.5%), over-exposed-module-symbol 2.4, plugin-layering 1.3, terminal-io 1.1, cordis-in-wiring-only 1.0, cordis-public-api 0.7, brig-one-adapter 0.7, worker-stdlib-only 0.6, init-reexport-only 0.5. Brig's gate: import-time-side-effects 4.3, refresh 1.8, brig-layers 0.8, brig-standalone 0.9. The small gates are process start-up (0.2 s) and a few tenths.

## Why (read from the pypeeker calls, and cProfile of the real run)

- no-hidden-global-mutation: three of its four parts start from one base, `references().where(in a function).where(not allowed)` (pypeeker/dsl/mutation_rules.py `_global_base`), which tests the allow patterns (fnmatch on the id and on the module, 3 patterns, 6 tests a row, each with a derivation) on every reference row before the cheap kind test drops nearly all of them. The base alone is 14.0 s; the parts as written 14.5 + 14.1 + 15.0 s.
- no-impure-functions (and import-time-side-effects' project part): the impurity sweep resolves each function it walks with `SemanticQueryEngine.find_symbol(symbol_id)`, which scans every symbol of every indexed file (about 25,400) per call: 2,167 calls, 55 million predicate calls, 605,000 store.load calls; 60 of the profile's 205 s (cProfile doubles every figure).
- print-input (ours, pypeeker_rules/apps.py): its first clause is an any_of over every unit's module test, evaluated for every reference row; the clause that keeps almost nothing (symbol id is print or input) comes last. 10.1 s as written, 2.7 s with it first.
- The DSL evaluates every clause of every row as a derivation tree, and builds an EvalContext copy (dataclasses.replace, 3 million of them) per comparison under a where: the per-row price that makes clause order matter.
- Cold: `pypeeker index PATH` ends with `treebuild.load_or_rebuild`, which reads every index entry the process did not write; 29 processes, so paths x files.
- Orphans: this checkout's root index has 54 entries for libs/brig/src (left from before brig had its own gate), outside src and never dropped; find_symbol and the call graph read all of them.

## Savings, each measured (root gate, in-process, base 106.1 s unless marked)

| change | after | saving | where |
|---|---|---|---|
| no-hidden-global-mutation: each part's own clauses before the base (all clauses kept) | 66.7 | -39.4 (37%) | pypeeker, TASK-0113 |
| find_symbol of a full id from a dict (same result for all 3,771 function ids: 29.0 s of scan against 0.01 s) | 84.6 | -21.5 (20%); real command 103.0 -> 86.4 in 3 paired runs | pypeeker, TASK-0114 |
| print-input: selective clause first | 99.4 | -6.7 (6%) | this repo, TASK-0115 |
| those three together | 43.9 | -62.2 (59%) | |
| 54 orphan entries dropped (.pypeeker copied aside, restored, verified) | 98.9 | -7.2 (7%) | this repo, TASK-0118 |
| gates side by side (local edit of arch-check, reverted): 115.6 -> 107.0 s end to end, 3 runs each | | -8.7 (7.5%); the other four gates' 12.7 s would be a fifth of the run once the root gate is near 44 s | this repo, TASK-0116 |
| cold: one process indexes the 29 root paths, one tree reconcile: 60.5 -> 4.1 s, the .pypeeker identical (diff -r) | | -56 s cold | pypeeker + this repo, TASK-0117 |
| EvalContext.consuming_falsity built once per context (not filed) | 99.3 alone, 83.8 on top of find_symbol (84.6 without) | -6.8 alone, -0.8 on top: inside the noise; left | pypeeker |

Estimate, not run end to end: with TASK-0113, 0114, 0115 and 0116 the warm run would be about 45 s (root gate ~44 s, the other four gates beside it), from 115.6.

Equivalence: on a scratch copy of the repository with one planted violation of each of no-hidden-global-mutation's four shapes (write to a module dict, ITEMS.append, os.planted_value = v, global COUNTER; COUNTER = 1) and a planted print() and input(), the rules as written and with the clause order changed gave the same six findings word for word. I did not see a gate guard fail: nothing here is a gate change.

Prototypes (scratch, applied at run time, the installed pypeeker is untouched): find_symbol: `by_id = {symbol_id: symbol}` built once per engine from `all_indexes()`, `return [by_id[name]]` when `name` is a key, else pypeeker's own scan. Rule order: the same `references().where(...)` chains with `.where(_in_a_function()).where(not_(allow_by_id_or_module(allow)))` last.

## scripts/check: is the gates step ever the slowest?

The steps run at once, so the gates compete with the tests for 4 cores. Driver: scripts/check's own `plan()` and `outcomes()` with `perform()` wrapped in a timer; run as root under tini (`tini -s -- .venv/bin/python`), every step ok in all 9 runs. Seconds, per run, median:

- Full check (3 runs): gates 143.5 (143.5, 148.6, 142.5), tests 208.6 (208.6, 215.7, 207.8), docs 4-5, format/lint/types about 1; wall 208.6 = the tests. The gates are not the slowest step in a full check; they run 24% slower than alone (143.5 against 115.6) for the shared cores, and would stop mattering to the wall time only if the tests also got faster.
- `scripts/check libs/host-paths` (3 runs): gates 118.2 (117.9, 125.1, 118.2), tests 2.6; wall 118.2.
- `scripts/check bh-02/plugins/agent-cordis-plugin` (3 runs): gates 119.6 (119.1, 119.6, 123.6), tests 7.8; wall 119.6.

So in every member check (the form workers run) the gates step is the slowest step, by 15x to 45x, and a member check cannot be faster than the gate, which always sees the whole workspace. The six tasks below are what shortens it.

## Filed (each sized 1-3)

TASK-0113 (size-2, high): no-hidden-global-mutation clause order, -39 s, pypeeker then pin. TASK-0114 (size-2): find_symbol by id, -21 s, pypeeker then pin. TASK-0115 (size-1): print-input clause order, -7 s. TASK-0116 (size-2): gates side by side, -9 s now. TASK-0117 (size-2, high): one index process per gate, -56 s cold, pypeeker then arch-check. TASK-0118 (size-1): drop index entries outside src, -7 s where they exist.

No one-line change to scripts/arch-check came out with a measured saving (the only script-side change that pays is TASK-0116's, which is more than one line and needs output capture), so none was made here. Not run: scripts/check in full for a change (no change), scripts/linux-jail-check (nothing here touches the jail). import-time-side-effects (8.8 s) and under-exposed-access (7.1 s) were not read for clause order; if TASK-0113's change lands, they are the next two to profile.

Review (closing reviewer): CLOSE. AC1 met: phase table warm and cold, median of 3, method stated; warm rows sum 115.4 against 115.6, cold 179.0 against 178.9 (rounding). AC2 met: root gate check named (89%), causes checked against pypeeker source (mutation_rules._global_base applies allow before kind; engine.find_symbol scans all_indexes per call; apps.py print-input puts the symbol-id clause last); each saving measured; TASK-0113..0118 filed, sized, To Do, board-check ready on all six. Nits, not filed: TASK-0115 title says under 3 s, its AC says under 4 s; TASK-0116 file name still carries an older title. No full check run: board-only change, as instructed.
<!-- SECTION:NOTES:END -->
