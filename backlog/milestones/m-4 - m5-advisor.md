---
id: m-4
title: "M5 Advisor"
---

## Description

A stronger model the working model can consult mid-task, as Claude Code's advisor does, and evidence that it helps: more tasks finished for what they cost, not just a tool that answers.

## What Claude Code does

Read from the CLI bundled with claude-agent-sdk 0.2.159 (2.1.281, one patch above the pin) and the docs (code.claude.com/docs/en/advisor, platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool):
- a server-side tool, `{"type": "advisor_20260301", "name": "advisor", "model": ...}` under the beta `advisor-tool-2026-03-01`; it takes no parameters, the API forwards the whole conversation to the advisor model, and the working model decides when to call;
- the answer is in the same assistant message: `server_tool_use`, then `advisor_tool_result` (`advisor_result` text; `advisor_redacted_result` encrypted, which current 5.x advisors return per the docs; or `advisor_tool_result_error` with a code, and the step carries on without advice);
- nothing streams while it advises, only pings;
- its tokens are `advisor_message` entries in `usage.iterations`, billed at the advisor's rate and outside the top-level totals;
- the advisor must rank at or above the main model, and stays fixed for a conversation until /clear or /compact;
- a `# Advisor Tool` system section says when to call: before substantive work, before declaring done (save the result first), when stuck, before changing approach, and once more to reconcile advice with evidence.

## Two routes

A, first: turn on Claude Code's own advisor in the claude-code provider (`--advisor` through `ClaudeAgentOptions.extra_args`). It is what Claude Code does, with Anthropic's advisor prompt. The work:
- an `advisor` setting and `/advisor [NAME|off]` beside `/model`, with a pairing check;
- an event when advice starts and ends (`stream.py` folds only text, thinking and tool_use);
- advisor usage and cost (`Step._count` reads only the top-level counts);
- `pause_turn`, which the provider would interrupt;
- stripping advisor blocks when rebuilding into a process without the advisor (`records.py`);
- a `system` section, if the CLI adds none of its own under bh-02's prompt.

B, if openai models should be advised or advice must be readable: a provider-agnostic `advisor` tool plugin that registers `advisor` and a `system` section, and asks a second model one step over `transcript.messages`, as `/compact`'s `summarise` does. It needs a model row bound under its own key (`models:model` binds `model` only), an approval decision (a `runs="host"` tool is asked about on every call), and an advisor prompt of our own.

## Measure first

- whether the advisor attaches under bh-02's isolated `CLAUDE_CONFIG_DIR` and scrubbed environment (a feature flag gates it; the CLI's debug log says `[AdvisorTool] Server-side tool enabled` or `Skipping advisor`);
- whether the CLI adds its advisor section under a custom system prompt;
- whether an advisor step ends in `pause_turn`;
- whether switching it on or off, which restarts the process, keeps the cache;
- that it works on the subscription (advisor tokens count against plan limits; a Fable advisor bills to usage credits).

## Proof

- It works: pure tests over recorded advisor streams, usage, stops and rebuilds; `FakeClaudeCode` emitting advisor blocks; a real-launch test showing advice in the TUI; an opt-in e2e on sonnet with an opus advisor, including a rebuild with advisor blocks in its history.
- It works well: an eval harness, which bh-02 does not have yet. 30-50 tasks, each with a programmatic check (closed backlog tasks replayed at their parent commit are one source), driven headless by a `--patch` layer that replaces `ui` with a scripted one. Arms: sonnet, sonnet with an opus advisor, opus. 3-5 runs per task per arm, compared task by task, on pass rate, cost (main model and advisor), turns, and advisor calls and their timing. The reported effects are small (about +7 points for Haiku, flat for Sonnet on mixed work, per the docs, not rechecked), so one run per task cannot tell.
- After it ships: advisor signals in `scripts/model-friction`.
