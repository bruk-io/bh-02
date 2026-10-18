---
id: TASK-0137
title: >-
  Rename the ui history's turn_end entry to reply_end, and read the files
  already written
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 04:15'
updated_date: '2026-10-18 13:09'
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
- [x] #1 The ui writes {"type": "reply_end"} where it wrote turn_end, and history.py, frame.py, the transcript widget, tui README and the tests use it
- [x] #2 A history file written before this change either resumes as it did (the tag read as reply_end) or the task's notes record the owner's choice not to read it, with a test of whichever holds
- [x] #3 No match of turn_end remains under bh-02/ except where the notes say why
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Rename the tag in the writer (app.py on_reply_ended), the readers (frame.total_usage, chat_view replay), history.py's doc, the tui README and the tests, by sed over the six files. The owner chose no backwards compatibility, so no reader of the old tag and no translation (criterion 2, second option). Proof: a test that writes a file through the app now and resumes it (separate replies stay separate blocks, a stopped reply counts as uncounted), seen failing with the writer, the replay reader and total_usage each planted wrong; git grep for the old tag under bh-02 finds nothing; scripts/check for the tui member.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner, 2026-10-18: no backwards compatibility. History files written before the rename are neither read for turn_end nor translated (criterion #2's second option); the rename is clean, as bh-02/CLAUDE.md's naming rule says.

Done. Renamed the stored tag to reply_end in: tui app.py (on_reply_ended writes it), frame.py (total_usage counts a reply ended with partial usage), widgets/chat_view.py (replay closes the block), history.py (module doc; the sentence saying the tag kept its first name is gone), the tui README, and tests test_chat_view.py, test_frame.py, test_history.py.

Criterion 2, owner's choice (2026-10-18, above): no backwards compatibility. A history file written before this change is neither read for the old tag nor translated, so a resumed old session loses its reply boundaries (text of consecutive replies joins into one block, a stopped reply's partial usage is left uncounted). The test for what holds: new test_chat_view.py::test_a_reply_end_written_now_closes_its_reply_and_counts_its_usage_when_resumed writes a file through BhApp now (text, ReplyEnded, text with partial usage, ReplyEnded), reads it back (types text, reply_end, text, usage, reply_end; frame.total_usage uncounted == 1) and resumes it in a second app (blocks one and two, not onetwo). No test feeds an old-tag file: a test line naming the old tag would be the one match criterion 3 forbids, and the owner's rule is that nothing reads it.

Seen failing (planted, then restored): app.py writing the old tag made test_chat_view's three history tests fail (first at the kinds list: turn_end != reply_end); chat_view replay case renamed so it matches nothing made the new test fail with ['onetwo'] != ['one', 'two']; frame.total_usage case renamed likewise made the new test and test_frame.py::test_a_reply_stopped_before_its_output_was_counted_makes_the_totals_lower_bounds fail (uncounted 0 != 1).

Criterion 3: git grep -n turn_end -- bh-02 docs libs examples scripts finds nothing (exit 1); only stale untracked .pyc files from the old transcript.py name hold it. Remaining mentions are in backlog/ (task-0089.10, task-0136.02, this task) as history, outside bh-02/.

Checks: scripts/check bh-02/plugins/tui-cordis-plugin exit 0 (346 passed, mypy, ruff, gates, docs ok; tokens skipped: no bh-01 dist). Whole-repo scripts/check is the reviewer's.
<!-- SECTION:NOTES:END -->
