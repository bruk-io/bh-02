---
id: TASK-0125
title: >-
  pypeeker: let check --fix report the findings it leaves, so arch-check runs a
  red gate's rules once
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 14:12'
updated_date: '2026-10-16 22:59'
labels:
  - gates
  - size-2
  - finish-moved
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0120. scripts/arch-check now runs the plain check first and only runs check --strict --fix on a gate with findings, so a clean gate's rules run once (118 s to 48 s with --fix). A gate whose findings have no fix still runs them twice: pypeeker's --fix report holds fixes, skipped_conflicts, declined, residual_violations (a count only) and tx_id, and the plain check's output does not mark which findings a fix could repair, so the script cannot skip --fix nor print the findings left from the --fix run. The change is upstream: --fix's report carries the residual findings as text (or check marks fixable findings), then arch-check uses it, and the pin is bumped.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pypeeker (upstream) gives the findings a --fix run leaves, as text in its report or a marker in check's output, and the root pin names the merged commit, uv.lock regenerated with uv
- [x] #2 scripts/arch-check runs a gate's rules once when no fix applies, findings and exit code unchanged, shown by a test, and its time on a gate with findings is recorded before and after
- [ ] #3 A clean gate's `scripts/arch-check` run with --fix is no slower than before this task (TASK-0120 left it at the plain check's cost), measured paired on the same machine
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. pypeeker (branch wt-0125 in its worktree). check --fix builds its JSON report in cli._apply_check_fixes from shown = the fresh run's findings after the confidence filter; plain check prints str(v) for each of the same kind of list. Add one pure helper, _finding_lines(shown), that is the single rendering of a shown finding, call it from plain check and from the report, and add the key residual_findings (the lines, in the order plain check prints them) beside residual_violations. The key is optional, as applied and the file lists are: present exactly when residual_violations > 0, so the report of a clean run stays byte-identical (test_clean_project_fix_is_a_no_op and architecture.md's 'byte-identical on every path' keep holding) and the count and every other key are untouched. It covers --fix-until-clean too, since both build the report from shown. Document in the _apply_check_fixes docstring and architecture.md (Output contract, check --fix paragraph).
2. pypeeker tests (tests/test_check_fix.py, a class beside TestCheckFixCli): residual_findings equals the lines a plain check then prints on the same tree, with a fix applied (COMBINED_SOURCE leaves 'keep') and with none (a finding with no remedy); --strict shows a heuristic finding and its line equals plain check --strict's, without --strict it is hidden from both; --fix-until-clean; a clean run has no key. The golden/exact-dict tests that run with a residual finding gain the key. Proof the tests guard: run them before the change (they fail on the missing key) and with the helper replaced by a different rendering (the equality tests fail), then restore. scripts/verify-repo.sh once at the end.
3. bh-02 scripts/arch-check, with --fix: run check --strict --fix once, FIRST. Exit 0: the gate is clean (pypeeker's own verdict, after fixing), print the applied line. Non-zero with a report: print the applied line then the report's residual_findings (no re-check); not JSON, or a JSON without residual_findings (an error envelope, or a pypeeker older than the key): fail with what pypeeker said. The plain check first, kept for a clean gate? It is cheaper (clean gate here: plain 36 s, --fix 54 s, two rounds, load 0.7-1.8; TASK-0120 had 48 against 74 s), but keeping it makes every gate with findings run the rules twice (plain, then --fix), which is exactly what this task removes, and the red gate with no fix would take the same time before and after. So it goes: the cost is a clean gate paying --fix's collection of repairs (+18 s here, +26 s in TASK-0120's measure); I record it, and report that a pypeeker change (skip that collection when the run has no findings) would give it back (not made here: out of scope). --no-fix is unchanged (one plain check).
4. bh-02 tests (bh-02/app/tests/test_arch_check.py): rewrite the --fix tests for the new flow with the existing spy on check calls: clean (one --fix call, no output), findings no fix applies to (ONE call: --fix, findings as the plain check prints them, exit non-zero, the new test), fix applied and clean (one call, note), fix applied and findings remain (one call: note then the finding, no re-check), exit code through main with three gates, non-JSON --fix output, error envelope / report without residual_findings (fails with what pypeeker said), --no-fix (one plain call). The tests run on the editable pypeeker of this worktree, so they pass only with the new key; the pin bump is the orchestrator's. Plant: restore the old flow, see the call-count tests fail; restore.
5. Timing (AC2): scratch copy of bh-02 at HEAD (git archive, warm .pypeeker copied) with one planted finding no fix applies to (a definition in a package __init__, init-reexport-only); before = HEAD's script with the pinned pypeeker (/home/user/bh-02/.venv, read-only), after = the new script with this worktree's pypeeker; whole 5-gate run with --fix, interleaved, 3 pairs, median, tini -s --, same output and exit code checked; the clean gate alongside (the cost of dropping the plain-first). Shared machine, load noted.
6. Proof: pypeeker scripts/verify-repo.sh once; bh-02 scripts/check bh-02/app (gates and docs once) with UV_NO_SYNC=1, scripts/arch-check --no-fix --no-fix once because scripts changed (UV_NO_SYNC=1 scripts/arch-check --no-fix); AC1's pin/uv.lock part and 'scripts/check passes' are the orchestrator's/reviewer's, left unticked.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Orchestrator, 2026-10-16: finish moved after the work. The worker dropped the plain-check-first step so a red gate runs once (93.1 s to 56.2 s), but that made the clean gate, every green CI and pre-commit run, 17.7 s slower (37.1 s to 54.8 s): TASK-0120's gain undone. The worker's prototype (pypeeker's plan_check_fixes skips collecting repairs when the run has no findings) took a clean --fix from 54.8 s to about 37 s. Added criterion 3 so the clean gate does not regress; the skip goes into the same pypeeker change.

TASK-0125 worker notes (bh-02 branch wt-0125 from 41b5bbb; pypeeker branch wt-0125 from 8e42118, commit 8f0e223, code the same as the pin 67b0a1b).

## What changed
pypeeker (8f0e223): src/pypeeker/cli.py, tests/test_check_fix.py, tests/test_check_fix_until_clean.py, architecture.md.
- check --fix's report gains residual_findings beside residual_violations: the lines a plain check prints (str of each shown finding, same order, same confidence filter), so residual_violations == len(residual_findings). One function, cli._finding_lines, now renders a finding for plain check, check --baseline and the report, so they cannot word a finding differently. No existing key moved.
- Deviation from my plan (item 1 said an optional key, present only when findings remain): the key is on EVERY report (an empty list when clean), like fixes. The first version (optional) broke test_the_flagged_report_is_a_strict_superset: plain --fix leaves a residual finding, --fix-until-clean cleans it, so the loop's report would lack a key the plain one has, which the report's own rule forbids (the loop report is a superset). Always-present keeps that rule and makes count and list always paired. Cost: the three tests that pin the report whole (test_clean_project_fix_is_a_no_op, the golden capture, the default key set) gain the key; nothing else changed.
bh-02: scripts/arch-check (fix_outcome, run_gate, docstrings) and bh-02/app/tests/test_arch_check.py.

## Plain check first, kept for a clean gate? No (the plan's question)
Measured on the root gate (same corpus, 2 rounds, load 0.7-1.8): plain check 36.5, 35.7 s; check --fix on a clean gate 54.0, 55.4 s (TASK-0120: 48 against 74). The plain check IS cheaper for a clean gate, by about 18 s. Kept first, though, a gate with findings runs the rules twice (the plain check, then --fix), the red gate with no fix takes the same time before and after, and the criterion is that it runs once. So --fix runs first and alone; exit 0 is the verdict, the report's residual_findings are the findings. The price is a clean gate paying --fix's collection of repairs: +17.7 s (below). Not made here (out of scope, reported): when run.findings is empty plan_check_fixes could skip that collection (it runs every fixable rule again); prototyped in-process with a patch, nothing changed in pypeeker: clean check --fix 36.5 and 38.6 s, i.e. a plain check's cost, which would give the clean-gate time back.

## scripts/arch-check now (with --fix)
One pypeeker check per gate: check --strict --fix. Exit 0 -> clean, prints the applied line if a fix landed. Non-zero -> the applied line, then the report's findings, one per line, then stderr. Not JSON, an error envelope, or a failing report without findings (a pypeeker older than the key) -> fails with what pypeeker said. --no-fix: one plain check, unchanged. Findings, the applied line and the exit code are as before in every case: shown by the tests, and by the timing runs below (byte-identical output).

## Evidence
- pypeeker: uv run pytest tests/test_check_fix.py tests/test_check_fix_until_clean.py -q: 96 passed. New tests (class TestResidualFindings, 6): findings equal a plain check's lines after a fix applied (COMBINED_SOURCE), with none applied (two public-unused findings), under --strict (heuristic finding listed with its [heuristic] marker, equals plain --strict) and without it (hidden from both, list empty), with --fix-until-clean, with --plan, and a clean run (empty list, plain check prints nothing). Seen failing: before the change 5 of 6 failed with KeyError: 'residual_findings' (the 6th, the clean run, expects an empty list and failed too only after I changed it; it passed in the optional-key version); with the report rendering findings as path:line only (planted, restored, cmp) 6 tests failed: the 5 above and the golden capture.
- pypeeker scripts/verify-repo.sh (once, at the end): pytest 3884 passed 11 skipped, ruff passed, self-lint passed, OVERALL: PASS.
- bh-02: UV_NO_SYNC=1 uv run pytest bh-02/app/tests/test_arch_check.py: 40 passed, on this worktree's pypeeker (editable). Planted: the previous script (git show HEAD:scripts/arch-check) put back under the new tests fails 8 (clean gate = one --fix call, no-fix findings = one call, fix applied and clean = one call, findings left after a fix = one call, and the four report-shape tests); restored, cmp identical, mode kept. New tests: clean (checks == [--fix]); findings no fix applies to (checks == [--fix], output equals a plain check's on the same gate); fix applied and clean (one call, note, file fixed); fix applied with findings left (one call: note then the finding, equal to what a plain check then prints); exit code through main with three gates; non-JSON output; error envelope; a failing report with a count and no findings; a report with findings printed whole between the applied line and stderr; --no-fix (one plain call). The old 'a --fix that applied nothing and says clean is not believed' test is gone: it described the plain-check-first disagreement.
- UV_NO_SYNC=1 scripts/check bh-02/app (first run, with gates and docs): format and lint failed on one 112-character line in my new test (formatted; ruff format and ruff check then green); types, 240 tests, five gates ok, docs ok. Then scripts/check bh-02/app --no-gates --no-docs: exit 0 (format, lint, types, 240 passed 1 skipped). UV_NO_SYNC=1 scripts/arch-check (the default, --fix): exit 0, five gates ok, tree unchanged, 55.5 s. scripts/arch-check --no-fix ran as the gates step of scripts/check (ok); the script's --no-fix branch is unchanged.

## AC2 timing: scripts/arch-check --fix, five gates, wall seconds
Setup: scratch copy of bh-02 at 41b5bbb (git archive, warm .pypeeker copied) under the session scratchpad, never committed; before = 41b5bbb's script with the pinned pypeeker (/home/user/bh-02/.venv, read only), after = this script with this worktree's pypeeker; each run a full five-gate run driven in-process (the script loaded as a module, PYPEEKER set to the binary), under tini -s --, interleaved, order alternated, 3 pairs, after a warm-up run. Machine shared with two other workers (load average 1.2-2.4 after each run), so absolute figures are noisy.
- Gate with findings no fix applies to (a planted function that calls print in a root-gate module: no-impure-functions, over-exposed-module-symbol and print-input fire; --fix applies nothing):
  before 94.7, 93.1, 92.7 s (median 93.1); after 57.1, 55.0, 56.2 s (median 56.2). Paired differences 37.6, 38.1, 36.5; median 37.6 s (40% less): the plain check and --fix become one --fix. All six runs exit 1 and print the same bytes (cmp, before against after, each pair; the old flow's warm-up too).
- Clean gate (the plant removed), the price of dropping the plain-first: before 35.8, 37.8, 37.1 s (median 37.1); after 54.5, 54.8, 55.7 s (median 54.8): +17.7 s (+48%). Same output (cmp).
- Fix applied: not timed (it would change the tree). By count: before a plain check, --fix (collect, apply, rerun) and, with findings left, another plain check; now the one --fix.

## Left for the orchestrator / not verified
- AC1 left unticked: the pypeeker half is done (8f0e223, not pushed); the root pin naming the merged commit and uv.lock regenerated are yours. Until the pin is bumped, test_arch_check.py in a checkout with the pinned pypeeker fails the tests that read residual_findings (the script then fails a red gate with the report's text, by design).
- AC2 ticked with evidence from this worktree (editable pypeeker); the reviewer proves scripts/check.
- Worth doing, unsized, not filed: pypeeker skips the repairs collection in check --fix when the run has no findings (clean --fix 54.8 -> about 37 s by the prototype), after which fix-first costs a clean gate nothing.

Correction to the evidence above: the pre-change run (5 of 6 new tests failed with KeyError: 'residual_findings') was of the first, optional-key version of the tests; the sixth then asserted the key was absent and passed. I then made the key always present and rewrote that test to expect an empty list, and did not re-run the final tests against the unchanged code; the planted rendering (path:line only) failed 6 tests of the final version.
<!-- SECTION:NOTES:END -->
