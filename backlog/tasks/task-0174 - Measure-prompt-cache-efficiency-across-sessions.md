---
id: TASK-0174
title: Measure prompt-cache efficiency across sessions
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-29T13:34:00Z'
updated_date: '2026-10-29T14:19:00Z'
labels:
  - size-2
  - context
  - scripts
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
We need to see what each change to bh-02 costs in prompt caching: how much of every request is read from the cache, and which changes break it. The data is already recorded: each assistant entry's step record carries usage (input_tokens, which already includes cached and written tokens, cache_read_input_tokens, cache_creation_input_tokens, output_tokens, cost_usd), at, took, model and settings (CONTRACTS.md: step record, usage total). bh-02 trajectory prints cache read and written per step but adds nothing up.

A script beside scripts/model-friction (scripts/cache-efficiency, standard library only, the same session directories and --sessions, --model and --json flags) reports per session and per model:
- hit rate: cache read over input, weighted by tokens;
- write share: cache written over input;
- cache breaks: a step whose cache read falls well short of the previous step's input. Each is sorted by the gap since the previous step ended (at plus took): past the cache lifetime, an expiry; inside it, the prefix changed. An inside break names the transcript entry just before it (a /compact seed, a prompt or tool-list edit entry, a model switch in settings), or none found, which points at the provider (the claude-code provider rebuilding its session);
- cost per step from cost_usd.
Sub-agents' transcripts (agents/NAME/) are reported apart from the parent's.

Before trusting the numbers, check two things in the claude-code provider. Does the Claude Code CLI use the 5-minute or the 1-hour cache? The lifetime is a flag, not an assumption. Can one step make several API calls? If so, say in the report that a break inside a step is not visible.

A baseline taken now lets later changes (TASK-0173's carried lines and per-input namespace line, which go into tool results and the seed, never the system prompt) be checked against it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scripts/cache-efficiency reports hit rate, write share, cache breaks (expiry or inside the lifetime, with the entry before an inside break) and cost per step, per session and per model, with --json
- [x] #2 The cache lifetime is a flag; its default, and whether a step can hold several API calls, are what the claude-code provider was found to do, said in the script's docstring
- [x] #3 Tests over hand-written transcripts: a steady conversation shows no break; a long gap is an expiry; a prompt edit entry or a /compact seed before a short-gap break is named as its cause; sub-agent transcripts are reported apart
- [x] #4 Must not break: it only reads; it never writes into a session directory
- [ ] #5 A baseline over the owner's sessions is recorded in this task's notes (the owner runs it; this container has no sessions)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Read the provider for the two facts (cache lifetime; several requests per step), write scripts/cache-efficiency beside model-friction, test over hand-written session dirs, strict mypy on a copy.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
scripts/cache-efficiency added with bh-02/app/tests/test_cache_efficiency.py (17 tests, pass; with the break test disabled 12 fail, seen). ruff format/check clean; mypy --strict clean on a copy. Facts (in the script docstring): lifetime not settable from code (credential.py _FIXED sets none, detach.py scrubs ANTHROPIC_*/CLAUDE_*; cost uses a 5-min write price), so default --ttl 300; a step can hold several API requests (provider.py:25-31, stream.py:13-17,154-159), so a break inside a step is invisible. A prefix-changing entry is preferred over a run start as the cause; a run start with none is a resume. AC5 (baseline) left for the owner; scripts/check not run.
<!-- SECTION:NOTES:END -->
