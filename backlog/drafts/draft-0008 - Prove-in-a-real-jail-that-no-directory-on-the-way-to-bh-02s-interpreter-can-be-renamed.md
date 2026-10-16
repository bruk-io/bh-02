---
id: DRAFT-0008
title: >-
  Prove in a real jail that no directory on the way to bh-02's interpreter can
  be renamed
status: Draft
assignee: []
created_date: '2026-10-16 23:20'
updated_date: '2026-10-16 23:24'
labels:
  - runner
  - security
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0127: rename(2) refuses only a dentry that is itself a mount point, so an ancestor of a held path can be renamed and its mounts move with it. With the project at the home directory, an input that could mv ~/.local/share/uv aside could build its own python3.15 at the old name, and the next uv run on the host would run it.

Measured 2026-10-16 by the orchestrator, in a real bwrap jail with `_a_uv_python_in`'s layout: it is refused today. TASK-0126's interpreter deny and TASK-0127's link-directory denies are write denies, so brig's decision-168 pins bind every existing directory between the project and them over itself: `uv`, `uv/python`, `venv` and `venv/bin` refuse a rename (Device or resource busy), the rest are inside a read-only deny (Read-only file system). With `brig.mech.bwrap`'s `pins` replaced by one that returns nothing, renaming `uv` and `venv` succeeds on the host. So the pins are the one thing holding it, and no runner test says so: a change to the pins, or to which denies the runner hands brig (`uncovered`, `mountable`), could reopen it silently. This adds that test; no code change is expected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 In a real bwrap jail with uv's layout under the project, an input's rename of each directory between the project and the interpreter file or a link on the way to it is refused, and nothing is moved on the host
- [ ] #2 The test is seen failing with brig.mech.bwrap's pins replaced by one that returns nothing (renaming uv and venv then succeeds), and passing without the plant
<!-- AC:END -->
