---
id: DRAFT-0010
title: Set up brig's docs and architecture model in bh-02's site
status: Draft
assignee: []
created_date: '2026-10-17 17:45'
labels:
  - brig
  - size-2
dependencies:
  - DRAFT-0009
parent_task_id: TASK-0135
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

decision-0008's order, step 2, the docs half: brig's docs live in bh-02's MkDocs site under docs/brig/ (TASK-0135 criteria 12 to 14), replacing the old brig's pages there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docs/brig/ holds an index, a glossary naming each term once (decision-0008 rule 12), and the SPEC's start: brig's ten laws carried verbatim from the old SPEC, section 2, with their amendments folded in
- [ ] #2 A reference page is generated from brig's public API at build time by mkdocstrings and never committed
- [ ] #3 docs/brig/architecture/ is a LikeC4 project in the c4-architecture plugin's layout with a System Context view for brig, embedded in the docs with mkdocs-likec4; likec4 validate and c4lint are clean
- [ ] #4 mkdocs build --strict passes, and just done runs the docs build and the architecture lint
<!-- AC:END -->
