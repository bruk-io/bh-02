---
id: task-0018
title: 'Make /model and /clear answer within a few seconds, or record why they can''t'
status: Done
assignee: []
created_date: '2026-09-28 12:26'
updated_date: '2026-09-28 12:41'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-0014's live run measured 12-15 s for /model and /clear while the Claude Code CLI restarted. That measurement predates strict_mcp_config, which cut the CLI's start-up work. Measure the time now; if it is still slow, bring it down where the cost can be avoided (e.g. switching models without restarting the process).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The time from /model NAME (and /clear) to the next reply being possible is measured against the real Claude Code CLI and recorded in the task notes
- [x] #2 If the measured time is over ~5 s, the avoidable part is removed and re-measured, or the notes say what makes it unavoidable
- [x] #3 Any change keeps the conversation carrying on after /model, and is covered by a test
- [x] #4 The Claude credential is only read from local.env as CLAUDE.md prescribes, never printed or logged
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Measured 2026-09-28 against the real Claude Code CLI 2.1.282 (SDK 0.2.158), haiku<->sonnet, the real bh-02 in a pty with the default jail and --trace; time from Enter on the command to the reply word appearing on screen, next line typed 0.2 s after the command. 5 rounds per command.
- First reply after launch: 2.0-2.5 s. Warm reply: median 0.65 s.
- /model sonnet -> reply: median 2.73 s (11.28 outlier once, 2.59-2.84 otherwise). /model haiku -> reply: median 2.51 s. /clear -> reply: median 2.80 s (2.54-3.37).
- Rows back up: /model ~0.6 s (incl ~0.45 s closing the old CLI), /clear 0.35 s. With fake models the same commands cost 0.24-0.29 s.
- Bare CLI connect with the provider's options: median 0.96 s (0.85-1.40, n=13); disconnect 0.48 s.
Under the 5 s bar, so no code changed (AC3 has nothing to cover). The old 12-15 s most likely came from the account's 118 claude.ai connectors, removed by strict_mcp_config=True; that fits task-0014's notes but wasn't tested. Possible further gain: ClaudeSDKClient.set_model switches a running CLI (verified once, reply in ~1 s), saving ~1.5 s on /model. It would mean keeping the CLI alive across a model-row reload, a cordis design change, so it wasn't built and needs a decision. /clear has no SDK equivalent. Noise: one 11.3 s /model and one 5.8 s post-switch reply, not reproduced. A failed first reply after /clear (1 of 10 runs) is tracked separately. The token was read only by the provider from local.env; never printed or copied.
<!-- SECTION:NOTES:END -->
