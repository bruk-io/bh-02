---
id: DRAFT-0014
title: 'A model''s key is one object: a source and an optional ttl_ms'
status: Draft
assignee: []
created_date: '2026-10-25 17:57'
labels:
  - size-5
dependencies: []
parent_task_id: TASK-0169
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The models file writes a key two ways, `key` (the name of a `local.env` line, openai only) and `key_command` with `key_ttl_ms`, and they exclude each other (TASK-0169). Replace both with one `key` object in an endpoint table, so a person writes each key one way:

```toml
key = { env = "OPENROUTER_API_KEY" }
key = { cmd = "my-token-helper get_token", ttl_ms = 600000 }
key = { op = "op://work/openrouter/key" }
```

`env` reads the process environment. `cmd` and `op` (as `op read`) are run through the shell as the person. There is no backwards compatibility before a supported release: the old attributes are not read and no test pins them; the notes say which models files stop working. This task does not remove `local.env` (a separate task does), but a `key` never reads it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `key = { env = "NAME" }` on an openai endpoint sends the value of NAME from the process environment as that request's Authorization header; a missing variable is refused with a message naming the variable and where it was looked for.
- [ ] #2 A `key` with `cmd` or `op` and an optional `ttl_ms` (default 300000) runs through the shell as the person, is kept for the TTL, is dropped at once when the server refuses it, and its errors name the command, never what it printed; discovery (`discover = true`) uses the same key.
- [ ] #3 A bare-string `key`, a `key` with no source or several, a `ttl_ms` beside `env`, an unknown field, and any `key` in a layer's `extra` are each refused with a message that says what to write instead.
- [ ] #4 `key_command` and `key_ttl_ms` are no longer read, no test pins them, and the change's notes say which models files stop working.
- [ ] #5 A `claude-code` endpoint with a `base_url` accepts `cmd` or `op` and hands the command to the Claude Code CLI, which runs it; `env` there is refused with a message saying why; bh-02 never holds that key.
- [ ] #6 docs/bh-02/using/models.md, the models plugin README, README.md and GLOSSARY.md describe the `key` object, and scripts/check passes.
<!-- AC:END -->
