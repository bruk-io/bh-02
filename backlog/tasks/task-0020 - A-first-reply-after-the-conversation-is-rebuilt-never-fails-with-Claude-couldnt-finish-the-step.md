---
id: task-0020
title: >-
  A first reply after the conversation is rebuilt never fails with "Claude
  couldn't finish the step"
status: To Do
assignee: []
created_date: '2026-09-28 12:41'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
While measuring task-0018, the first reply after /clear (Claude Code rebuilt from an empty transcript) failed once in 10 runs with: Claude couldn't finish the step. Send the message again. Claude Code ended the query before the reply's stream had finished. The person has to resend a message for no reason of their own, and it may hide a race in how the provider reads a rebuilt session.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause is found: which message order from Claude Code produces the error, shown by a test that reproduces it with the fake Claude Code
- [ ] #2 In that order the reply completes (or, if the SDK truly lost the reply, the provider retries once itself before asking the person to resend)
- [ ] #3 Existing provider tests and scripts/check pass
<!-- AC:END -->
