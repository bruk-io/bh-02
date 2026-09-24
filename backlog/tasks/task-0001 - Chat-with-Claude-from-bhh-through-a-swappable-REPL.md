---
id: task-0001
title: Chat with Claude from bhh through a swappable REPL
status: Done
assignee: []
created_date: '2026-09-15 18:26'
updated_date: '2026-09-15 18:50'
labels:
  - bhh
  - cordis
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Give bhh a very simple way to talk to Claude interactively: a REPL where you type a message and Claude's reply streams back, with the conversation remembered across turns.

It authenticates through the user's existing Claude Code subscription login (Claude Agent SDK), never an ANTHROPIC_API_KEY.

The presentation layer must be separable from everything else so the REPL can later be removed and replaced by a different interface without touching the conversation or backend code. The whole thing is built on cordis: the Claude backend, the conversation, and the presentation layer are cordis components/providers, so swapping the interface is a cordis provider swap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Running the bhh REPL lets a user send a message and see Claude's reply appear incrementally as it streams
- [x] #2 A follow-up message in the same REPL session gets a reply that uses the earlier turns as context
- [x] #3 No ANTHROPIC_API_KEY is read, required, or set; auth uses the existing Claude Code login
- [x] #4 Replacing the REPL with another presenter at runtime continues the same session without changing conversation or backend code, verified by a test using a scripted presenter
- [x] #5 The conversation and backend are testable with no network and no Claude login (scripted backend and scripted presenter)
- [x] #6 An authentication, billing or rate-limit failure shows a readable message in the REPL instead of a traceback, and the REPL keeps running
- [x] #7 Exiting the REPL (EOF or an exit command) shuts the session down cleanly with no leftover Claude process
- [x] #8 Code outside bhh's presentation module has no knowledge of the terminal (input/print), and the architecture gate enforces that boundary
- [x] #9 Tests, ruff, mypy and scripts/arch-check pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Confirm how to reach Claude without an API key: Claude Agent SDK (bundled Claude Code, inherits the existing claude.ai login); check its option-to-flag mapping and types from the installed source.
2. bhh.chat: Backend (`llm`) and Presenter (`ui`) contracts, ChatError, and run_chat() on a cordis Host; the session loop is a component depending on both keys so a presenter swap restarts it.
3. bhh.claude: `llm` provider on ClaudeSDKClient (tools=[], setting_sources=[], include_partial_messages), mapping stream deltas to text and SDK errors to ChatError, interrupting and draining abandoned replies.
4. bhh.repl: terminal presenter (daemon-thread input) and click entry point; `bhh` script and `python -m bhh`.
5. Export Component from cordis so run_chat is typed against the public API.
6. Tests with scripted backend/presenters and a fake SDK client; a REPL test with scripted input.
7. pypeeker rules confining terminal imports and print/input to bhh.repl, each proven with planted violations.
8. Verify offline (tests, ruff, mypy, arch-check), then a short live session through the user's login.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on branch feat/repl (commit e189907). bhh.chat holds the Backend (`llm`) and Presenter (`ui`) contracts, ChatError and run_chat(); the session loop is a cordis component depending on both keys. bhh.claude is the `llm` provider on ClaudeSDKClient with tools=[] and setting_sources=[] (plain chat), include_partial_messages for streaming, readable ChatErrors for auth/billing/rate-limit/result errors, and interrupt+drain for abandoned replies. bhh.repl is the terminal presenter and click entry point (`uv run bhh`, `python -m bhh`, `--model`).

Verified offline: 12 new tests (scripted backend/presenters, fake SDK client) including a live presenter swap that keeps the conversation (#4, #5); arch-check clean with two custom pypeeker rules (bhh-terminal-in-repl-only, bhh-print-input-in-repl-only), each proven with planted violations (#8); 407 tests, ruff, ruff format, mypy, arch-check all pass (#9).

Still to verify live against Claude Code's login: #1 streaming, #2 multi-turn context, #6 real error text in the terminal, #7 no leftover claude process after exit. #3 pending a check that no code references an API key.

Found while building the gate: pypeeker records builtin calls as symbol_id `<builtins>.print` (binding_name is only set for locals), so a rule matching binding_name is silently inert.

Live smoke test through Claude Code's claude.ai (Max) login, no ANTHROPIC_API_KEY in the environment: `uv run bhh` driven over stdin. Reply 1 ('Count from 1 to 20') streamed in 11 stdout reads from 0.34s to 6.41s (#1); reply 2 ('What was the last number you wrote?') answered '20' (#2); /exit returned 0 with empty stderr and no bundled claude process left running (#7). A code search found no API-key handling in bhh source, tests or config, only the docstring stating it is never used (#3).

#6 is verified offline only (a real auth or rate-limit error was not triggered, since that would mean logging the user out): SDK errors map to ChatError (test_claude_backend.py), and test_repl.py drives the real terminal presenter to show a readable stderr message and carry on.

Closing summary. Commits on feat/repl: e189907 (feature), ef91afc (REPL error test). 409 tests, ruff, ruff format, mypy and arch-check pass; live session verified streaming, context and clean exit.

Decisions: Claude Agent SDK instead of the Anthropic API SDK, because the user authenticates with a Claude Code subscription and must not use an API key. Anthropic's Agent SDK docs describe only API-key and cloud-provider auth and restrict third-party products from offering claude.ai login; the user chose this backend for personal use knowing that. Built-in tools and filesystem settings are off so this is plain chat; `--model` defaults to Claude Code's configured model. Backend and presenter are separate cordis providers, so either can be replaced without touching the other or the session.

Known gaps / follow-ups (not started): a real auth, billing or rate-limit error was never triggered live (#6 is verified offline); when the presenter is swapped mid-reply the in-flight reply is abandoned (interrupted and drained), not handed to the new presenter; cordis's `component` decorator is typed as returning Any, so chat.py builds the session by calling it rather than decorating; possible next steps are wiring bhh's CodeAct Harness to the Claude backend and typed overloads for cordis's `component`.
<!-- SECTION:NOTES:END -->
