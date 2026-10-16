---
id: TASK-0119
title: >-
  arch-check: say so when dropping a gate's orphan index entries leaves any
  behind
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 12:14'
updated_date: '2026-10-16 14:17'
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
From TASK-0118's close review. scripts/arch-check's drop_entries unlinks orphan index entries by pypeeker's storage layout (.pypeeker/index/<path>.json, what IndexStore.remove unlinks) with missing_ok, since pypeeker has no command for it. If pypeeker's layout changes, the drop becomes a silent no-op: the orphans come back and the gate slows again with nothing said. After the drop, read indexed() again and fail the gate, naming the entries, if any it meant to drop is still listed; the docstring says why.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After dropping, scripts/arch-check fails the gate with a message naming the entries if any entry it dropped is still indexed, and a test shows it with an index whose entry file is not where the layout says
- [x] #2 drop_entries' docstring says what a layout change would do and that the check catches it
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. scripts/arch-check: pure left_behind(dropped, entries) returning the problem text (each dropped entry still in entries, named, with what to do) or None, beside outside_src. run_gate reads indexed(gate) a second time after drop_entries, calls left_behind, returns Outcome(False, problem) on a problem, and hands the same second read to without_index (no extra read). drop_entries' docstring says a layout change makes the unlink a silent no-op (missing_ok) and that run_gate's re-read catches it; module docstring gets a clause. 2. Tests in bh-02/app/tests/test_arch_check.py: pure cases (all gone, some left, nothing dropped, an entry that is listed but was not dropped is not named); integration: a fixture runs the real drop_entries with the layout it believes in moved (INDEX patched for the call), so an index whose entry files are not where it looks; gate with member b out of src fails naming b's entries, exit 1, nothing indexed or checked; the same gate without the moved layout passes. Plant: remove the left_behind check from run_gate, see the integration test fail, restore (cmp). 3. Proof: uv run pytest on the test file; scripts/check bh-02/app --no-gates --no-docs; scripts/arch-check once at the end of both tasks. Risk: a layout change that also changes what indexed() reads is not caught by this (the first test, which pins indexed() to what pypeeker writes, is what notices that); say so in the docstring.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0119 worker notes (branch wt-w1, from ac91bcc).

## What changed
- scripts/arch-check: pure left_behind(dropped, entries) -> the problem text, naming each dropped entry the index still lists (one per line, with where to look: INDEX and drop_entries against pypeeker/storage/index_store.py), or None. run_gate reads indexed(gate) once more after drop_entries, returns Outcome(False, problem) on a problem (before indexing or checking), and hands that same read to without_index, so no read is added. drop_entries' docstring now says a layout change makes the unlink (missing_ok) a silent no-op, the orphans stay and the gate slows again, that run_gate's re-read catches it, and what it does not catch (a change that moves where indexed() lists entries too, which the clean-gate test notices). run_gate's and the module docstring say so too.
- bh-02/app/tests/test_arch_check.py: 3 tests and a fixture. Pure: an entry dropped and still listed is named, one never dropped (inside src) is not; nothing is left behind when all are gone or none was dropped. Integration (fixture layout_moved: the real drop_entries run with INDEX pointing at .pypeeker/index-v2, so the index's entry files are not where it looks): member b leaves src, the run exits 1, the message starts 'arch-check: dropped 2 index entries that are still listed' and names b's two entries, they are still indexed, and nothing was indexed or checked.

## Evidence
- uv run pytest bh-02/app/tests/test_arch_check.py -q: 30 passed.
- Planted and seen failing: with the left_behind check removed from run_gate the integration test fails (assert 0 == 1: the run is green with the orphans still indexed, the silent no-op); script restored (cmp against the saved good copy) and 30 passed again.
- scripts/check bh-02/app --no-gates --no-docs: exit 0 (format, lint, types, 228 passed 1 skipped; tokens skipped, no bh-01 dist).
- scripts/arch-check runs once at the end of TASK-0120, which follows this on the same files.

Review: CLOSE. AC1 met: run_gate re-reads indexed() once after drop_entries and hands that same read to without_index (two reads, as before); left_behind names each dropped entry still listed; the layout_moved integration test exits 1 naming b's entries, seen failing with the check removed; a clean gate drops nothing so left_behind returns None. test_arch_check.py 38 passed on re-run; full scripts/check green at eedde1e. AC2 met: drop_entries' docstring says a layout change makes the missing_ok unlink a silent no-op that slows the gate, that run_gate's re-read catches it, and what it cannot catch. Findings: none blocking or should-fix; no drafts filed.
<!-- SECTION:NOTES:END -->
