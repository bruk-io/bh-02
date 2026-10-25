---
id: DRAFT-0011
title: >-
  A claude-code endpoint can run on an Anthropic API key, not only a
  subscription token
status: Draft
assignee: []
created_date: '2026-10-25 17:52'
updated_date: '2026-10-25 21:44'
labels: []
dependencies:
  - TASK-0169
priority: medium
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

A `claude-code` endpoint without a `base_url` runs on a subscription token (`CLAUDE_CODE_OAUTH_TOKEN`). The person has extra Anthropic API tokens that can only be used through Claude Code (the Agent SDK's CLI child), not by calling the Messages API directly, and bh-02 has no way to give the CLI one. The earlier idea of a separate `anthropic-api` provider that calls the API itself is dropped: those tokens could not be used that way.

## Affected users and systems

- The person who writes `~/.config/bh-02/models.toml` and picks a model with `--model` or `/model`.
- The models plugin's `claude-code` provider: the CLI child's explicit environment (`ChildEnv`), the endpoint's `key` handling, errors and docs.
- The project rule "never set or read `ANTHROPIC_API_KEY`" (root CLAUDE.md, bh-02/CLAUDE.md), which exists to keep a Claude credential out of bh-02's own environment and out of the model's reach.

## What is known (read from claude_agent_sdk 0.2.158, 2026-10-25)

- The SDK has no api-key option. `ClaudeAgentOptions.env` is passed to the CLI child and wins over the inherited environment, and the SDK itself treats `ANTHROPIC_API_KEY` there as env-based auth. So the route is the key in the child's `env`.
- The SDK always merges bh-02's whole environment into the child's, so an `ANTHROPIC_API_KEY` exported in the person's shell would reach the CLI as well (`detach.py` exists for that reason).
- Not verified: how the CLI chooses when both a subscription token and an API key are set.

## Decisions already made (with the person, 2026-10-25)

- The credential goes through the endpoint's `key` object (`env`, `cmd` or `op`), written in `models.toml`, never in the runner's `env` allow-list.
- The key reaches only the CLI child's explicit environment: never bh-02's `os.environ`, the Python worker, a jail, a log or a transcript.

## Open questions

- [ ] What tells a `claude-code` endpoint its `key` is an API key and not a subscription token (a field on the endpoint, or the key's own shape)? Carried forward: a design choice for the person once the CLI's behaviour is known.
- [ ] How does the CLI choose when `ANTHROPIC_API_KEY` and a token are both set, and what must `ChildEnv` blank so only the chosen one is used (as `gateway_env` blanks the token)? Carried forward: a spike answers it against the real CLI.
- [ ] The project rule against `ANTHROPIC_API_KEY`: reword it to "never in bh-02's own environment or any program the runner starts; only in the CLI child's explicit environment"?
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `claude-code` endpoint without a `base_url` whose `key` is an Anthropic API key answers a message through the CLI, with no subscription token set.
- [ ] #2 The API key is in the CLI child's explicit environment only; a test shows it is absent from `os.environ`, the Python worker's environment, the transcript and any error message.
- [ ] #3 With both a token and an API key available, the endpoint uses the one its configuration says, and the other is blanked in the child's environment.
- [ ] #4 A missing or refused key is a message that names the endpoint and what to write in its `key`, and `/model` with another name gets the person going again.
- [ ] #5 The project rule about `ANTHROPIC_API_KEY` is reworded to say where it may and may not appear, and docs/bh-02/using/models.md, the models plugin README and GLOSSARY.md describe the endpoint's API-key form, with scripts/check passing.
<!-- AC:END -->
