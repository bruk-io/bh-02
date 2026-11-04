---
id: TASK-0183
title: On darwin runner:confined reports itself jailed until the first input fails
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - runner
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: BrigJail.report() returns PLANNED on every platform and the darwin refusal (and the missing-bwrap check) happens only at start, so before an input approval.confined is true, the status bar says jailed and the model is told its inputs are confined. Nothing escapes; what the person sees is wrong. Proposed: refuse in the confined component when the platform has no jail type or bwrap is missing (said before a row starts), or report UNENFORCED off Linux.
<!-- SECTION:DESCRIPTION:END -->
