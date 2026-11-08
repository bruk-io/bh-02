---
id: TASK-0213
title: Lift pypeeker's tree-sitter cap so the workspace can use 0.26
status: To Do
assignee: []
created_date: '2026-11-08 18:10'
labels:
  - pypeeker
  - size-2
dependencies: []
type: chore
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pypeeker requires tree-sitter<0.26. tree-sitter 0.25.2 has no 3.15 wheel, and compiled at -O3 by gcc 13 on aarch64 it segfaults in Parser.parse; TASK-0212 works round that in the scripts/linux-jail-check image only, with CFLAGS=-O2. A person running scripts/arch-check on such a Linux host still gets the crash. 0.26.0 parsed correctly at the default flags in the container.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pypeeker's pin in the root dev dependencies permits tree-sitter 0.26 and uv.lock resolves to it
- [ ] #2 The CFLAGS line and its comment are gone from scripts/linux-jail-check, and test_arch_check.py passes in it
<!-- AC:END -->
