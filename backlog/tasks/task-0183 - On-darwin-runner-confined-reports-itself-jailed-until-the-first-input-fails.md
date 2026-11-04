---
id: TASK-0183
title: On darwin runner:confined reports itself jailed until the first input fails
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T12:39:00Z'
labels:
  - runner
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: BrigJail.report() returns PLANNED on every platform and the darwin refusal (and the missing-bwrap check) happens only at start, so before an input approval.confined is true, the status bar says jailed and the model is told its inputs are confined. Nothing escapes; what the person sees is wrong. Proposed: refuse in the confined component when the platform has no jail type or bwrap is missing (said before a row starts), or report UNENFORCED off Linux.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Off Linux, or with no bwrap on PATH, runner:confined's report is not confined: approval.confined is false and the status bar never shows jailed, before or after a start; repro test: Approval(Runner(BrigJail(BrigConfig(), Host(), platform='darwin'))).confined is False
- [ ] #2 The person is told before the first input that runner:confined cannot jail here and what to use instead (runner:unconfined, --no-jail)
- [ ] #3 The darwin skip conditions in test_runner_tmux.py and test_runner_allowlist.py say what they now mean
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
