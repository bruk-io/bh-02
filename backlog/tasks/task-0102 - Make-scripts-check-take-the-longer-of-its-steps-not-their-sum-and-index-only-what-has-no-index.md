---
id: TASK-0102
title: >-
  Make scripts/check take the longer of its steps, not their sum, and index only
  what has no index
status: Done
assignee:
  - '@claude'
created_date: '2026-10-15 02:28'
updated_date: '2026-10-15 12:37'
labels:
  - scripts
  - gates
  - size-2
dependencies: []
priority: high
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-15). Measured 2026-10-14 on this machine (4 cores): a full scripts/check is about 640 s, all sequential: tests 433 s, gates 204 s, format, lint, types and docs under 3 s together. The gates are about 89 s of 37 separate 'uv run pypeeker index' calls (one per source path: 29 at the root, 2 per library) and about 117 s of the root gate's 'check --strict', most of it a pypeeker bug fixed upstream (the impurity sweep rebuilt the call graph per function; symbol lookups re-listed the index): bump the pin to the merged fix. pypeeker's check already re-indexes stale entries itself, so arch-check needs to index only a path with no index yet (a new member); scripts/arch-check's comment says why indexing exists (check against a missing index passes silently), which must stay true. The gates share nothing with the tests, so scripts/check can run them side by side.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The root pyproject pins pypeeker to the merged commit that caches the call graph and the indexed-file list; uv.lock regenerated with uv
- [x] #2 scripts/arch-check indexes only paths that have no index (still failing on any indexing error), so a new member is still indexed before check; a test or a recorded run with a new empty member shows it
- [x] #3 scripts/check runs the gates (and docs) at the same time as the tests and reports each step's result as now, exit code non-zero if any failed
- [x] #4 A full scripts/check's wall time before and after is recorded in the notes, with each step's time; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) BEFORE numbers on the old pin and old scripts: arch-check --no-fix alone (done: 236 s) and a full scripts/check run through a timed scratchpad copy of the old script (per-step seconds). (2) Bump the root pyproject pin to pypeeker@7905d24 (PR #146 is 7a8fe5f; 7905d24 is main after it), uv lock, uv sync --all-packages; time arch-check --no-fix again. (3) Experiment on what pypeeker check refreshes on its own (pypeeker/indexer.py ensure_fresh reads: only files that already have an index entry are re-indexed or dropped; never widens): changed file in an indexed path, NEW file in an indexed path, new path. Source says a new file in an indexed path is NOT picked up, so 'index only paths with no index' is not enough: a new module in an existing member would pass the gate unchecked. (4) arch-check: pure core missing(sources, indexed) -> the paths holding a .py file with no entry in the gate's .pypeeker/index (layout documented in pypeeker's IndexStore: index/<source path>.json); shell indexes only those paths with the CLI (one process each, still failing on any indexing error). A file that fails to parse never gets an entry, so it is re-indexed and re-reported on every run; a missing or wiped index indexes everything (fails safe). Rejected: mtime heuristics (a checkout or cp -p can bring older mtimes), a record of what arch-check indexed (survives a wiped index, so check would pass silently), the pypeeker Python API in one process (couples a script to pre-1.0 internals). (5) Test: a tmp gate (pyproject with [tool.arch-check] and the init-reexport-only rule), a clean member passes, a new module with a violation in an existing member is reported, a new member with a violation is reported; each planted check seen failing against the old arch-check (index all paths... and against check alone for the new-module case). Plus the pure function's cases and a check that after a run nothing is missing (catches layout drift on a pin bump). (6) scripts/check: a pure plan of steps (frozen Step/Skipped), all submitted to a thread pool at once, each step's output captured (stderr merged) and printed whole in the declared order, same '== name' and ok/FAILED format, exit non-zero if any failed; scripts/check MEMBER unchanged. (7) Docs: CLAUDE.md and docs/contributing/index.md say arch-check indexes every path; reword. (8) AFTER numbers: full scripts/check timed via a timed copy of the new script; arch-check, uv run mypy, scripts/check as root one at a time. Risks: concurrent steps contend for CPU (4 cores) and uv; pyproject src rewrite by arch-check racing a test that reads it (only when a member is added). Proof: exit codes read directly; planted violations seen failing before they pass.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0102 worker notes. Run as root (uv run pytest ...); the two new test files also run as the tester user under tini (16 passed).

What changed: pyproject.toml + uv.lock (pypeeker pin cf4f168 -> 7905d24, main after PR #146 = 7a8fe5f; uv lock, uv sync --all-packages); scripts/arch-check; scripts/check; bh-02/app/tests/test_arch_check.py and test_check_script.py (new); CLAUDE.md and docs/contributing/index.md (what the gate indexes, that the steps run at once).

What pypeeker's check refreshes, by experiment (a tmp gate with the init-reexport-only rule, pypeeker 7905d24, check run directly; also read in pypeeker/indexer.py ensure_fresh): a CHANGED file in an indexed path: refreshed, the planted definition reported. A NEW file in an indexed path: NOT picked up, exit 0 and silent; reported once the path is indexed. A NEW path: not picked up, same. A deleted file: its entry dropped. So the task's 'index only a path with no index' would let a new module in an existing member pass unchecked (planted: the literal version fails test_a_new_module_in_a_path_that_is_indexed_reaches_the_gate).

Approach and why: arch-check indexes a path only if it holds a .py file with no entry under the gate's .pypeeker/index (the layout IndexStore documents: index/<source path>.json); pure core without_index(files, entries), shell sources()/indexed(), pypeeker index PATH per such path, still exiting non-zero on any indexing error (a file that fails to index has no entry, so it is asked again and fails again every run; a src entry pointing nowhere names itself and pypeeker refuses it). A wiped index indexes everything (fails safe). Rejected: mtime (a checkout or cp -p can bring older times), a record of what arch-check indexed (survives a wiped index, so check would pass silently), pypeeker's Python API in one process (couples a script to pre-1.0 internals). A fresh checkout or worktree still indexes every path as before (37 processes).

Planted checks, seen failing (test_arch_check, 8 tests, passes on the real script): (1) index only paths with NO entry (task wording): 3 failed, incl. the new-module test. (2) never index (check alone): 7 failed of 8. (3) old behaviour, index every path: correct but 2 failed (the 'only what is missing' tests). scripts/check: ThreadPoolExecutor(max_workers=1) made test_steps_run_at_the_same_time and the order test fail (60 s of deadlines); restored. Also a recorded run on the real repo (scripts/arch-check --no-fix, 116.6 s, exit 1): a planted def in a new package chat_cordis_plugin/zz_planted/__init__.py (new module in an existing member) and in a new member bh-02/plugins/zz-planted-cordis-plugin (UV_FROZEN=1 UV_NO_SYNC=1 so uv did not lock or install it) were both reported by init-reexport-only; both removed, the next run exit 0 with the root pyproject's src back as committed.

scripts/check: plan() (frozen Step/Skipped) -> every step started at once in a thread pool, stdout+stderr captured, printed whole in plan order with '== name' and 'ok' / 'FAILED: name' as before; a step that cannot start FAILS with the command named; exit 1 if any failed; scripts/check MEMBER unchanged (checked: scripts/check libs/host-paths --no-gates --no-docs exit 0). Not kept: pytest's live dots and ruff/mypy/pytest colour (output is captured, as asked). Only shared write: arch-check rewrites the root pyproject's pypeeker src when a member is added; no test reads that file.

Times (4 cores, nothing else running; per step, seconds).
BEFORE (old scripts, old pin cf4f168): wall 732 s = format 0.1, lint 0.1, types 0.5, tests 466.1, gates 262.5, docs 2.3. arch-check --no-fix alone 236 s.
Pin only (old arch-check, new pin): arch-check --no-fix 198 s. Gates on the new pin: root check --strict 86 s, cordis 3.0, cordis-helpers 0.3, host-paths 0.5, brig 7.3.
AFTER (new scripts, new pin, via a scratchpad copy that adds each step's time): wall 487 s = format 0.1, lint 0.1, types 0.6, tests 487.0, gates 95.4, docs 2.6 (steps overlap; tests 2772 passed, 31 skipped, 16 more than before; they took 21 s longer than alone, CPU shared with the gates). The real scripts/check, run last: exit 0, wall 478 s, same results. arch-check --no-fix on a clean tree with the new files to index: 93.7 s (exit 0). Not changed by this: scripts/arch-check in its default mode (with --fix) took 244 s (check --strict --fix alone 131 s vs 82 s plain check), upstream pypeeker's fix pass; scripts/check uses --no-fix.

Exit codes read directly, one at a time, foreground: uv run mypy 0 (186 files); ruff format --check 0, ruff check --no-fix 0; scripts/arch-check (default) 0, --no-fix 0; scripts/check 0. Not run: scripts/linux-jail-check (nothing here touches the jail).

Closed on the independent review (Opus low, did not do the work): CLOSE.
- AC #1: pyproject pins pypeeker @7905d24; uv.lock carries the full sha; uv lock --check exits 0; the installed copy's direct_url.json names commit 7905d240.
- AC #2: met, and stronger than its words: a path is indexed when any .py file under it has no entry. The reviewer planted a layering violation and a new subpackage in the real repo (exit 1, all three findings), renamed and deleted them (the rename reported at its new path, the deleted entry dropped, no ghost finding), then removed both (exit 0, 97.7 s); afterwards no gate had a file without an entry.
- AC #3: a misformatted file planted in libs/host-paths/tests: exit 1, FAILED: format, the other steps reported ok in plan order.
- AC #4: the reviewer's scripts/check exited 0 in 8m12s (tests 489 s, 2772 passed, 31 skipped), against 12m12s before; uv run mypy exits 0. brig: 1029 passed, 24 skipped.
- Guards: test_check_script with max_workers=1 fails exactly the two tests that guard concurrency.
Should-fix (sync_src's non-atomic write of pyproject.toml while pytest, ruff and mypy read it) joined TASK-0103 as AC #4. Nits answered here: AC #2's wording is narrower than what was built and the notes say why; captured output hides a long test run's progress (noted on TASK-0103); test_arch_check.py sits in bh-02/app/tests beside test_check_script.py, where the repo's script tests are.
<!-- SECTION:NOTES:END -->
