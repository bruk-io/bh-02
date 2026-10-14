---
id: TASK-0092
title: >-
  Make bh-02's plugin contracts and composition easier to trust and learn as the
  family grows
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-14 03:13'
labels:
  - docs
  - cordis
dependencies: []
priority: low
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
A review of bh-02's plugin design (2026-10-14, by a small local model, Qwen 27B, relayed by the owner) found the core sound but three things that will hurt as the plugin family grows past ten:
- The contracts live in prose. CONTRACTS.md (215 lines) must change in lockstep with the code, and nothing checks it: which row binds a key and who reads it is checkable but unchecked, and the semantic promises (a restart a command asks for never runs in the chat row's task) are doc-only unless a test happens to cover them.
- The dependency graph is visible only at runtime. Wires are parameter names, so what reloads when X restarts is a reading exercise across the layer file, explain and --trace; there is no one static place to see it.
- The docs are reference-grade but hard to learn from: dense, nested prose with no path in for a newcomer.
(Its fourth point, cordis being young: no policy seam, no sys.modules eviction on reload, no draining in-flight calls, is already listed in libs/cordis/README.md in order of value.)

## Outcome
A drift between CONTRACTS.md and the code fails a check instead of the doc quietly lying; anyone can see the composition's graph and what a restart reloads without running bh-02; and a newcomer has one plain walkthrough into the references.

## Must not break
- One consumer's Protocol per key: contracts are not centralised into shared types (two consumers may hold one provider to two contracts).
- plugin-layering: no plugin imports another.
- The references keep their precision; the walkthrough links into them rather than replacing them.

## Open questions
- [ ] The contract check: parse CONTRACTS.md's table, or generate its bound-by and read-by columns from provides= and the layer's parameter names?
- [ ] The graph: a bh-02 graph command, a generated LikeC4 view (the owner's choice for architecture diagrams), or both?
- [ ] The semantic promises: link each one in CONTRACTS.md to the test that proves it, and file a task for each with none?
- [ ] Who writes the walkthrough's voice: the owner reviews it either way.

Candidate tasks, not yet filed (orchestrator's sizes): a check that CONTRACTS.md's bound-by and read-by columns match the code (2); a static graph of rows, keys and what each restart reloads (2); a 'build your first bh-02 plugin' walkthrough (2). Deferred by the owner, 2026-10-14: work on it another time.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A test fails when CONTRACTS.md's bound-by or read-by column disagrees with the code
- [ ] #2 The composition's graph (each row's reads and binds, and what a restart reloads) can be seen without running bh-02
- [ ] #3 Each semantic promise in CONTRACTS.md names the test that proves it, or a task to write one
- [ ] #4 A plain walkthrough takes a newcomer from nothing to a working plugin, linking into the references
<!-- AC:END -->
