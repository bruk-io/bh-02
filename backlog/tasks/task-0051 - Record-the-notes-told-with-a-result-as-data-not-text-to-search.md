---
id: TASK-0051
title: 'Record the notes told with a result as data, not text to search'
status: Done
assignee: []
created_date: '2026-10-07 13:47'
updated_date: '2026-10-09 03:05'
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
- [x] #1 The loop records the notes it told with a result as a structured field on the tool entry (for example notes: [...]), and the memory rows read that field rather than searching text
- [x] #2 A transcript from before the field still resumes, read as today's text search reads it
- [x] #3 Tests cover a note that sorts after another row's and a trimmed guidance file across a resume
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ported from 899874f (ccr-934e6775-vdsnnr) in c3185c7, onto the memory plugin that replaced context. The loop keeps the notes it told with each result as a list on the tool entry (`notes`), beside the text the model reads, which is unchanged. memory:on_touch reads that list after a resume (`_holds`: a text told whole at a note's start or after a blank line, ending where the note does, where it was cut, or where the next of its texts begins); an entry from before the field falls back to the old text search. scripts/model-friction reads `notes` too. Shell hints were removed before the port, so only memory reads the field. One judgement remains: where one text ends inside on-touch's own joined note is found by its own headers, so a text followed by a custom notes function's may be told twice after a resume, never skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
