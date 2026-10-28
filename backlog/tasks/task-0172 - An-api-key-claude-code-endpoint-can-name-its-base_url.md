---
id: TASK-0172
title: An api-key claude-code endpoint can name its base_url
status: To Do
assignee: []
created_date: '2026-10-28T23:29:00Z'
labels: []
dependencies:
  - TASK-0171
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A claude-code endpoint with auth = "api-key" always reaches Anthropic's default API URL, and base_url on it is refused (base_url means a gateway, whose key is an apiKeyHelper command the CLI runs). The person has API credit and wants an api-key endpoint that names its API URL explicitly (https://api.anthropic.com, or another Anthropic-compatible one), with the key read as for any api-key endpoint (env, cmd or op). The subscription token stays Anthropic's alone: base_url with auth = "subscription" is refused, so the token is never sent to a URL a file names. Follows TASK-0171.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A claude-code endpoint with auth = "api-key", a base_url and a key of env, cmd or op is accepted, and the CLI is started with ANTHROPIC_BASE_URL set to it in bh-02's settings layer and the key as ANTHROPIC_API_KEY in its explicit environment alone
- [ ] #2 experimental_betas is accepted on such an endpoint and sets CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS
- [ ] #3 base_url with auth = "subscription" is refused with a message saying what to write; a gateway (base_url, no auth) behaves as before
- [ ] #4 docs/bh-02/using/models.md and the models plugin README describe the form; scripts/check passes
<!-- AC:END -->
