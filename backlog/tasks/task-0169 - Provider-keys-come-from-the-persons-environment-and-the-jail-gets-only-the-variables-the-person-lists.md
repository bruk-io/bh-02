---
id: TASK-0169
title: >-
  Provider keys come from the person's environment, and the jail gets only the
  variables the person lists
status: To Do
assignee: []
created_date: '2026-10-25 17:39'
updated_date: '2026-10-25 18:03'
labels:
  - size-8
dependencies: []
priority: medium
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

A model's key is written two ways in the models file: `key` (the name of a line in `local.env`, openai only) and `key_command` with `key_ttl_ms` (a command that prints the key). They exclude each other, so there is a "give one, not both" error and two code paths for one idea. The person's keys already sit in their own environment (direnv, `op run`, a shell profile), yet bh-02 asks them to copy each one into `local.env`, a second place for a secret.

The `local.env` rule exists so a key never reaches code the model writes. The jail already scrubs the model's environment to an allow-list (the runner's `env` setting: PATH, HOME, LANG, LC_ALL, TERM by default), so the process environment is not what exposes a key; the allow-list is the guard. That setting is only reachable from a `--patch` layer, which is per-launch and easy to forget.

## Affected users and systems

- The person who writes `~/.config/bh-02/models.toml`: every `key` and `key_command` changes shape, with no migration (no backwards compatibility before a supported release).
- The models plugin (endpoint tables, the openai and claude-code providers, discovery) and its docs.
- The runner plugin: where its `env` allow-list is set.
- The jail docs, `get-started`, the `/release` and "adding your credential mid-session" flow, and the `hide = ["local.env"]` default, all written around `local.env`.
- `CLAUDE_CODE_OAUTH_TOKEN`, now read from `local.env` and handed only to the Claude Code CLI.

## Decisions already made (with the person, 2026-10-25)

- `key` becomes one object: exactly one source (`env`, `cmd` or `op`), plus an optional `ttl_ms` that is valid only with `cmd` or `op`. A bare string is refused. `key_command` and `key_ttl_ms` go away.
- `env` reads the process environment. `local.env` is retired, `CLAUDE_CODE_OAUTH_TOKEN` included: a `claude-code` endpoint without a `base_url` takes `key = { env = "CLAUDE_CODE_OAUTH_TOKEN" }` (or `cmd`/`op`) and hands it only to the Claude Code CLI it starts.
- The jail keeps its allow-list; it gets a standing home in the person's config directory (`~/.config/bh-02/`), not only a `--patch` layer. The runner plugin owns it, not the models file.
- `--no-jail` does not scrub provider keys. The docs say so plainly.
- A `claude-code` gateway endpoint takes `cmd` (and `op`, as `op read`), run by the Claude Code CLI. bh-02 never holds that key. `env` is refused there, with a message saying why.
- `key` is read only from the models file, never from a layer's `extra`.

## Open questions

- [ ] Where in `~/.config/bh-02/` does the runner's allow-list live (its own file, or a runner section of a config file), and how is it protected from the model, as the models file is today? Carried forward: it blocks only the allow-list's standing home, so it becomes a design task that the key-object and retire-local.env work do not wait on.
- [ ] Should startup refuse an allow-list that names a variable a `key = { env = ... }` also reads, so one line cannot leak a provider key into the jail? Carried forward: it needs the allow-list file to exist first, so it is decided in the same design task.
- [ ] Every process bh-02 spawns (the Python worker, the extensions process, `cmd` shells, the startup check): which already get an explicit environment, and which inherit bh-02's whole one? Carried forward: it only sets how truthful the docs' exposure wording is, so it becomes a spike that gates the allow-list work and the docs, not the key object.
- [x] Is `op` worth its own source, or is `cmd = "op read ..."` enough? Answered: keep `op` as its own source (it is how the person writes their examples); on a `claude-code` gateway endpoint it becomes `op read <ref>` for the CLI.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `key = { env = "NAME" }` on an openai endpoint sends the value of NAME from the process environment as that request's Authorization header, and a missing variable is refused with a message naming the variable and where it was looked for.
- [ ] #2 A `key` with `cmd` or `op`, and an optional `ttl_ms` (default 300000), behaves as `key_command` and `key_ttl_ms` did: run through the shell as the person, kept for the TTL, dropped at once when the server refuses it, and errors name the command, never what it printed.
- [ ] #3 A bare-string `key`, a `key` with no source or more than one, a `ttl_ms` beside `env`, an unknown field, and any `key` in a layer's `extra` are each refused with a message that says what to write instead; `key_command` and `key_ttl_ms` are no longer read and no test pins them.
- [ ] #4 A `claude-code` endpoint with a `base_url` accepts `key = { cmd = ... }` or `{ op = ... }` and hands the command to the Claude Code CLI; `{ env = ... }` there is refused with a message saying why; bh-02 never holds that key.
- [ ] #5 `local.env` is no longer read for any key or for `CLAUDE_CODE_OAUTH_TOKEN`, and the `hide = ["local.env"]` default, the credential-list entries and the `/release` and mid-session flows built on it are removed or reworded, with the docs saying which old files stop working.
- [ ] #6 The runner's environment allow-list is read from a standing file under `~/.config/bh-02/` without `--patch`, and the model's code cannot write that file; a test shows a variable not on the list (a provider key exported in the shell) is absent from the jailed worker's environment.
- [ ] #7 Under `--no-jail`, provider keys in the process environment are not scrubbed, and the jail docs state that this exposes them to the model's code.
- [ ] #8 README.md, docs/bh-02/using/models.md, the jail docs, get-started, GLOSSARY.md and the models plugin README describe the new `key` object, the environment source and the allow-list's home, and scripts/check passes.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-25 18:03

---

Spike TASK-0169.01 result: every spawn site is tabulated in its implementation notes. The jail is a real allow-list (`env -i` + `allow_names`), so a provider key in bh-02's environment does not reach the model's code unless listed. One unexpected exposure: `!COMMAND` passes the whole environment less ANTHROPIC_*/CLAUDE* and its output goes to the model; filed as a child task.

---
<!-- COMMENTS:END -->
