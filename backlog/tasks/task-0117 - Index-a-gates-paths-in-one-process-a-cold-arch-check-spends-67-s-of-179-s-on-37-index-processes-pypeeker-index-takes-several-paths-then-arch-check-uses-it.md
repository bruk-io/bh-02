---
id: TASK-0117
title: >-
  Index a gate's paths in one process: a cold arch-check spends 67 s of 179 s on
  37 index processes (pypeeker index takes several paths, then arch-check uses
  it)
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 08:20'
updated_date: '2026-10-16 13:17'
labels:
  - gates
  - scripts
  - size-2
dependencies: []
priority: high
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. A fresh checkout or worktree has no .pypeeker (it is git-ignored), so scripts/arch-check indexes every path first. Cold, scripts/arch-check --no-fix takes 178.9 s here against 115.6 s warm, and 67.0 s of it is indexing: 61.7 s for the root gate's 29 paths (224 files), 3.2 s for brig, 0.9 s for cordis, 0.6 s each for cordis-helpers and host-paths.

Why: arch-check runs one pypeeker index PATH process per path, and each process reconciles the cross-file symbol tree before it exits (indexer.index_path with a tree store, then treebuild.load_or_rebuild), which deserialises every index entry written so far, since the process has no cache from the last one. The calls take longer as the index grows, from 0.7 s for the first root path to 3.8 s for the last: the cost grows with paths times files.

Measured saving: one process that indexes the same 29 paths with index_path (no tree store) and then reconciles the tree once took 4.1 s (4.09, 4.08, 4.18) against 60.5 s for the per-path processes in the same scratch copy (59.9, 60.5, 61.2), and the resulting .pypeeker (every index entry and tree.json) is identical, file for file (diff -r). Saving on a cold run: about 56 s for the root gate, the largest of the five.

TASK-0102 rejected calling pypeeker's Python API from the script (it couples a script to pre-1.0 internals), so the change is upstream: pypeeker index takes several paths (one reconcile at the end), and arch-check passes it every path of a gate that has no index entry in one call. A script-only way that needs no upstream change is not known; if there is one, say so here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pypeeker (upstream) indexes several paths in one call and reconciles the tree once, and the root pin names the merged commit, uv.lock regenerated with uv
- [x] #2 scripts/arch-check indexes the paths of a gate that have no index entry in one call per gate, still failing on any indexing error; the index it writes cold is identical to the one the per-path calls wrote, and a cold run's indexing time is recorded in the notes (67.0 s before; 61.7 s of it the root gate)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. pypeeker (worktree pp-0117): add indexer.index_paths(targets, ...) that checks every target exists first (a missing one raises PathNotFoundError before anything is written), indexes each with the per-file loop, merges the results in path order and reconciles the tree once at the end; index_path becomes the one-target case of it so one path is unchanged. CLI: pypeeker index takes PATH... (nargs=-1, required), a missing path exits 1 naming the path as typed. Tests: several paths give the same entries and tree.json as one call per path (indexer and CLI), a missing path among several fails the call, names the path and writes nothing, per-file errors from several paths come back in one errors list naming each file. See the equivalence test fail with the reconcile moved inside the per-path loop? No: plant by making the multi-path call reconcile per path and assert the reconcile count is 1. Proof: scripts/verify-repo.sh once. 2. bh-02: scripts/arch-check index(gate, paths) makes one pypeeker index call for all of a gate's paths without an entry, error handling unchanged (non-zero exit, errors list); run_gate calls it once per gate; update the module docstring; tests in bh-02/app/tests/test_arch_check.py in its style (one call per gate, error still fails and names the path). 3. Measure: cold indexing time before (pinned pypeeker 7905d24, per-path calls) and after, interleaved median of 3 in-process on the root corpus, machine shared; cold index vs per-path index diff -r. Risks: the pin in bh-02 is not bumped here (orchestrator), so the arch-check change only works against this pypeeker worktree; TASK-0116 edits the same script (keep to index() and its call in run_gate).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0117 worker notes (claude). Two commits: pypeeker branch wt-0117 (184d2ac, from 7905d24) and this repository's branch wt-0117. Not pushed; the pin bump and uv.lock are the orchestrator's, so AC #1 is left unticked.

## What changed
- pypeeker 184d2ac: `pypeeker index PATH...` (nargs=-1, required). New `indexer.index_paths(targets, ...)`: checks every target first (a missing one raises PathNotFoundError before anything is written; the CLI exits 1 with `Path not found: <path as typed>`), runs `index_path` per target with no tree store, joins the results in order, reconciles the tree once at the end. One path is the same code and the same output as before. A file that cannot be indexed is listed under `errors` by its own path with exit 0 (the contract architecture.md records for `index`); I read "an indexing error fails the call and names the path" as: a missing path fails the call and is named, a bad file is named in `errors` and the caller (arch-check) fails on it, exactly as with one path. `index_path` loses its only caller outside indexer.py, so it is on pypeeker's over-exposed-module-symbol allow list with the reason (pypeeker's self-lint found it before I added it). architecture.md's command list updated.
- scripts/arch-check: `index(gate, paths)` makes one `pypeeker index` call; run_gate calls it once per gate when any path has no entry. Errors still exit non-zero (pypeeker's own failure, with its message naming a missing path; `errors` entries each name their file; the header names every path of the call). The module docstring says why. TASK-0116's lines (the gates running at once) are not touched.
- bh-02/app/tests/test_arch_check.py: the spy fixture `indexed_paths` became `index_calls` (one tuple per call), the existing assertions now say one call; four new tests: every path without an index in one call and a second run makes none; the call holds only the paths without an index; an indexing error in the second path of a call fails it (exit 1) and names its file; a src path that is not there fails the call and is named.

## Proof
- pypeeker tests added: indexer (TestIndexPaths: several paths leave every entry and tree.json byte-identical to one index_path call per path; the tree is reconciled once; results joined in order; one path = index_path; a missing path among several raises naming it and writes no entry and no tree; a failing file is named in errors) and CLI (the same equivalence through `main`; missing path exit 1 naming it as typed with nothing written; a failing file under its own path with exit 0; no path is usage error 2).
- Seen failing: with `tree_store` passed to each per-path call the reconcile-count test fails (`assert 4 == 1`); with the up-front check removed the missing-path tests fail (the index of the earlier path was written). In arch-check: with the old per-path loop (`index(gate, [path])`) five tests fail (the one-call tests, the error and missing-path tests); with the error exit removed two fail. Both restored.
- pypeeker `scripts/verify-repo.sh`: 3870 passed, ruff clean, self-lint clean (PASS x3).
- bh-02: `UV_NO_SYNC=1 scripts/check bh-02/app` with every gate's .pypeeker moved aside (a real cold run, gates included): format, lint, types, tests (218 passed, 1 skipped), gates, docs all ok; tokens skipped (no bh-01 dist). 20 passed in test_arch_check.py.

## Criterion 2 measurement (cold indexing time, machine shared: load average 1.4-2.7 on 4 cores from the other workers)
Driver (scratch, not committed) loads scripts/arch-check as a module and times its own `index` for each gate with every gate's .pypeeker renamed aside; before = the pinned pypeeker 7905d24 (the main checkout's venv, read-only) one `index` call per path, as the script did; after = pp-0117, one call per gate. Both run the pypeeker binary directly (no `uv run` per call, which TASK-0111 measured at 0.04 s a call). Interleaved before/after/before/after/before/after, each started cold, seconds:

| gate (paths) | before (3 runs) | median | after (3 runs) | median |
|---|---|---|---|---|
| root (29) | 56.29 53.97 55.14 | 55.14 | 3.84 3.91 4.41 | 3.91 |
| brig (2) | 2.95 3.17 2.99 | 2.99 | 2.27 2.41 2.57 | 2.41 |
| cordis (2) | 0.72 0.74 0.80 | 0.74 | 0.43 0.44 0.56 | 0.44 |
| cordis-helpers (2) | 0.39 0.40 0.43 | 0.40 | 0.21 0.21 0.30 | 0.21 |
| host-paths (2) | 0.40 0.40 0.41 | 0.40 | 0.20 0.29 0.25 | 0.25 |
| total (37 calls, 5 calls) | 60.75 58.68 59.77 | 59.77 | 6.95 7.26 8.09 | 7.26 |

Saving on a cold run: 52.5 s (88%); TASK-0111's own run had 67.0 s of indexing on an idle machine (61.7 s root), so the shares carry over and the seconds do not. TASK-0111's prototype saw 4.1 s for the root gate; here 3.9 s.
Identity: the first before run and the first after run each copied every gate's .pypeeker (index entries and tree.json: 225, 171, 20, 6, 6 files); `diff -r` of before against after is empty for all five gates. The index the real cold `scripts/check` run left in the root gate also differed from that snapshot (I did not list how before putting the originals back); a later cold run with the sources as they now are (`diff -rq` against the snapshot) differs in exactly two files, the entry for bh-02/app/tests/test_arch_check.py and tree.json, the one source file I reformatted after taking the snapshot, so the snapshot is stale for it, not the index wrong. The worktree's own .pypeeker directories were moved aside by rename and put back: the manifest of every path, size, mode, mtime and sha256 (1014 lines) is identical before and after, three times.

## Caveats
- Until the root pin names a pypeeker with this change, scripts/arch-check on a checkout with the pinned pypeeker fails on any gate with more than one path to index (`Got unexpected extra argument`), and the arch-check tests need the new pypeeker too: they pass here only because this worktree's venv has pp-0117 installed editable.
- Script-only alternative with no upstream change: none known (as the task said).

Pin part of criterion 1 (orchestrator, 2026-10-16): the pypeeker change landed as part of brukhabtu/pypeeker PR #148 (CI green), squash-merged as 67b0a1b0121fa48d89c6cecaa82624592bfa8386. The commits reviewed were 04e2249 (TASK-0113), f6ea736 (TASK-0114) and 8fd3239 (TASK-0117) on pypeeker branch ccr-8cdd69a0-gt1lov (the workers' wt-* commits 7370f98, ae3f719 and 184d2ac re-applied without change). bh-02 commit 2bcfefe pins pypeeker@67b0a1b; uv.lock regenerated with `uv lock` (pypeeker 7905d240 -> 67b0a1b0, nothing else).
- After the pin, on a quiet machine: scripts/arch-check --no-fix exit 0 in 56.4, 49.9, 49.8 s (TASK-0111 measured 115.6 s warm before any of TASK-0113..0118).
- Full scripts/check: exit 0 in 208 s; format, lint, types, tests (3186 passed, 31 skipped), gates (all five ok), docs, tokens.

Reviewer: APPROVE. pypeeker 8fd3239 (squash 67b0a1b): index takes several paths, checks all first, reconciles once; missing path exits 1 named, per-file errors under errors exit 0, which arch-check still fails on. index_path kept public on the allow list with a sound reason. Merge db56e56 with TASK-0116 checked: index returns its problem, run_gate one call per gate, Outcome(False, problem). Pin 2bcfefe names 67b0a1b and uv.lock resolves to it; full check passed (orchestrator). No blocking or should-fix findings. Nits, not filed: b1fe1d1's message cites a stale pypeeker SHA 184d2ac; index's error prefix joins every path into one line.
<!-- SECTION:NOTES:END -->
