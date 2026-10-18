---
id: TASK-0136
title: >-
  See what happened in a session, step by step, with its timing, as DeepSeek's
  trajectory view shows it
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-14 03:42'
updated_date: '2026-10-18 07:47'
labels:
  - tui
  - agent
  - size-8
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
priority: medium
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
After a reply I can't see what happened inside it: what the model was sent, how long each model step and tool call took (time to first token, generation, throughput), which calls were asked and which ran unasked and how long I took to answer, what changed in the context (the prompt, the tool list, asides, the date), and how sub-agents sat inside their parent. DeepSeek's harness shows this as a trajectory: a timeline of input, model and tool lanes, a list of steps, and a detail pane with a summary, a preview and the raw request. Today bh-02 keeps the conversation (transcript.jsonl, no timing), what the ui showed (events.jsonl, usage but no timestamps), each sub-agent's events (agents/NAME/events.jsonl, timestamped), and row lifecycle under --trace; nothing joins them or records timing.

## Outcome
A session's trajectory, recorded as it happens: its model steps, tool calls, approvals, context changes, sub-agents and row reloads, each with its timing and tokens, that I can browse while a reply runs and after the session has ended.

## Must not break
- Nothing blocks the event loop the TUI shares: recording writes off it.
- Recording never changes what the model is sent.
- Trajectories live where the jail can neither read nor forge them (under host.secrets, 0600), and never hold the credential.
- tui:ui keeps depending on nothing; rows contribute data, the TUI owns how it looks (decision-0003's split).

## Open questions
- [x] Where the record lives: timing, answers, usage and sub-agent links on the transcript's own entries, plus rows.jsonl for row reloads (decision-0009).
- [x] Whether raw requests are recorded: never stored; rebuilt from the transcript and the recorded settings, shown once the projection functions move to a shared library (decision-0009).
- [x] How it is shown: a read-only command first, bh-02 trajectory [ID] with --follow (decision-0009).
- [ ] Carried forward: whether the TUI grows a general place rows contribute views to, or only a trajectory screen; the TUI screen comes after the command, once the projection functions are in a library.
- [x] Live first, or after the fact first: both from the start; --follow re-reads the files while a reply runs (decision-0009).
- [ ] Carried forward: how long trajectories are kept and their size; they last as long as the session's own files, a few fields more per entry, until sessions are pruned.

Drafted by the orchestrator from the owner's ask and a brainstorm (2026-10-14); corrected and accepted by the owner with decision-0009 (2026-10-18).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every model step, tool call, approval, context change, sub-agent and row reload in a session is recorded with its start, end and tokens, off the event loop, where the jail can't reach it
- [ ] #2 I can browse a session's trajectory (a timeline and the steps, each step's detail) while a reply runs and after the session has ended
- [ ] #3 Must not break: what the model is sent is unchanged; nothing blocks the event loop; tui:ui depends on nothing
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-18, found while designing the trajectory; kept off the board for now at the owner's word:
- A torn last line stops a resume: `FileTranscript` raises on it (`json.loads` on every line, agent plugin `transcript.py`).
- A process that dies mid-call leaves the call unanswered, and a resume sends that call with no result: nothing answers it on open.
- Two bh-02 processes can append to one session (`--resume` while it runs): nothing locks the session directory.
- `FileTranscript.append` writes on the event loop the TUI shares, and the transcript, its backups and the session directory take the umask's mode, not 0600 and 0700. This one breaks this draft's must-not-break, so the trajectory design takes it on as its first slice.

Check `scripts/check` exited 0

(30 earlier lines omitted)
```text
........................................................................ [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
.....................................s.ss....ss.sss.ss..ss...s.s...sss.. [ 48%]
ss.s.s.s.s.ssss.........s............................................... [ 50%]
........................................................................ [ 51%]
.....................................................................sss [ 53%]
ssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss........ [ 55%]
.....................ssssssssssss....................................... [ 57%]
.................................s...................................... [ 59%]
........................................................................ [ 61%]
.............................................sss........................ [ 63%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
................................................................         [100%]
3764 passed, 118 skipped in 216.39s (0:03:36)
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
INFO    -  Documentation built in 5.19 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
