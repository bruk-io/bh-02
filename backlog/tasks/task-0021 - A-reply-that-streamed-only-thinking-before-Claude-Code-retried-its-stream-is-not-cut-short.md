---
id: task-0021
title: >-
  A reply that streamed only thinking before Claude Code retried its stream is
  not cut short
status: Done
assignee: []
created_date: '2026-09-28 13:16'
updated_date: '2026-09-28 13:29'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing task-0020, by reading Claude Code's CLI (2.1.282): after a stream that showed only thinking, the CLI emits a made-up message_stop and then retries the stream. The provider would read that as a finished step with nothing said, cut it, and drop the real reply that follows, so the person sees an empty or failed turn. Not yet seen live; confirm it and handle it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Whether the CLI emits that order is confirmed from its code or a live log, with the evidence recorded in the notes
- [x] #2 If it does: a test with the fake Claude Code reproduces the order and fails first, and afterwards the reply that follows the retried stream is what the loop receives
- [x] #3 If it does not: the notes say why, and nothing changes
- [x] #4 Existing provider tests and scripts/check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed from Claude Code 2.1.282's (minified) code: three paths close a stream with content_block_stop (if a block is open) plus message_stop, with no message_delta and so no stop reason, then restart the request: the idle/stale timeout after a thinking-only yield, a stream connection error before any block completed, and a mid-stream 529 before content. They are sent as ordinary stream events, so the SDK passes them through. Not seen in a live log (a stall can't be forced). Fix b8c7b06 (merged): a message_stop with no stop reason means Claude Code will retry, so the step starts over on the next stream. Thinking already shown stays; text or a call already shown fails with the existing 'restarted its reply' error. task-0020's whole-message path now folds after streamed thinking too. Tests (all red before the fix), using FakeStep.retry_after: a retry after finished thinking and a retry with thinking still open both complete with the reply and no interrupt; a retry after text raises the restarted error. scripts/check green on leftovers after the merge: 1775 passed, 10 skipped. Short live haiku run streamed normally. Known cosmetic gap: in the connection-error path with a half-streamed tool call, the CLI's closing content_block_stop makes a tool call with broken arguments show briefly before the step fails. Nothing runs.
<!-- SECTION:NOTES:END -->
