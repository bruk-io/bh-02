---
id: TASK-0212
title: Make bh-02/app/tests/test_arch_check.py pass in the Linux container
status: To Do
assignee: []
created_date: '2026-11-07 22:31'
updated_date: '2026-11-08 18:10'
labels:
  - app
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Run in the scripts/linux-jail-check container, serially, as the unprivileged user under tini, 25 of its 40 tests fail: the output that scripts/arch-check prints is empty where a pypeeker report or an index line is expected, and exits are 1 where 0 is expected. On the Mac they pass. The test loads only scripts/arch-check and the standard library. Seen while doing TASK-0079.31, whose diff it cannot reach.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Why the 25 fail in the container is found and said in the notes
- [ ] #2 The file passes in scripts/linux-jail-check run on it alone, or skips there by name saying why
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause: pypeeker segfaults (exit 139) in the container, in tree_sitter's own binding at Parser.parse, seen with PYTHONFAULTHANDLER and a five-line script with no pypeeker in it. tree-sitter 0.25.2 has no 3.15 wheel, so uv sync compiles it, and at the interpreter's -O3 under gcc 13 on aarch64 it crashes. Parsing works rebuilt at -O0, at -O2 -fno-strict-aliasing, at plain -O2 through the script, and on 0.26.0, which pypeeker caps out (tree-sitter<0.26). Which optimisation or which undefined behaviour is at fault was not found. Fix: ENV CFLAGS=-O2 in the image (scripts/linux-jail-check USER_STEPS). Evidence: scripts/linux-jail-check -- bh-02/app/tests/test_arch_check.py: 40 passed, exit 0; before, 25 failed, 15 passed. Any other Linux host building 0.25.2 with gcc at -O3 may hit the same crash; the lasting fix is pypeeker's cap, filed as a follow-up.
<!-- SECTION:NOTES:END -->
