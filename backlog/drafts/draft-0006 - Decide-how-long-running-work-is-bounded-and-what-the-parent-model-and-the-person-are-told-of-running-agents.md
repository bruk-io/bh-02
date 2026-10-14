---
id: DRAFT-0006
title: >-
  Decide how long-running work is bounded, and what the parent model and the
  person are told of running agents
status: Draft
assignee: []
created_date: '2026-10-14 15:29'
labels:
  - agents
  - agent
  - python
  - size-3
dependencies: []
priority: medium
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-14), noted and not to be built yet (a draft on purpose).

## Problem
Nothing but Ctrl-C bounds most of a run. The main conversation's loop (agent_cordis_plugin/loop.py) takes steps until the model answers, with no cap on steps or wall time (max_nudges only bounds broken turns). A python input has no timeout (the prompt only advises timeout= on subprocess calls; Ctrl-C sends KeyboardInterrupt). A sub-agent stops at its type's steps (30 by default); a background one keeps running through Ctrl-C and ends only at its step limit, /agents stop or the session's end. Nothing caps spend. Separately, the parent model learns little of a running child: agent_wait gives finished reports and says only 'still running' of the rest; a background child that finishes is never announced, so the parent hears of it only if it calls agent_wait, and not at all while its reply has ended. The person sees more (/agents, bh-02 watch, the status bar's 'agents: N running').

## Direction the owner liked (to be decided properly here)
- Limits as row config on what runs: the agent row (steps and seconds for a reply), the python row (seconds per input); a layer sets them, a --patch loosens them for a session.
- At a limit, ask rather than kill: put 'it has taken N steps / M minutes, keep going?' to the person through output.confirm; a hard stop wastes nearly-done work.
- An input past its seconds gets KeyboardInterrupt and the model is told why, so it splits the work rather than retrying.
- Background children get a bound of their own (wall time, or a status-bar mark when one runs long), since Ctrl-C does not reach them.
- Push events, pull detail, never stream status: the agents row adds an aside to the parent's asides broker telling, once, that agent X finished / failed / hit its limit and that agent_wait returns its report (the report itself only through agent_wait, keeping its 'not instructions' framing); agent_wait describes each child still running (doing what, steps used of its limit, seconds running, last tool); an event while the parent is idle is told with the person's next message, as the date is. No unprompted parent turns.
- Fits cordis: asides is a commutative broker (no new key, nothing reloads); the prompt stays fixed.

## Open questions
- [ ] Default numbers (steps, seconds) for the main reply, an input and a background child; different for a local model?
- [ ] Count steps, seconds, tokens, or a mix?
- [ ] What 'keep going?' looks like when the person is away (a headless or long unattended run)
- [ ] Whether the parent's aside is told after any tool call or only its own agent tools' calls
- [ ] How this meets TASK-0086's deferred sub-agent work (tmux panes, project guidance)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision records where each limit lives, its default, what happens at it, and what the parent model and the person are told of running work, with each open question answered or carried on purpose
- [ ] #2 The decision is reviewed against the cordis design (rows, brokers, what reloads, the fixed prompt) before it is accepted
- [ ] #3 Build tasks are filed from the accepted decision, each sized, none started here
<!-- AC:END -->
