---
id: TASK-0051
title: 'Record the notes told with a result as data, not text to search'
status: To Do
assignee: []
created_date: '2026-10-07 13:47'
labels:
  - agent
  - context
  - kernel
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
kernel:shell_hints and context:on_touch decide what a resumed conversation was already told by searching the free text of the transcript's tool entries (_told_in, _HINTED, _ENDS), which depends on how the loop joins and sorts notes and on what each note starts with. Another memory row whose note sorts after 'From ', or a guidance file trimmed after a paragraph that starts with '(', makes the search answer wrongly, so a note is told again or wrongly skipped. Found in the code review of PR #8.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The loop records the notes it told with a result as a structured field on the tool entry (for example notes: [...]), and the memory rows read that field rather than searching text
- [ ] #2 A transcript from before the field still resumes, read as today's text search reads it
- [ ] #3 Tests cover a note that sorts after another row's and a trimmed guidance file across a resume
<!-- AC:END -->
