---
id: TASK-0115
title: 'Put print-input''s selective clause first: 9.8 s to under 3 s of the root gate'
status: To Do
assignee: []
created_date: '2026-10-16 08:19'
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
- [ ] #1 pypeeker_rules/apps.py's print-input tests the symbol id (print or input) before the unit and allowed-module clauses; the rule takes under 4 s on a warm run (9.8 s before, in-process timing)
- [ ] #2 A planted print() and input() in a unit module outside the allowed list are reported, the same two findings as before the change, by a test or a recorded run
<!-- AC:END -->
