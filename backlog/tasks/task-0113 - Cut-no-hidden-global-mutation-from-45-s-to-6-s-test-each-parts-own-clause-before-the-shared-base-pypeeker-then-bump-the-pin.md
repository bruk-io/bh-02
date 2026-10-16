---
id: TASK-0113
title: >-
  Cut no-hidden-global-mutation from 45 s to 6 s: test each part's own clause
  before the shared base (pypeeker, then bump the pin)
status: To Do
assignee: []
created_date: '2026-10-16 08:19'
labels:
  - gates
  - size-2
dependencies: []
priority: high
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. On a warm run (the index is current) scripts/arch-check --no-fix takes 115.6 s here (4 cores, nothing else running), and the root gate's pypeeker check --strict is 89% of it. The biggest single cost in that check is the rule no-hidden-global-mutation: 44.7 s of the gate's 106 s (in-process timing; 42%).

Why: the rule has four parts and three of them (outer-scope write, mutator call, attribute write on an import) are built on the same base in pypeeker/dsl/mutation_rules.py, _global_base: references().where(in a function).where(not allowed), and only then the clause that picks the rows out (kind, attribute access, receiver kind). The base walks every reference row and tests the rule's allow patterns (fnmatch against the function id and against its module, three patterns, so six tests a row, each building a derivation) before the cheap kind test throws almost every row away. Timed one part at a time (parts_time script, scratch): the base alone is 14.0 s; the three parts as written are 14.5, 14.1 and 15.0 s; the same three with every clause kept and the base moved last are 1.4, 2.1 and 1.6 s, with the same rows (none here). Where the DSL stops at the first false operand in a where, the clause order is only a cost order.

Measured saving: no-hidden-global-mutation 44.7 s -> 6.5 s; the root gate's check 106.1 s -> 66.7 s in-process (median of 3), 37%. Equivalence checked on a scratch copy with one planted violation of each of the four shapes (a write to a module-level dict, ITEMS.append, os.planted_value = v, global COUNTER; COUNTER = 1): the same four findings, word for word, before and after.

This is a pypeeker change (the repository is pinned in the root dev dependencies, so it is made upstream, then the pin is bumped here as TASK-0102 did). The clause order is a fork the pypeeker docs call normative ("written order"); that is the authors' call, so the upstream fix may instead share the base across parts through the corpus memo. Either way one pass over the references should replace three.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pypeeker (upstream) evaluates no-hidden-global-mutation's selecting clauses before the shared in-a-function and allow clauses, or shares that base across the rule's parts, and the root pin names the merged commit, uv.lock regenerated with uv
- [ ] #2 The root gate's no-hidden-global-mutation takes under 10 s on a warm run (44.7 s before, in-process timing, median of 3), recorded in the notes, and its findings on a planted violation of each of the rule's four shapes are the same as before
<!-- AC:END -->
