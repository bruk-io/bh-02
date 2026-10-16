---
id: TASK-0113
title: >-
  Cut no-hidden-global-mutation from 45 s to 6 s: test each part's own clause
  before the shared base (pypeeker, then bump the pin)
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 08:19'
updated_date: '2026-10-16 13:17'
labels:
  - gates
  - size-2
dependencies: []
modified_files:
  - pyproject.toml
  - uv.lock
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
- [x] #1 pypeeker (upstream) evaluates no-hidden-global-mutation's selecting clauses before the shared in-a-function and allow clauses, or shares that base across the rule's parts, and the root pin names the merged commit, uv.lock regenerated with uv
- [x] #2 The root gate's no-hidden-global-mutation takes under 10 s on a warm run (44.7 s before, in-process timing, median of 3), recorded in the notes, and its findings on a planted violation of each of the rule's four shapes are the same as before
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Read what the pypeeker docs say about clause order (fork #3: written order, no optimizer; dsl/selection.py, expr.py, evidence.py) and choose: each part's selecting clauses first and the shared in-a-function and allow clauses last, not a shared base through the corpus memo. Why: the engine never reorders, so the rule's author writing the cheap clauses first is allowed where every clause is pure (all are), the rows and their meet of confidence are the same (fork #4); the base alone is 14 s here (TASK-0111), so sharing it could never reach under 10 s and the memo would hold every row in flight.
2. pypeeker worktree pp-0113 (from 7905d24, the commit bh-02 pins): in src/pypeeker/dsl/mutation_rules.py replace _global_base(options) by _in_unallowed_function(selection, options), applied last by the three reference parts. In tests/test_dsl_rules_mutation.py: the structural test that pinned the old order now pins the new one; add a table of the four shapes under several allow lists (written against the old code first, so before = after), and a count of fnmatch tests that does not grow with unrelated references (no timing).
3. Measure on bh-02's root corpus in-process, before (7905d24 source via PYTHONPATH) and after interleaved, median of 3, the machine shared; plant the four shapes in a scratch copy of bh-02 and compare findings before and after.
4. scripts/verify-repo.sh once in pypeeker; one commit there and one here (the board). The pin bump and uv.lock are the orchestrator's (criterion 1's last part, left unticked).

### Risks
Tests that pin the old structure or a derivation order (the structural test did, and is updated); a reorder that changes a row (excluded: every clause kept and pure, equal findings shown on planted shapes). no-argument-mutation has the same shape but is outside the criteria: reported, not changed.

### Proof
The new count test and structural test fail on the old order and pass on the new; the findings table passes on both; verify-repo.sh passes; the rule takes under 10 s in-process on the root corpus (median of 3, before and after back to back) with the same four findings on planted shapes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-0113 worker notes (pypeeker commit 7370f98e11271215c90b6d55ba81a026cdbdcc3d on branch wt-0113, from 7905d24; not pushed, the pin and uv.lock are the orchestrator's).

## What changed (pypeeker)
- src/pypeeker/dsl/mutation_rules.py: _global_base(options) (references() + in-a-function + allow, then the part's clauses) is replaced by _in_unallowed_function(selection, options), which the three reference parts (outer-scope write, mutator call, attribute write on an import) apply LAST, after their own selecting clauses. Every clause is kept, the part for the `global x; x = 1` rebind is untouched.
- tests/test_dsl_rules_mutation.py: the structural test that pinned the old order now asserts the three parts close with the two clauses; new: a table of the four shapes under eight allow lists (findings word for word), and a fnmatch-count test that pins the cheaper evaluation without timing.

## Fork chosen, and why
The docs call written order normative (fork #3: dsl/selection.py, dsl/expr.py, dsl/evidence.py: clauses run as written, the engine never reorders; confidence is the meet over every clause, order-independent, fork #4). That binds the engine, not the rule's author: the author may write the cheap clause first where every clause is pure (field reads, fnmatch, opaques over declared reads), and all of them are. Chosen: selecting clauses first, base last. Not chosen: sharing the base through the corpus memo, because the base alone is 14.0 s here (TASK-0111) so it could never reach under 10 s, and the memo would hold every row in flight. The one observable difference is the order of a match's derivations, printed only by `pypeeker query --why` for a named library expression; no selection of this rule is one (grep: Match.derivations is read only in dsl/run.py).

## Evidence
- Time of the rule on bh-02's root corpus (this worktree at 904ed8f, 224 src files in the root gate), in-process (scratch driver: ensure_fresh and the corpus index load outside the timer, then dsl_rule(...).findings over one Corpus), three interleaved rounds before/after, each its own process under tini, before = pypeeker 7905d24 source via PYTHONPATH, after = 7370f98: before 42.05, 43.59, 44.89 s (median 43.59); after 6.24, 6.34, 6.57 s (median 6.34); load average 1.1-1.6 from other workers' processes (the machine was shared). TASK-0111 measured 44.7 s before. Findings: 0 before and after (same digest).
- Equivalence on planted shapes: a scratch copy of this worktree (tar, no .git/.venv) with bh-02/app/src/bh_02/planted_mutation.py holding one violation of each shape (CACHE[key] = value, ITEMS.append(value), os.planted_value = value, global COUNTER; COUNTER = 1), indexed: before 43.82 s, after 6.17 s, the same four findings, word for word (diff of the rendered path:line:rule:message lines empty). Nothing planted is in the repository.
- The new tests seen failing on the old code: with src/pypeeker/dsl/mutation_rules.py put back to 7905d24 (copy aside, restored after), 6 failed: the structural test x3 and the count test x3 (3288 fnmatch tests with 40 modules of unrelated references against 168 without them; with the change both are equal). The 8-row findings table passes on both (it pins equality). pytest tests/test_dsl_rules_mutation.py tests/test_rule_no_hidden_global_mutation.py tests/test_dsl_rules.py: 82 passed.
- pypeeker scripts/verify-repo.sh: pytest 3860 passed, 11 skipped; ruff check src tests passed; self-lint passed (OVERALL: PASS).
- UV_NO_SYNC=1 scripts/arch-check --no-fix here with the new pypeeker installed editable: exit 0, 66.3 s wall (one run, machine shared; TASK-0111 measured 115.6 s on a quieter machine, so this is indicative only, not an interleaved comparison).

## Not done / left
- Criterion 1's last part, "the root pin names the merged commit, uv.lock regenerated", is the orchestrator's: unticked.
- no-argument-mutation (same mutation_rules.py) has the same shape in _argument_base (in-a-function and allow before its kind clauses); none of this repository's gates enable it, so it was not measured and not changed (outside this task's criteria): worth a pypeeker follow-up for consumers that do.

Pin part of criterion 1 (orchestrator, 2026-10-16): the pypeeker change landed as part of brukhabtu/pypeeker PR #148 (CI green), squash-merged as 67b0a1b0121fa48d89c6cecaa82624592bfa8386. The commits reviewed were 04e2249 (TASK-0113), f6ea736 (TASK-0114) and 8fd3239 (TASK-0117) on pypeeker branch ccr-8cdd69a0-gt1lov (the workers' wt-* commits 7370f98, ae3f719 and 184d2ac re-applied without change). bh-02 commit 2bcfefe pins pypeeker@67b0a1b; uv.lock regenerated with `uv lock` (pypeeker 7905d240 -> 67b0a1b0, nothing else).
- After the pin, on a quiet machine: scripts/arch-check --no-fix exit 0 in 56.4, 49.9, 49.8 s (TASK-0111 measured 115.6 s warm before any of TASK-0113..0118).
- Full scripts/check: exit 0 in 208 s; format, lint, types, tests (3186 passed, 31 skipped), gates (all five ok), docs, tokens.

Review: APPROVE. pypeeker 04e2249 reorders clauses, which are pure and joined by AND, so the findings and confidence are unchanged; only the derivation order seen by query --why moves, and no selection of this rule reaches it. Criterion 2 evidence is 43.6 s to 6.3 s with the same four planted findings. Pin checked: 2bcfefe pins pypeeker@67b0a1b; uv.lock names 67b0a1b0121f; .venv direct_url.json has commit 67b0a1b0121f. The full check passed (orchestrator). Nits, not filed: the worker notes name 7370f98 rather than the merged 67b0a1b; no-argument-mutation has the same order cost but no bh-02 gate enables it, so it is a possible pypeeker follow-up.
<!-- SECTION:NOTES:END -->
