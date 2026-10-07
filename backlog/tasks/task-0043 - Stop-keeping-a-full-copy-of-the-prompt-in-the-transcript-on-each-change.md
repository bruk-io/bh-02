---
id: TASK-0043
title: Stop keeping a full copy of the prompt in the transcript on each change
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 13:18'
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
- [x] #1 A changed prompt is recorded without storing a full copy per change, and the next change is still detected against what the model was last told
- [x] #2 Requests still begin with the prompt the conversation began with, and changes are still told as notes
- [x] #3 An existing transcript with full copies still loads and resumes
- [x] #4 Tests cover a conversation with several prompt changes and a resume
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A prompt change is kept as paragraph edits from the reading before it (prompt.edits), not a whole copy; the loop replays them (prompt.latest) and caches what it last told. Requests still send only the first, whole entry, and changes are still told as notes. A transcript that kept whole copies resumes unchanged; an edits entry that can't be applied is passed over. Nine changes to a 21.5k-character prompt took 197 KB as whole copies and 0.9 KB as edits. Tests: several changes and a resume, an old-format resume, a hypothesis round trip, and the shipped app switching branches across a resume.
<!-- SECTION:FINAL_SUMMARY:END -->
