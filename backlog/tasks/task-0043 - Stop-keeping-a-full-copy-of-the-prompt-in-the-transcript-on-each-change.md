---
id: TASK-0043
title: Stop keeping a full copy of the prompt in the transcript on each change
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
labels:
  - agent
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop keeps the prompt a conversation began with and records each later reading that differs as another whole `{"role": "system"}` entry. A session where extensions load, branches switch or CLAUDE.md is edited grows its transcript.jsonl by the whole prompt each time. A resumed transcript from before the date moved out of the prompt also keeps an old `Today:` line in its first entry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A changed prompt is recorded without storing a full copy per change, and the next change is still detected against what the model was last told
- [ ] #2 Requests still begin with the prompt the conversation began with, and changes are still told as notes
- [ ] #3 An existing transcript with full copies still loads and resumes
- [ ] #4 Tests cover a conversation with several prompt changes and a resume
<!-- AC:END -->
