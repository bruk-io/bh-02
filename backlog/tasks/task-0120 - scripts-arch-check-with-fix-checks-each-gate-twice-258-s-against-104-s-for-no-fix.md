---
id: TASK-0120
title: >-
  scripts/arch-check with --fix checks each gate twice: 258 s against 104 s for
  --no-fix
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 12:19'
updated_date: '2026-10-16 14:17'
labels:
  - gates
  - scripts
  - size-2
  - finish-moved
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0116 (its worker measured it; its close review noted it). scripts/arch-check's default mode runs pypeeker check --strict --fix, which prints a JSON report of the fixes it applied rather than findings, then a plain check --strict for the findings and the exit code, so every gate's rules run twice: 258 s with --fix against 104 s with --no-fix on a shared machine. Find whether pypeeker's --fix run can give the findings left after fixing (its report, a flag, or a check that runs only when a fix was applied), so a run that applied nothing checks once.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Its wall time with --fix before and after is recorded in the notes
- [x] #2 scripts/arch-check (with --fix) runs a clean gate's rules once; a gate with findings still reports the findings left and exits non-zero (it still runs them twice when no fix applies, until TASK-0125), shown by tests
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Read pypeeker's check --fix (done: cli._apply_check_fixes, app/fix_run.plan_check_fixes). Facts: --fix runs run_check once (findings), collects remediations (only rules with a mutation are rendered, over a warm corpus), plans, applies, and only when it applied something runs the rules again (run.rerun) for the residual. Its JSON report holds fixes/skipped_conflicts/declined (each with the finding it addresses), residual_violations as a COUNT, tx_id; it exits non-zero iff residual findings (honouring --strict) remain, and the residual is the run's own findings when nothing applied. It never prints the findings that have no fix, so text for those needs a plain check. Today the script then always runs a plain check: clean gate 2 runs, fix applied 3.
2. Choice: run --fix FIRST, trust its exit code, and run a plain check only when it exits non-zero (to get the findings text). Not 'plain first, then --fix': per case (rule runs, now / plain-first / fix-first): clean 2 / 1 / 1; findings with no fix 2 / 2 / 2; fix applied and all fixed 3 / 3 (plain, then --fix with its rerun) / 2; fix applied and findings remain 3 / 4 / 3. Fix-first is never worse and the usual run (a clean gate) is one run either way. The floor for findings with no fix is 2 without a pypeeker change (the report has a count, not text): the AC's 'once when no fix applies' holds for a clean gate, and I say so in the notes. Findings, the applied-fix line and the exit code are as now in every case: exit 0 iff the gate is clean after fixing (pypeeker's own verdict when --fix exits 0, the plain check's otherwise); a non-JSON --fix output still fails with its text.
3. scripts/arch-check: pure applied_note(report) (the existing line), run_gate returns right after --fix when it exits 0; module and run_gate docstrings. Tests in bh-02/app/tests/test_arch_check.py, with a spy on arch_check.pypeeker recording each check call: clean (one --fix call, no plain check), findings with no fix (--fix then plain, findings reported, exit non-zero through main too), fix applied and clean (one call, note, file fixed), fix applied and findings remain (both calls, note then finding), non-JSON --fix output (fails with its text, no plain check), --no-fix (one plain call). Plant: put back the unconditional plain check, see the clean and fix-applied tests fail, restore (cmp).
4. Timing: old script (copy of the current one at scripts/.arch-check-before, untracked, removed after) vs new, scripts/arch-check --fix on this checkout, paired and interleaved, 3 pairs, median, shared machine (load average noted). Same exit codes and output checked.
5. Proof: test file; scripts/check bh-02/app --no-gates --no-docs; scripts/arch-check and scripts/arch-check --no-fix once each at the end. Risk: the first --fix run on a gate with a stale index is also what refreshes it; unchanged.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0120 worker notes (branch wt-w1, on top of TASK-0119's commit ae0e42e).

## What pypeeker's --fix holds (read in .venv: cli._apply_check_fixes, app/fix_run.plan_check_fixes)
run_check evaluates the rules once; the fix pass then collects the repairs of the rules that have a mutation (a fresh Corpus), plans, applies, and only when it applied something runs the rules again (run.rerun) for the residual. The JSON report is {fixes, skipped_conflicts, declined, residual_violations (a COUNT), tx_id} (plus applied and the file lists when applied); each fix entry carries the finding it addresses, but a finding with no fix appears nowhere as text. It exits non-zero exactly when findings (honouring --strict) remain; with nothing applied the residual is the run's own findings. So no flag gives the findings text, and findings with no fix cannot be read from a --fix run without a pypeeker change (an upstream report holding the findings would do it; reported, not filed).

## The choice, and why (measured, not only counted)
Plain check first; stop if it passes (one run). Only with findings run --fix: nothing applied and exit non-zero -> the findings printed stand (no third run); applied and exit 0 -> clean, done; applied and findings remain (or the two disagree) -> a plain check again for the text, since a fix moves lines. The alternative I measured first, --fix first and a plain check only on a non-zero exit, is cheaper when a fix applies (one run less) but a clean gate pays --fix's own run, which is dearer than a plain check (it collects each fixable rule's repairs): fix-first on this clean checkout, 3 pairs, load 1.4-4.1 (shared): before 118.9, 118.1, 120.5 (median 118.9 s); fix-first 86.1, 73.1, 74.2 (median 74.2 s). Plain-first, the same state: see below, 48.1 s. Per case, in whole runs on the root gate (P a plain check ~47 s, F a --fix with nothing to apply ~74 s, F' a --fix that applied, ~F+P): clean: now F+P, plain-first P, fix-first F; findings with no fix: F+P all three; fix applied and all fixed: now F'+P, plain-first P+F' (the same as now), fix-first F'; fix applied and findings remain: now F'+P, plain-first P+F'+P (one plain check more than now), fix-first F'+P. Plain-first wins when clean runs are more than about 1.5 times as many as runs where a fix applied (29 s saved on each clean run against 45 s lost on each applied one), and a clean run is the usual one (a fix is followed by a clean run). The only case plain-first makes dearer than now is a fix applied with findings left, by one plain check.
What stayed the same in every case: findings text, the 'pypeeker applied N fix(es): tx ID' line, and the exit code (zero iff the gate is clean after fixing; a non-JSON --fix output still fails with its text). Findings with no fix applying still run twice (the plain check, then --fix): that is the floor without a pypeeker change.

## What changed
- scripts/arch-check: run_gate runs the plain check first (as --no-fix does), returns on a pass or with fix off, else runs --fix and decides as above; pure applied_note(report) (the existing line, now a function); module and run_gate docstrings.
- bh-02/app/tests/test_arch_check.py: a spy fixture on the check calls, and tests for each case (calls in order, output, outcome): clean gate (one plain check, no --fix); findings no fix applies to (plain, --fix, the findings as printed, no third run); a fix that leaves the gate clean (plain, --fix, only the applied line, file fixed); findings left after a fix (plain, --fix, plain: applied line then the finding); the exit code through main with three gates (one fixed, one with findings left: exit 1, FAILED naming it); --fix output that is not the report (fails with its text, no recheck); --fix that applied nothing but exits 0 (not believed, checks again); --no-fix (one plain check).
- CLAUDE.md: the command line says autofixes apply to a gate that has findings.

## Evidence
- uv run pytest bh-02/app/tests/test_arch_check.py -q: 38 passed.
- Planted and seen failing, script restored each time (cmp): the previous script (HEAD, --fix first then a plain check) fails 6 tests (the call order of every --fix case); the 'nothing applied and non-zero' shortcut removed fails the no-fix-findings test (a third run); the recheck replaced by the stale first findings fails the findings-left-after-a-fix test and the disagreement test. The exit-code test and the three-gate applied-fix test pass with the old and the new script (same exit codes and reports).
- Same output and exit code on this checkout: all nine timing runs below exit 0 and print the same 110 bytes (cmp).

## AC2: scripts/arch-check --fix wall time on this checkout (clean tree, warm index), before and after
Machine shared with the other workers (load average 1.1-1.6 at the start of each run). Paired, interleaved, 3 rounds, order rotated, each run a full 5-gate run through uv run --script; before = the script at TASK-0119's commit (--fix, then a plain check), after = this one; --no-fix (this script) alongside for reference.
- before: 118.4, 117.8, 121.9 s; median 118.4
- after: 44.5, 50.6, 48.1 s; median 48.1
- --no-fix: 46.8, 47.7, 48.2 s; median 47.7
Paired differences before - after: 73.8, 67.2, 73.8; median 73.8 s (60%). A clean --fix run now costs what --no-fix costs. (The 258 s of TASK-0116 against 104 s was a heavier moment of the same machine; the ratio, 2.5, is 2.5 here too: 118.4 / 47.7.) Not timed: the fix-applied and findings-left cases on the root gate (they cost what they did before, plus one plain check when a fix applied and findings remain).
- AC1 shown by the clean-gate test (one check, no --fix) and the findings tests above: reported and non-zero in every case. Findings with no fix applying run twice, said above and in the script's docstring.
- scripts/arch-check and scripts/arch-check --no-fix once each, and scripts/check bh-02/app --no-gates --no-docs: see the closing note.

## Closing note (final runs, after the last edit to the test file's docstring)
- scripts/arch-check (default, --fix): exit 0, five gates ok, tree unchanged (git status shows only my three files). scripts/arch-check --no-fix: exit 0, five gates ok.
- scripts/check bh-02/app --no-gates --no-docs: exit 0 (format, lint, types, 236 passed 1 skipped; tokens skipped, no bh-01 dist). The first run failed lint on a 114-character docstring line in the new test; shortened, then green.
- AC #1 left unticked on purpose: it holds for a clean gate (one pypeeker check, no --fix: test_a_clean_gate_with_fix_runs_one_check_and_no_fix) and findings are reported with a non-zero exit in every case (the tests above), but a gate with findings that no fix applies to still runs the rules twice (plain check, then --fix). Without a pypeeker change the --fix report holds only a count of those findings, so there is no way to read them from a --fix run; the reviewer rules on whether that reading of 'once when no fix applies' is the intent. Upstream, a --fix report (or flag) that carries the findings left would remove the second run; not filed (parallel workers).
- Correction to the AC2 note: 'a heavier moment of the same machine' explaining 258 s against 118 s here is a guess I did not test; what I measured is 118.4 s before and 47.7 s for --no-fix, a ratio of 2.5 like the 258/104 of TASK-0116.

2026-10-16, orchestrator: finish moved after the work. Criterion 1 asked for one run "when no fix applies"; the worker showed pypeeker gives no way to meet it for a gate whose findings have no fix (the --fix report carries only a count, and check marks no finding as fixable). Narrowed to the clean gate, the case the task was filed for (every green CI and pre-commit run, 118 s to 48 s), with the red-gate case moved to TASK-0125 (an upstream pypeeker change, then a pin bump).

Review (closing reviewer): CLOSE. Full scripts/check passed at eedde1e (exit 0, 3226 passed, five gates ok), not re-run per orchestrator. test_arch_check.py re-run: 38 passed. AC1 met: before/after timing in notes (118.4 s -> 48.1 s median). AC2 met: clean gate one plain check (test_a_clean_gate_with_fix_runs_one_check_and_no_fix); every new path traced against the old two-run version: same findings text, applied line and exit code; non-JSON --fix still fails with its text. Narrowing judged honest: the description asked that 'a run that applied nothing checks once', and the clean gate is the run it was filed for; the no-fix red gate genuinely needs an upstream change and TASK-0125 carries it with criteria. Nit (not filed): when a fix applies and --fix exits 0, the plain recheck's stdout is no longer appended; harmless since a passing check --strict prints nothing of note.
<!-- SECTION:NOTES:END -->
