---
id: TASK-0104
title: >-
  One way to write models: endpoints with their models nested, for openai and
  for Claude Code through a gateway
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-15 20:32'
updated_date: '2026-10-17 01:48'
labels:
  - models
  - size-8
dependencies: []
priority: high
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
On a work machine, Claude Code doesn't use a claude.ai subscription token. It reaches Claude through a company's Anthropic-compatible gateway (`ANTHROPIC_BASE_URL`), with a token that a command fetches and refreshes (`apiKeyHelper`). bh-02's claude-code provider only runs on `CLAUDE_CODE_OAUTH_TOKEN` from `local.env`. It removes every `ANTHROPIC_*` variable and loads no settings, so bh-02 can't be used there.

The models file also has two ways to write a model: a flat one-model table, or an openai endpoint with `discover`. I want one format everywhere. An endpoint is a table that says how to reach a server, and its models sit under it, for both providers:

```toml
default = "work/opus"

[work]
provider = "claude-code"
base_url = "https://<gateway>/anthropic"
key_command = "<command that prints a token>"
experimental_betas = false

[work.models.opus]
id = "claude-opus-5-5"

[local]
provider = "openai"
base_url = "http://127.0.0.1:8888/v1"
key = "LINE_IN_LOCAL_ENV"

[local.models.qwen]
id = "<model id>"
max_tokens = 4096
```

## Affected users and systems
- People with a models file (`~/.config/bh-02/models.toml`) and layers whose model row has `extra`.
- The models plugin: `named.py`, `catalog.py`, the openai provider, and `claude_code/` (provider, credential, detach).
- `/model`, `--model`, and the model name a session stores.
- Docs: the `named.py` docstring, the app README and GLOSSARY.

## Open questions
- [x] Does a token helper given through `--settings` run under the detached CLI, with `setting_sources=[]`? Yes, measured on the gateway (notes). Refresh after `key_ttl_ms` is Claude Code's own and not measured.
- [x] Should openai endpoints also take `key_command`? Yes: the same format everywhere.
- [x] Should the gateway's beta switch be a named setting? Yes: `experimental_betas`.
- [x] A resumed session whose layer names a model the file no longer has (like `qwen38`)? It errors for now.
- [x] Do `[1m]` model ids work through the gateway? They are supported; the build checks them through the gateway.
- [x] Does the Agent SDK pass inline JSON to `--settings`? Yes: `_build_settings_value` passes it through unchanged (no sandbox set).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An endpoint is a top-level table holding `provider` and how to reach the server; its models are `[NAME.models.ALIAS]` tables (or the same data inline), each with an `id` and the provider's per-model settings, named `NAME/ALIAS`, the same for openai and claude-code
- [ ] #2 A flat one-model table in the models file or in `extra` is refused, with an error showing how to rewrite it as an endpoint
- [ ] #3 With `base_url` and `key_command`, a claude-code endpoint runs the Claude Code CLI against that gateway with the command as its token helper; bh-02's own process never runs the command or holds the token, and no `CLAUDE_CODE_OAUTH_TOKEN` is needed
- [ ] #4 An openai endpoint may take `key_command` instead of `key`; what it prints is held only in the request headers, kept for `key_ttl_ms` and dropped when the server refuses it, and is never printed, logged or shown in an error
- [ ] #5 A claude-code endpoint without `base_url` runs on the subscription token as today
- [ ] #6 There are no built-in models (owner's call, 2026-10-15): every model comes from an endpoint; with no models file, or no `default` and no `--model`, the model row is unusable and says to add an endpoint and a default, and a new session records no model
- [ ] #7 The Claude Code CLI still loads none of the person's settings, hooks, plugins, MCP servers or CLAUDE.md
- [ ] #8 `key_command` and `discover` are read only from the models file; `extra` otherwise takes the same nested format
- [ ] #9 `NAME/ID` for an id not listed under `models` still resolves, as endpoint names do today; with `discover`, `/model` lists the named models first, then the server's
- [ ] #10 On this machine, a message sent through bh-02 on a gateway model gets a reply, with `[1m]` ids checked too (by hand, with the evidence in the notes)
- [ ] #11 This machine's models file uses the new shape (`qwen38` under an endpoint) and its models work
- [ ] #12 `scripts/check` passes, and the docs describe the one format
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the owner's machine (DRAFT-0008 there, uncommitted), their notes as written:

Done uncommitted on the owner's machine (2026-10-15; the owner asked for no commits).

- Format: `named.py` (every user table an endpoint, `models` table per endpoint, `derived` merges endpoint then model settings, flat tables with `id` refused with a rewrite hint, endpoint names can't be built-ins or hold `/`, `Named.endpoint` replaces `endpoint()` and `shadows`). `catalog.py` lists named models then discovered ones; `endpoints()` only for problems or `discover`.
- key_command: `key_command.py` (`command_key`); openai `headers_for`, headers kept for `key_ttl_ms` (default 300000) and dropped on 401/403; discovery requests are async.
- Gateway: `credential.Gateway`, `gateway_settings` (inline JSON for the SDK's `settings`), `gateway_env` (token variable empty); `ClaudeCodeConfig.gateway`; `failure_of` names the gateway and command.
- Tests: new `test_models_key_command.py`, `test_models_gateway.py`; existing models, app and subagents tests moved to the format.
- Evidence: through the owner's gateway, bh-02's provider got replies on `work/opus`, `work/sonnet`, `work/haiku` and `claude-opus-5-5[1m]`; a `key_command` printing a bad key got the gateway refusal message (after the CLI retried for about 3 minutes). `local/qwen38` answered from the local server. The owner's `~/.config/bh-02/models.toml` is in the new shape.
- `scripts/check`: format, lint, gates, docs ok. Tests: 2775 passed; the failures are environment-bound and touch no models code (subagent tests read `/proc`, which macOS lacks; two python-repl tests see this machine's global Claude rules or jail; the rest pass alone, flaky under load). Types: the bare `mypy` run stops on stray empty plugin directories (agents-, brig-, context-, kernel-cordis-plugin, only `__pycache__`); mypy over the changed packages is clean.
- Built-ins removed (#12): no `BUILT_IN`; no default and no `--model` means no model (`chosen` raises "no model is chosen" with an endpoint to write; status bar `none`); `bh_02.sessions._pinned` records none; a broken or untrusted models file leaves only `extra`. Docs: get-started gains "Your models" (a `claude` endpoint with sonnet/opus/haiku), models guide, README, CONTRACTS, GLOSSARY, plugin READMEs, CLI help. `scripts/check` after: format, lint, gates, docs ok; 2776 passed, the 9 failures environment-bound or flaky alone (as above).

Accepted 2026-10-15 by the owner, who asked for these changes on this branch, made carefully rather than copied, since the codebase may have moved. Their diff is kept at the orchestrator's scratchpad (models-endpoints.diff, 48 files). Measured before porting: 42 of its 44 changed files have exactly the diff's base here; bh-02/CLAUDE.md and GLOSSARY.md differ only by TASK-0099.05's and TASK-0100's edits, and the whole diff applies. Criteria #9 and #10 are about the owner's machine: their notes above are that evidence, and nothing here can repeat it (no gateway, no owner models file).

Owner, 2026-10-17, in conversation: criteria #10 (a gateway reply through bh-02, [1m] ids included) and #11 (their models file in the new shape, its models working) hold on their machine with the merged code: "i can confirm its fine". And no backwards compatibility is needed: an old flat table, an old session's model name or an old layer's `extra` is refused or errors, as the criteria already say, with nothing translated.
<!-- SECTION:NOTES:END -->
