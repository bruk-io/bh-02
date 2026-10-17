---
id: DRAFT-0008
title: >-
  Rebuild brig around its architecture, in the owner's Python dialect, with no
  backwards compatibility
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-17 14:58'
labels:
  - brig
dependencies: []
references:
  - >-
    backlog/decisions/decision-0008 -
    Rebuild-brig-as-a-pure-domain-behind-ports-and-adapters-with-no-backwards-compatibility.md
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
brig works and its grades are honest, but its layout is cut by stage, not by concern: a jail type is spread over four packages, pure security decisions (grading, the kill ladder's choices) sit inside the I/O code, grades are stated and then checked rather than derived from evidence, the supervisor program is written to Python 3.9 outside strict typing, and one role has two names. It is hard to read, hard to extend with a new jail type, and the house idioms and rules don't apply to it.

## Affected users and systems
- bh-02, brig's one embedder: its runner (runner_cordis_plugin) is the only importer and changes once, when the new API lands.
- Whoever reads or extends brig: the owner, workers, reviewers.

## Outcome
A brig whose layout states its architecture: a pure domain behind ports and adapters, one value per jail type, grades derived only from evidence, written in the owner's Python dialect (philosophy:python-idioms) on 3.15 everywhere, and enforced by its gate. The layout and rules are decision-0008.

## Must not break
- brig's ten laws (SPEC section 2), every one.
- bh-02's jail guarantees while the rebuild runs: the live libs/brig keeps jailing bh-02 until the rebuilt one replaces it.
- brig standalone: the standard library and itself only.

## Open questions
- [ ] decision-0008's four open questions (proxy, shipping the batteries, Seatbelt before a Mac run, SPEC numbering).
- [ ] Carried forward: sizing each rebuild step, once decision-0008 is accepted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 decision-0008 is accepted by the owner
- [ ] #2 Each step of decision-0008's order is done, and bh-02's runner runs on the rebuilt brig
- [ ] #3 Every rule in decision-0008 is enforced by the check it names, each seen failing on a planted violation
- [ ] #4 Must not break: the ten laws hold, each grade backed by a battery; bh-02's jail tests and scripts/linux-jail-check pass
<!-- AC:END -->
