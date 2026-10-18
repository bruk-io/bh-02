---
id: TASK-0154
title: >-
  /compact of a resumed session whose last call a crash left unanswered sends
  that call with no result
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 13:55'
updated_date: '2026-10-18 21:49'
labels:
  - agent
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found doing TASK-0142, which answers a call a crash left unanswered at the loop's next reply (loop.py _unanswered_calls, _LOST). /compact does not go through a reply: conversation.py compact_conversation reads the transcript file itself and asks the model for a summary over asked(messages) = request_for(messages) plus its ask, so a session resumed after a process died mid-call, and compacted before the next message, sends the model a call with no result after it, which a provider rejects or the model answers again. The summary request should have a result for every call, worded and recorded as TASK-0142's answers are (_LOST, a call record of the time alone), without changing the entries already in the file.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A test runs /compact over a transcript cut after a step's calls (one answered, one not) and shows the summary request the model receives has a result for every call, in the calls' order, worded as the loop's _LOST answer
- [x] #2 A test shows /compact over a whole transcript sends the request it sent before, unchanged
- [ ] #3 scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. loop.py: add the pure public lost_answers(messages, at) = the tool entries answering _unanswered_calls(messages) with _LOST and a call record of the time alone (records.call_record(at, None, ...)); the loop's _answer_the_unanswered uses it (one clock reading per reply instead of one per call). 2. conversation.py: asked(messages, keep, *, at) sends request_for over messages plus lost_answers(messages, at), so the summary request has a result for every call; compact_conversation reads the clock (resolved once, shared with summarise) for at; the file is never touched (rewrite writes only the seed). 3. Tests in test_agent_conversation.py: AC1 compact over a cut transcript (one answered, one not): request has a result per call in order, wording is the loop's _LOST, call record time alone, file/bak unchanged; AC2 compact over whole transcripts sends request_for(messages)+ask, with no lost answer; pure lost_answers test. Plant the violation (drop the answers from asked) and see AC1 fail. 4. Docs: README agent plugin compact paragraph, conversation.py module docstring. 5. scripts/check bh-02/plugins/agent-cordis-plugin (once), arch-check --no-fix. Risk: asked signature gains required keyword at, existing test callers updated.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: loop.py gains the pure public lost_answers(messages, at) (the tool entries answering _unanswered_calls(messages) with _LOST and a call record of the time alone, via records.call_record); the loop's _answer_the_unanswered now keeps exactly those (one clock reading per reply, where it read once per call). conversation.py: asked(messages, keep='', *, at) sends request_for(messages + lost_answers(messages, at)) then the ask; compact_conversation resolves its clock once (shared with summarise) and passes at=clock.now(). The file is never touched: rewrite still writes only the seed, the .bak is the old bytes. README (agent plugin) and the module docstring say so. Tests: test_agent_conversation.py test_compact_over_a_transcript_a_crash_cut_asks_with_a_result_for_every_call (AC1: c1 answered, c2 not; roles, ids in calls' order, c1 as in file, c2 worded interrupted: ... bh-02 stopped before this call finished ... it may have partly run, call == {at} of the clock, .bak bytes equal old file, new file is the seed), test_the_answer_compact_sends_for_a_lost_call_is_the_entry_the_loop_keeps_for_it (the loop's reply over the same transcript keeps the entry the request carries), test_compact_over_a_whole_transcript_sends_the_request_it_always_sent (AC2, 5 whole shapes: request[:-1] == request_for(messages), one ask, no interrupted entry); test_agent_unanswered_calls.py: the pure lost_answers and that the loop keeps what it makes. Planted violations seen failing: asked without the answers -> the AC1 test and the loop-equality test fail (2 failed, 5 passed); asked answering every call -> 2 of the 5 AC2 cases fail (every result written, no step after; a call answered, no step after); restored, all pass. Existing asked(...) test callers now pass at=NOW. Ran: uv run pytest of both test files (passed), scripts/check bh-02/plugins/agent-cordis-plugin (format, lint, mypy, 207 passed 1 skipped, gates incl. root and libs, docs: all ok; tokens skipped, no bh-01). Not ticked: #3 scripts/check passes (the full check is the reviewer's). No stored format changes: the request is not stored.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 46%]
.................................................ss.....sssss..ss.ss.... [ 48%]
ss...ss.ss.s..ss..ss..sss.s.........s................................... [ 50%]
........................................................................ [ 52%]
...........s............................................................ [ 54%]
............sssssss.ssssssssssssssssssssssssssssssssssssssssssssssssssss [ 56%]
sssssss....s...................ssssssssssss............................. [ 57%]
........................................................................ [ 59%]
........................................................................ [ 61%]
......................................................sss............... [ 63%]
...s.................................................................... [ 65%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
........................                                                 [100%]
3868 passed, 118 skipped in 205.29s (0:03:25)
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
INFO    -  Documentation built in 4.54 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
