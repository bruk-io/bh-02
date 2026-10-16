---
id: TASK-0126
title: The jail must not let an input write the Python bh-02 itself runs on
status: To Do
assignee: []
created_date: '2026-10-16 22:06'
labels:
  - runner
  - security
  - size-1
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0124's worker (2026-10-16), probing spec_for in bh-02's own venv layout with the project root holding the uv-managed Python (a project opened at the home directory): <sys.base_prefix>/bin/python3 is not in the Spec's write_denies (the base standard library directories are), so an input can write the interpreter bh-02 itself runs on, and the next bh-02 start on the host runs what it wrote, outside any jail. With no venv (prefix == base_prefix) it is denied. bh-02/CLAUDE.md's rule: what the host trusts, the jail keeps from the model (a file the host reads and trusts, or code it imports, is in host and runner:confined denies writing it); the interpreter the host executes is the plainest case of that. TASK-0124 only stopped the supervisor from choosing such an interpreter as the jail's PID 1; this is the host side.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 spec_for denies writing the interpreter bh-02 runs on (sys.executable, <sys.base_prefix>/bin/python3 and each one's resolved target) whenever it lies under a root the jail may write, in a venv layout and without one
- [ ] #2 A test plants the layout (the base interpreter under the project root, in a venv layout) and shows the write denied; seen failing before the fix
- [ ] #3 Shown in a real bwrap jail: an input's write to that interpreter path is refused
<!-- AC:END -->
