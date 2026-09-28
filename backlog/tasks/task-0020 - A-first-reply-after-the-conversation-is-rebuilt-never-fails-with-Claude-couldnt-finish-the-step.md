---
id: task-0020
title: >-
  A first reply after the conversation is rebuilt never fails with "Claude
  couldn't finish the step"
status: Done
assignee: []
created_date: '2026-09-28 12:41'
updated_date: '2026-09-28 13:16'
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
- [x] #1 The cause is found: which message order from Claude Code produces the error, shown by a test that reproduces it with the fake Claude Code
- [x] #2 In that order the reply completes (or, if the SDK truly lost the reply, the provider retries once itself before asking the person to resend)
- [x] #3 Existing provider tests and scripts/check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fix f99eb9e (merged into leftovers). Cause: when a stream fails before a block completes, Claude Code (CLI 2.1.282) asks again without streaming and hands the reply over as one AssistantMessage (new id, stop_reason and usage set, no stream events), then the result. The provider built steps only from stream events, reached the result without a message_stop, and gave the generic error. The one live failure matches: a success result carrying the reply text, with no error and no message_stop. Not reproduced live (0 in 27 runs of the /clear path); the CLI clamps stream timeouts (>=300 s, >=10 s), so the fallback can't be forced. Found by reading the CLI's code. Fix: Step.whole folds such a message as the step (chunks in stream order). If part of it was already shown, the step fails with the existing 'restarted its reply' error instead of saying it twice. The reply was never lost, so there is no retry. Tests (red first) in models-cordis-plugin/tests/test_claude_code_model.py: an answered step after a rebuild with nothing streamed / only the start streamed (both failed with the live error text before the fix); a tool step arriving whole (hung before the fix); partial text then the whole message -> restarted error. FakeStep.fallback_after was added to the fake. scripts/check green (1772 passed, 10 skipped). Open: the SDK drops redacted_thinking blocks from a whole message (matters only on replay/rebuild).
<!-- SECTION:NOTES:END -->
