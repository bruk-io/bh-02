---
id: task-0027
title: A tool call whose arguments never finished streaming is not shown
status: Done
assignee: []
created_date: '2026-09-30 01:36'
updated_date: '2026-09-30 02:03'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0021. When Claude Code drops a connection mid-stream it closes the open block with content_block_stop before retrying, so a half-streamed tool call reaches the TUI with broken arguments just before the step fails. Nothing runs, but the person sees a call that was never made.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When Claude Code closes a stream it will retry (message_stop with no stop reason) while a tool call's arguments are incomplete, that call is neither shown nor recorded; a test with the fake Claude Code covers it
- [x] #2 A call whose arguments genuinely didn't decode in a finished step (a stop reason arrived) is still shown and classified as today; the loop's existing undecodable-call tests pass unchanged
- [x] #3 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commits f3fa23c, 9a38d80 (merged into leftovers). Step (claude_code/stream.py, still pure) emits a call whose arguments decode at its block close, as before. A call that doesn't decode (or has no arguments yet, since '' decodes to {}) is held, along with everything after it so stream order is kept, and released only when message_delta brings a stop reason. The loop then sees it with its error before stop, exactly as today. On a retry close (message_stop with no stop reason) the provider drops the Step and the held call with it. A held call was never shown, so a retry whose only streamed content was that call carries on to the retried stream. After shown text the step still fails with the restarted error, now without the broken call before it. Tests, red first: test_a_call_cut_off_by_a_stream_claude_code_retries_is_never_shown (cut before any arguments and halfway through them), test_a_call_cut_off_by_a_retried_stream_after_text_is_not_shown_before_the_error, two Step-level tests in test_claude_code_stream.py. test_a_finished_step_whose_call_did_not_decode_shows_it_with_its_error pins today's behaviour (it passed before the fix, on purpose). agent-cordis-plugin is untouched and its undecodable-call tests pass. scripts/check after the merge: 1794 passed, 14 skipped, all green. Covered by the fake only: a dropped connection can't be forced against the real CLI.
<!-- SECTION:NOTES:END -->
