---
id: TASK-0088
title: >-
  Discover the models an OpenAI-compatible endpoint serves, rather than one
  table per model
status: To Do
assignee: []
created_date: '2026-10-13 22:33'
labels:
  - models
  - size-3
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-13), who runs a local OpenAI-compatible server. Today each model is a table in ~/.config/bh-02/models.toml with a fixed id. Proposal, design first: a table with discover = true is an endpoint (provider openai, base_url, optional key) and names models ENDPOINT/ID. Resolution stays pure: ENDPOINT/ID needs no network (the table gives provider, base_url and key; the id is the rest), so models:model neither waits on nor fails at a server being up, and an id the server lacks is the first step's 404 as now. Discovery is listing only: models:catalog (the models value, already read fresh each time asked) asks GET {base_url}/models when /model lists, off the event loop with a short timeout, an unreachable endpoint shown as one line, never an error; the status bar never triggers it. No new row or key: models:switch depends on models, not model, so listing never reloads the model in use, and choosing a discovered model writes default = "ENDPOINT/ID" into the session's layer as now. The HTTP call behind a small Protocol faked in tests; parsing the /models reply a pure function. Trust: endpoints only from the trusted models file (never the project); the key only in the request's header; ids are the server's text, shown with control characters stripped, never a path or an argument; only the person picks a model. Open: a name rule for ids holding / or : (split at the first /); a filter for endpoints listing hundreds (include = ["qwen*"]); a short per-endpoint cache. Pairs with the models-file default ticket (default = "local/qwen2.5-coder").
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A models-file table with discover = true lists, under /model, every model its endpoint's GET /models returns, named ENDPOINT/ID; an unreachable endpoint is one line saying so, within a short timeout, off the event loop
- [ ] #2 ENDPOINT/ID resolves with no network call, by --model, /model and a layer's default; the model row never waits on discovery; a test
- [ ] #3 Ids from the server are shown with control characters stripped and never used as a path or an argument; the key is sent only in the request's header; endpoints are read only from the trusted models file; a test of each
- [ ] #4 An optional include filter narrows what is listed; the status bar never triggers discovery
- [ ] #5 docs/bh-02/using/models.md, the models plugin's README and CONTRACTS.md (if the models value's shape changes) describe it; scripts/check passes
<!-- AC:END -->
