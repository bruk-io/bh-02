---
id: TASK-0142
title: A call left unanswered by a crash is answered when the session resumes
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:15'
updated_date: '2026-10-18 13:59'
labels:
  - agent
  - size-3
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found designing TASK-0136 (noted there, filed at the owner's word 2026-10-18). The loop appends a step's assistant entry, with its calls, before it runs them; a stop answers every call (_INTERRUPTED, _NOT_RUN), but a process that dies mid-call answers none. A resumed session then sends the model a call with no result after it, which a provider rejects or the model answers again. The loop's next reply should answer such a call first, as it answers calls a stop interrupts, so the conversation is whole before any request.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Before the first request of a resumed conversation, every call in the transcript with no tool entry after it is answered with an entry saying bh-02 stopped before the call finished and it may have partly run (wording as _INTERRUPTED's), in the calls' order, with a call record (decision-0009) whose fields say no answer or run time was recorded
- [x] #2 A test resumes a transcript cut after a step's calls (one call answered, one not) and shows the request the model receives has a result for every call; another shows a whole transcript is sent unchanged
- [x] #3 The claude-code provider still resumes such a session (its reconcile rebuilds or accepts it; a test) ; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. loop.py: a pure _unanswered_calls(messages) (the last assistant entry's tool_calls with no tool entry for their call_id after it; none when a user entry already follows them, a transcript an older bh-02 resumed unanswered, which cannot be mended by appending) and LoopModel._answered_lost(), called first in _reply (before _offer/_told, so every ending of the reply leaves the conversation whole): one tool entry per call, in the calls' order, content _LOST ('interrupted: bh-02 stopped before this call finished; it may have partly run', _INTERRUPTED's wording), asides [], call record = _Call(clock).record() i.e. at alone. 2. Tests (agent plugin): a transcript cut after a step's calls, one call answered and one not, and one with none answered: the request has a result for every call in order with the record at alone; a whole transcript (answered, no calls, a legacy user-after-calls one) is sent unchanged and gains nothing but the new message; the file transcript flushed holds the answers. Plant: remove the _reply call, see the tests fail, restore. 3. models plugin: reconcile test (a crash-saved state reads FAILED and the resumed transcript with the loop's answer is rebuilt, prefix includes the answer) and a ClaudeCodeModel test over the fake: a second model resumes the first's crashed state, the rebuilt session file holds a tool_result for every tool_use. 4. Docs: CONTRACTS.md (call record, transcript, loop section), GLOSSARY call record, agent README, models README, docs loop.md and sessions.md. 5. scripts/check agent plugin (with gates, docs), models plugin (--no-gates --no-docs), arch-check --no-fix for docs only if outside members (docs are outside members: run it). Risks: /compact right after a resume still sends the unanswered call (it never reaches the loop): file a follow-up task, not done here.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: loop.py gains _LOST ('interrupted: bh-02 stopped before this call finished; it may have partly run', _INTERRUPTED's wording), a pure _unanswered_calls(messages) (the last assistant entry's tool_calls with no tool entry after it; [] when a user entry already follows them, a transcript an older bh-02 resumed unanswered, since an answer appended after the person's message would not make it whole) and LoopModel._answer_the_unanswered(), called first in _reply, so every ending of the reply (stopped, Unstarted, answered) leaves the conversation whole. Each answer is _answer(call, _LOST, [], _Call(clock).record()): a tool entry with asides [] and a call record of at (now) alone, as a _NOT_RUN one has: no answer, waited or took was recorded. CONTRACTS.md (loop section, message call, call record), GLOSSARY, agent and models READMEs, docs loop.md and sessions.md say so. Tests: agent tests/test_agent_unanswered_calls.py (8): a transcript cut after a step's calls with c1 answered and c2 not (request has a result per call, in order, c2 interrupted: with call == {at: resume time}), three unanswered in order, the answers kept in the file once and a second reply adds none, a whole transcript sent unchanged in 4 shapes (nothing added but the message and the answer), an older bh-02's user-after-calls transcript left as it was. Planted: with the _reply call removed 3 of 8 failed (first request lacked the result, the file lacked c2); with the user guard removed the older-transcript test failed; restored, 8 pass. Claude Code provider: models tests/test_claude_code_reconcile.py (a crash-saved OPEN state reads FAILED and the resumed transcript with the loop's answer reconciles to Rebuild(prefix 4, 'carry on'), and to CONTINUE with no line typed) and tests/test_claude_code_model.py (a second ClaudeCodeModel over the first one's crashed state rebuilds the session from the transcript: records user, assistant, user, user, with a tool_result for t1 and t2 in the calls' order; planted: with the lost answer omitted the test failed on the record count). Ran: scripts/check bh-02/plugins/agent-cordis-plugin (exit 0: format, lint, types, 195 passed 1 skipped, gates, docs), scripts/check bh-02/plugins/models-cordis-plugin --no-gates --no-docs (exit 0, 363 passed 2 skipped), scripts/arch-check --no-fix (exit 0), subagents/chat/memory plugin tests (300 passed). AC #3's 'scripts/check passes' is the reviewer's to prove (the full check was not run), so #3 is left unticked though its claude-code part is proven by the tests above. Not done, filed: TASK-0154, /compact right after a resume reads the file itself and sends the unanswered call (it never goes through a reply).

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 33%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 45%]
.....................................................................s.s [ 47%]
s....sss..s.ss..s.ss.s.s...s.s.s.s..s.s.s..ssss.ss.......s.............. [ 49%]
........................................................................ [ 51%]
........................................................................ [ 53%]
...............................sssssssssssssssssssssssssssssssssssssssss [ 55%]
ssss.sssssssssssssssssssss.....s......................sssssssssss....... [ 56%]
.s................................................................s..... [ 58%]
........................................................................ [ 60%]
........................................................................ [ 62%]
....sss................................................................. [ 64%]
........................................................................ [ 66%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
..................................                                       [100%]
3806 passed, 118 skipped in 195.81s (0:03:15)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 3.86 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (not closed): full scripts/check exit 0 (3806 passed, 118 skipped; gates, docs ok), all three ACs met and ticked, no code findings. close-task refused: a bug needs its repro recorded (record-check TASK-0142 --repro -- <test failing before the fix>, e.g. tests/test_agent_unanswered_calls.py at 0af979a) or a 'No repro:' note. The worker's planted-failure note is not a recorded repro; the worker should record one at the pre-fix commit, then this closes.
<!-- SECTION:NOTES:END -->
