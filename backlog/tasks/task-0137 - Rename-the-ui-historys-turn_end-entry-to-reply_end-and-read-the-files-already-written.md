---
id: TASK-0137
title: >-
  Rename the ui history's turn_end entry to reply_end, and read the files
  already written
status: To Do
assignee: []
created_date: '2026-10-18 04:15'
updated_date: '2026-10-18 13:06'
labels:
  - tui
  - naming
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-0009 retires "turn" (TASK-0136.02 renamed every use that was not a stored value). The ui's history file (events.jsonl, one JSON object a line) still writes {"type": "turn_end"} to mark a reply's stream ending (tui history.py, frame.py total_usage, widgets/transcript.py replay, app.py on_reply_ended), and every session already on disk carries that tag. Renaming it changes how a resumed session replays (a missing end closes no block and leaves a partial usage uncounted), so it was left out of a prose-and-names task. Decide whether old files are read (the rule in bh-02/CLAUDE.md: a rename is clean, nothing translates it) or translated, then rename the tag and say which in the notes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The ui writes {"type": "reply_end"} where it wrote turn_end, and history.py, frame.py, the transcript widget, tui README and the tests use it
- [ ] #2 A history file written before this change either resumes as it did (the tag read as reply_end) or the task's notes record the owner's choice not to read it, with a test of whichever holds
- [ ] #3 No match of turn_end remains under bh-02/ except where the notes say why
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner, 2026-10-18: no backwards compatibility. History files written before the rename are neither read for turn_end nor translated (criterion #2's second option); the rename is clean, as bh-02/CLAUDE.md's naming rule says.
<!-- SECTION:NOTES:END -->
