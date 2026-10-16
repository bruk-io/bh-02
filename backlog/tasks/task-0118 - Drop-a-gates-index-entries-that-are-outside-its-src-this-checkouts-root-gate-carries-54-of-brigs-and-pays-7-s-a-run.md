---
id: TASK-0118
title: >-
  Drop a gate's index entries that are outside its src: this checkout's root
  gate carries 54 of brig's and pays 7 s a run
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 08:20'
updated_date: '2026-10-16 12:13'
labels:
  - gates
  - scripts
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. scripts/arch-check indexes a path only when it holds a file with no index entry, and pypeeker's check refreshes entries it already has and drops those whose source file is gone, but nothing ever drops an entry whose file still exists and is no longer in the gate's src. This checkout's root index holds 278 entries and the root src has 224 files: the 54 extra are libs/brig/src, left from when brig was in the root gate's src before it kept a gate of its own.

Cost, measured: with those 54 entries removed (the .pypeeker copied aside, the libs/ entries deleted, put back afterwards and checked file by file) the root gate takes 98.9 s against 106.1 s in-process (median of 3), 6.8%: the refresh reads fewer files (3.7 s -> 3.0 s) and every symbol lookup and the call graph, which read all indexed files and not only src, see 24% fewer symbols (no-impure-functions 23.4 s -> 19.9 s). It is paid on every run, by any checkout whose src has ever shrunk or a member moved; a fresh checkout has none.

The rules' own corpus is cut to src, but find_symbol and call_graph read the whole store, so an orphan entry is also code the gate does not police that its sweeps still see.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scripts/arch-check removes a gate's index entries whose source is not under any of that gate's src paths (a pure function decides which, in the style of without_index), and a test shows an entry outside src is dropped and an entry inside src is kept
- [x] #2 On a checkout whose root index has entries outside src, the root gate's time before and after is recorded in the notes (106.1 s and 98.9 s in-process on this one)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Layout: pypeeker has no CLI command that drops an index entry (its commands: index, check, tree, query, ...; ensure_fresh drops only entries whose file is gone). The documented layout is pypeeker/storage/index_store.py: src/a.py -> .pypeeker/index/src/a.py.json, and IndexStore.remove unlinks exactly that file. So the shell unlinks <gate>/.pypeeker/index/<entry>.json, the same file. Nothing else changes: tree.json is reconciled by the query engine's get_tree (load_or_rebuild) on the next read, so a stale tree is not read.
2. scripts/arch-check: pure outside_src(paths, entries) beside without_index, Path.is_relative_to (whole components, so libs/a does not hold libs/ab/x.py; a src path that is a file holds itself); shell drop_entries(gate, entries) unlinks each entry's file; run_gate gets one call, after sync_src and before without_index. Module docstring gets one sentence.
3. Tests in bh-02/app/tests/test_arch_check.py: pure edges (sibling-prefix, nested src path, file directly in a src root, src path that is a file) and an integration test: a gate whose src shrinks from members/* to members/a/src; b's entries dropped, a's kept, b's file still on disk and no longer checked. Plant: drop the call in run_gate, see the integration test fail, restore.
4. Criterion 2: snapshot of the root .pypeeker with the 54 orphans taken before any change (scratchpad). After the change, scripts/arch-check --no-fix drops them: that state is the 'after'. Time pypeeker check --strict at the root (the command the script runs) on each state, interleaved, pairs, median of 3; machine shared (noisy); also diff the two outputs (findings must be the same).
5. Proof: uv run pytest on the test file; scripts/arch-check --no-fix once at the end; scripts/check bh-02/app --no-gates --no-docs. Not run: scripts/check in full, the criterion's ruling is the reviewer's.
Risks: TASK-0116 edits the same script: keep to the function, the helper and one line in run_gate. Removing orphans changes what find_symbol sees: the outputs check compares it.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0118 worker notes (branch wt-0118, from 11f8dd8).

## What changed
- scripts/arch-check: pure `outside_src(paths, entries)` beside `without_index` (Path.is_relative_to, whole components; a src path that is a file holds itself); shell `drop_entries(gate, entries)` unlinks `<gate>/.pypeeker/index/<entry>.json` with missing_ok; `run_gate` gets one call after `sync_src` and before the indexing step; run_gate's docstring and the module docstring get the new step.
- bh-02/app/tests/test_arch_check.py: 4 tests (3 pure-function edges, 1 integration: a member leaves src, its entries are dropped, the member in src keeps its own, the dropped member's file stays on disk and a violation in it is not reported, nothing is indexed).

## Layout decision
pypeeker has no command that drops an entry whose file still exists (its CLI: index, check, tree, query, refactor commands; ensure_fresh drops only entries whose file is gone). The documented layout is pypeeker/storage/index_store.py: src/a.py -> .pypeeker/index/src/a.py.json, and IndexStore.remove unlinks that file, so drop_entries unlinks the same file. tree.json is not edited: TreeStore is read only by treebuild.load_or_rebuild, which the query engine's get_tree calls on the first tree read and persists. Checked: after the drop, `check --strict` leaves tree.json unchanged (still 278 nodes, 54 brig), and one `pypeeker tree` read rewrites it to 221 nodes, 0 brig. Empty directories under .pypeeker/index/libs/brig are left behind (13), as IndexStore.remove leaves them; pypeeker never reads a directory as an entry.

## Tests and proof
- `uv run pytest bh-02/app/tests/test_arch_check.py -v`: 16 passed (12 before).
- Planted, then restored (diff of scripts/arch-check against a saved copy: identical):
  (a) the drop_entries call removed from run_gate: test_an_index_entry_outside_src_is_dropped_and_one_inside_src_is_kept FAILS at the entries assertion (members/b/src/b/mod.py still indexed); with the call: passes.
  (b) Path.is_relative_to replaced by a string prefix (e.startswith(path)): test_a_src_path_holds_the_files_beneath_it_by_whole_path_components FAILS (returned () for ('libs/a.py', 'libs/ab/z.py')); restored: passes.
- Root index on this checkout: 278 entries, 54 outside src (all libs/brig/src); after the first `scripts/arch-check --no-fix` run: 224 entries, and the set equals the 224 root src files exactly. No index directory of the libs gates changed during the run (none had entries to drop).
- `scripts/check bh-02/app --no-gates --no-docs`: exit 0. format: 23 files already formatted; lint: All checks passed; types: no issues in 7 source files; tests: 214 passed, 1 skipped.
- `scripts/arch-check --no-fix` (final, once more after the timing): exit 0, no findings. Only scripts/arch-check and bh-02/app/tests/test_arch_check.py changed in git.
- Not run: full scripts/check (left to the reviewer, criterion not ticked on its behalf).

## Criterion 2: root gate time, before and after
Machine shared with two other workers (1-minute load average 1.8 to 2.9 on 4 cores during the rounds). Timed: `env PYTHONPATH=<root> uv run --quiet pypeeker check --strict` run from the root, the root gate's command in arch-check, on two saved copies of the root .pypeeker: W (the 54 orphans, as copied from the main checkout) and O (the same after arch-check dropped them). Each run starts from a restored copy (restore not timed). Three paired rounds, order alternated: (W,O), (O,W), (W,O). Output of all six runs: empty, exit 0, identical between states.
- W: 97.83, 97.58, 100.58 s; median 97.83 s
- O: 94.04, 97.27, 97.00 s; median 97.00 s
- paired differences W minus O: +3.79, +0.31, +3.58 s; median +3.58 s (3.7%)
This is a smaller and noisier saving than TASK-0111's in-process figure (106.1 s to 98.9 s, 7.2 s): the run-to-run spread (94.0 to 100.6 s) is larger than the median difference, and this is the subprocess command, not the in-process rule timing. Not reproduced at 7 s on this run; a reviewer who wants a firmer number needs more paired rounds, which were not run because the brief said median of 3.

Reviewer verdict: CLOSE. AC1 met: outside_src pure, Path.is_relative_to, 4 tests (dropped/kept + edges), re-run 16 passed; arch-check --no-fix exit 0. AC2 met: before/after recorded (97.83 s vs 97.00 s median, paired +3.6 s, noise noted). Should-fix (not filed): drop_entries unlinks by pypeeker's on-disk layout, the same pre-1.0 coupling TASK-0102 rejected for the Python API, just smaller; the docstring names IndexStore.remove but not that a pypeeker storage change silently makes the drop a no-op (missing_ok). Corruption risk low: per-file unlinks are independent, tree.json is rebuilt on read. Nit: empty index dirs left behind.
<!-- SECTION:NOTES:END -->
