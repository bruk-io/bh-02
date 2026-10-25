---
id: DRAFT-0011
title: >-
  Claude is reached two ways: through Claude Code on a subscription token, or
  straight through the Anthropic API on an API key
status: Draft
assignee: []
created_date: '2026-10-25 17:52'
updated_date: '2026-10-25 17:53'
labels: []
dependencies:
  - DRAFT-0010
priority: medium
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

bh-02 reaches Claude only through the Claude Code CLI (the `claude-code` provider), on a subscription token or a company gateway. A person with an Anthropic API key and no subscription, or who wants a call that does not go through the CLI, has no route.

## Affected users and systems

- The person who writes `~/.config/bh-02/models.toml` and picks a model with `--model` or `/model`.
- The models plugin: a second Claude provider beside `claude-code`, with its endpoint tables, discovery of its models, errors and docs.

## Decisions already made (with the person, 2026-10-25)

- Two providers for Claude: `claude-code` (as today, taking `CLAUDE_CODE_OAUTH_TOKEN`) and a new `anthropic-api` provider that takes an Anthropic API key.
- Both take their credential through the `key` object from DRAFT-0010 (`env`, `cmd` or `op`), written in the provider's own endpoint table in `models.toml`. Neither goes in the runner's `env` allow-list: that list is what the jail lets through to the model's code, and these credentials must never be on it.
- This work starts after DRAFT-0010, which retires `local.env`.

## Open questions

- [ ] Does `anthropic-api` run the agent loop itself (Messages API, tool use, streaming) or wrap the SDK? What does it share with the openai provider?
- [ ] Does it take a `base_url`, for a proxy or a gateway that speaks Anthropic's API?
- [ ] Does it discover its models (`GET /v1/models`) as the openai provider does with `discover = true`?
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An endpoint with `provider = "anthropic-api"` and `key = { env = "ANTHROPIC_API_KEY" }` (or `cmd`, `op`) answers a message through Anthropic's API, with no Claude Code CLI started and no subscription token needed.
- [ ] #2 An `anthropic-api` model name works in `--model`, `/model` and the models file's `default` the same way a `claude-code` or `openai` one does.
- [ ] #3 The API key reaches only the request to the provider: not the Python worker's or the jail's environment, not a log, a transcript or an error message.
- [ ] #4 A missing or refused key is a message that names the endpoint and what to write in its `key`, and `/model` with another name gets the person going again.
- [ ] #5 A `claude-code` endpoint without a `base_url` is unchanged from DRAFT-0010: its token comes from `key` and goes only to the CLI.
- [ ] #6 docs/bh-02/using/models.md, the models plugin README and GLOSSARY.md describe both Claude providers and when to pick each, and scripts/check passes.
<!-- AC:END -->
