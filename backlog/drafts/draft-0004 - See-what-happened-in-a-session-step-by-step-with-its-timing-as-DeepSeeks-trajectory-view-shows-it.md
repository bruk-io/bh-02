---
id: DRAFT-0004
title: >-
  See what happened in a session, step by step, with its timing, as DeepSeek's
  trajectory view shows it
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-14 03:42'
updated_date: '2026-10-18 02:01'
labels:
  - tui
  - agent
dependencies: []
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
- [ ] Where the record lives: timing and approvals added to the transcript's entries; a trajectory plugin with a recorder broker the loop, providers, approval and the agents row report spans to (generalising the sub-agents' event log); or derived after the fact from what is already kept.
- [ ] Whether raw requests are recorded, opt-in, and how they are bounded.
- [ ] How it is shown, and in what order: a read-only viewer command (bh-02 trajectory SESSION, as bh-02 watch), a trajectory screen inside the TUI beside the chat, an HTML export, or one data shape with more than one renderer.
- [ ] Whether the TUI grows a general place rows contribute views to (data, never widgets), or only a trajectory screen.
- [ ] Live first, or after the fact first.
- [ ] How long trajectories are kept, and their size.

Drafted by the orchestrator from the owner's ask and a brainstorm (2026-10-14); the owner corrects it before anyone accepts it. No spec yet: the open questions come first, likely as a design task.
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
<!-- SECTION:NOTES:END -->
