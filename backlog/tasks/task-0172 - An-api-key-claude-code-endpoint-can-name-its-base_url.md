---
id: TASK-0172
title: An api-key claude-code endpoint can name its base_url
status: In Progress
assignee: []
created_date: '2026-10-28T23:29:00Z'
updated_date: '2026-10-28T23:35:00Z'
labels:
  - size-2
  - models
dependencies:
  - TASK-0171
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A claude-code endpoint with auth = "api-key" always reaches Anthropic's default API URL, and base_url on it is refused (base_url means a gateway, whose key is an apiKeyHelper command the CLI runs). The person has API credit and wants an api-key endpoint that names its API URL explicitly (https://api.anthropic.com, or another Anthropic-compatible one), with the key read as for any api-key endpoint (env, cmd or op). The subscription token stays Anthropic's alone: base_url with auth = "subscription" is refused, so the token is never sent to a URL a file names. Follows TASK-0171.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A claude-code endpoint with auth = "api-key", a base_url and a key of env, cmd or op is accepted, and the CLI is started with ANTHROPIC_BASE_URL set to it in bh-02's settings layer and the key as ANTHROPIC_API_KEY in its explicit environment alone
- [x] #2 experimental_betas is accepted on such an endpoint and sets CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS
- [x] #3 base_url with auth = "subscription" is refused with a message saying what to write; a gateway (base_url, no auth) behaves as before
- [x] #4 docs/bh-02/using/models.md and the models plugin README describe the form; scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on bhabtu/sleepy-tesla-pnb7wl. `named._auth_problem` now owns every claude-code endpoint that says `auth`: `api-key` may take a `base_url` (key from env, cmd or op; experimental_betas allowed with a base_url; ttl_ms still refused), `subscription` with a `base_url` is refused (the token goes to Anthropic alone). An endpoint with a base_url and no auth is a gateway exactly as before. `providers._provided` passes `base_url` and `experimental_betas` to `ClaudeCodeConfig` for an api-key endpoint; the provider gives the CLI `credential.api_settings` (a settings layer with ANTHROPIC_BASE_URL and no apiKeyHelper) and the key as ANTHROPIC_API_KEY through `child_env` as before.

Evidence: `scripts/check bh-02/plugins/models-cordis-plugin`: format, lint, types, tests (406 passed, 2 skipped), gates, docs all ok; tokens skipped (no bh-01 beside the repo). New tests: the validation rows, an api-key endpoint with base_url accepted for each key source, `api_settings`, and the models file through `opened` reaching a fake CLI with the URL in its settings and the key in its env.

NOT verified: the real CLI against https://api.anthropic.com with a real API key (needs the owner's key).
<!-- SECTION:NOTES:END -->
