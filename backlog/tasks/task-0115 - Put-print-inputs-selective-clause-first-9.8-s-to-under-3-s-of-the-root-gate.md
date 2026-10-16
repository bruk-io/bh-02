---
id: TASK-0115
title: 'Put print-input''s selective clause first: 9.8 s to under 3 s of the root gate'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 08:19'
updated_date: '2026-10-16 11:58'
labels:
  - gates
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. print-input, one of this repository's own rules (pypeeker_rules/apps.py, _print_input), takes 9.8 s of the root gate's 106 s on a warm run (in-process timing; 9%). It is written as references().where(all_of(in one of the units, not in an allowed module, symbol id is <builtins>.print or <builtins>.input)): the first clause is an any_of over every unit's module test (about twenty), evaluated for each reference row, and the last clause, the one that keeps almost no rows, is evaluated only for the rows that pass the first two.

Measured saving: with the symbol-id test first and the same three clauses after it, the rule is 2.7 s (as written: 10.1 s, rule alone, same corpus) and the root gate's check is 106.1 s -> 99.4 s in-process (median of 3). On a scratch copy with a planted print() and input() in a module outside the allowed list the same two findings come out, word for word, in both orders.

The other rules in the file (terminal-io 1.0 s, plugin-layering 1.3 s, cordis-in-wiring-only 1.0 s, cordis-public-api 0.7 s, brig-one-adapter 0.7 s, worker-stdlib-only 0.6 s, init-reexport-only 0.5 s) are under 1.5 s each; leave them unless a clause is plainly the selective one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pypeeker_rules/apps.py's print-input tests the symbol id (print or input) before the unit and allowed-module clauses; the rule takes under 4 s on a warm run (9.8 s before, in-process timing)
- [x] #2 A planted print() and input() in a unit module outside the allowed list are reported, the same two findings as before the change, by a test or a recorded run
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Save HEAD's pypeeker_rules/apps.py as the before variant (scratch, not the repo). 2. Timing: a scratch driver (not committed) loads one variant of apps.py, runs ensure_fresh untimed (what check does first), then times the print-input rule alone over a fresh Corpus on the root index; before/after interleaved, 3 pairs, median and paired difference. 3. Edit _print_input: the symbol-id clause (with its comment) first, the unit and allowed clauses unchanged after it; nothing else in apps.py. 4. Criterion 2: no test home for gate rules exists (pypeeker_rules has no tests), so a scratch copy of the worktree (no .git) gets a planted print() and input() in memory_cordis_plugin, indexed; pypeeker check --strict run there with the before and after apps.py, both outputs recorded and compared. The plant is never in the worktree. 5. Risks: machine shared (noisy timings, so paired medians); findings must match word for word. 6. Proof: ruff format/check on apps.py; scripts/arch-check --no-fix exits 0 in the worktree under tini; scripts/check not run (no member changed) and the full check is not mine to prove. One commit, attribution lines as given.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementation (worker, 2026-10-16). Changed: pypeeker_rules/apps.py only, _print_input. The symbol-id clause (any_of print/input, with its builtins comment) is now the first clause of all_of; _in_units(units()) and the allowed clauses follow unchanged; one comment line above the symbol-id clause says why it is first. git diff: 1 file, 3 insertions, 2 deletions. The rule itself is unchanged in meaning.

AC1 timing. Method: scratch driver outside the repo (scratchpad 0115/time_rule.py, not committed). One process per run: read_config, IndexStore, ensure_fresh untimed (as check does first), then print-input alone over a fresh Corpus on the root index, timed; findings recorded. The before variant is HEAD's apps.py (checked equal to git show HEAD). Runs interleaved as pairs (before, after / after, before / before, after), in-process seconds: before 10.077, 10.586, 10.591 (median 10.586); after 2.609, 2.459, 2.709 (median 2.609); paired differences 7.47, 8.13, 7.88 (median 7.88). Root findings: 0 both. Machine shared with two other workers (load average 0.7 to 1.2 during these runs, 2.5 later): noise is in the seconds, the pairing holds the order. Under 4 s: met (2.6 s).

AC2 planted run. No test home exists for gate rules (pypeeker_rules has no tests), so a recorded run: a scratch copy of the worktree (no .git, no .claude; outside the repository), with bh-02/plugins/memory-cordis-plugin/src/memory_cordis_plugin/planted_print.py added (_ask: print(text), input(...)), indexed with pypeeker index, then pypeeker check --strict run in the copy (PYTHONPATH the copy root, as arch-check does) with HEAD's apps.py and then with the edited one. Both runs exit 1 and report, word for word, the same lines: planted_print.py:5 [print-input] '<builtins>.print' and :6 [print-input] '<builtins>.input' (plus the same no-impure-functions finding at :4, which is another rule). diff of the two whole outputs: identical. The plant exists only in the scratch copy, never in the worktree or a commit. The copy was made before the final wording of the comment; the code is the same.

Proof: scripts/arch-check --no-fix (tini -s --, in the worktree): exit 0, 1m39s. ruff format --check and ruff check --no-fix on pypeeker_rules/apps.py: pass. scripts/check not run: no member changed (the rule file is outside every member), and the full check is the reviewer's to prove. git status: only pypeeker_rules/apps.py modified.
<!-- SECTION:NOTES:END -->
