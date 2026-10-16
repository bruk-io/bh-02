---
id: TASK-0127
title: >-
  Keep the links on the way to bh-02's interpreter out of an input's reach (uv's
  Python directory under a writable root)
status: To Do
assignee: []
created_date: '2026-10-16 22:27'
labels:
  - runner
  - security
  - size-2
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0126's worker, measured in bwrap. TASK-0126 denies writing the interpreter files bh-02 runs on, but a read-only mount on a file cannot hold the links on the way to it. In bh-02's venv layout with the project root holding uv's Python (a project opened at the home directory), .venv/bin/python leads through uv's ~/.local/share/uv/python/cpython-3.15-<platform> link to the versioned directory; with only the file denied, an input can mv that link away and plant its own tree at its name, and the next `uv run` on the host executes it. Closing it needs a policy decision (the owner's): deny the directories that hold each link on the way to the interpreter when they lie under a writable root (for uv, ~/.local/share/uv/python), or refuse a confined session whose writable roots contain bh-02's own interpreter or installation, or another rule.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The owner's chosen rule is written in the runner README's host section and decided by a pure function beside spec_for
- [ ] #2 In a real bwrap jail, in the layout above, an input can neither replace nor rename any link on the way from sys.executable to the interpreter file, and a test plants it; seen failing before the fix
<!-- AC:END -->
