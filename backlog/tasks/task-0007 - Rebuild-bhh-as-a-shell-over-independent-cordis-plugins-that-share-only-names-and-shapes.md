---
id: task-0007
title: >-
  Rebuild bhh as a shell over independent cordis plugins that share only names
  and shapes
status: Done
assignee: []
created_date: '2026-09-16 18:29'
updated_date: '2026-09-16 21:02'
labels:
  - bhh
  - cordis
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Second rebuild of bhh, grounded in a full read of cordis and of the paper's §6.2 (service broker) and DeepSeek Harness's ctx.tools / ctx.llm registries. The first rebuild (task-0003) got the port/provider/consumer shape right but treated the model as the only capability. This one adds what a harness needs beyond chat, using cordis's own mechanisms and no runtime change:

- `bhh.tools`: a concrete `Tools` registry bound once by `bhh-tools:registry` (the broker). Tool plugins depend on `Tools` and yield a `register(tools, tool)` effect whose undo unregisters; approvers yield `guard(tools, fn)`. Both are commutative registrations (paper Def. 44). The registry owns the execution pipeline: decide (guards, any deny wins) then execute. Adding or removing a tool or an approver perturbs nothing else.
- `bhh.llm`: `Model` (a conversation modes talk to) and `Completion` (one stateless model turn over messages + tool schemas, streaming text deltas and tool calls). `bhh-agent:loop` consumes `Completion`, `Tools` and `Transcript` and provides `Model`; history lives in `Transcript` (`bhh-transcript:memory`) so an adapter swap restarts the loop without losing the conversation.
- `bhh-claude:model` (plain chat over the Agent SDK) and `bhh-claude:agent` (the SDK's own loop, with the registry's tools exposed as in-process MCP tools and guards behind `can_use_tool`). `bhh-ollama:completion` as a raw adapter, translation unit-tested, not run against a live server.
- `bhh-fs:tools` (read_file, list_dir) as a real tool plugin; `bhh-terminal:approver` as a guard that asks on the terminal.
- Layers: chat.toml; agent.toml over it (SDK agent + tools + approver + fs); loop.toml over it (ollama + loop + transcript); ask.toml.
- Gate rules updated; docs rewritten; the SDK stack's limitation documented (tool set snapshotted at activation; the loop reads schemas per request).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Unloading a tool plugin removes its tool from the registry and the model sees the change on the next request; unloading an approver removes its guard; neither restarts the llm or mode rows
- [x] #2 The loop drives a scripted Completion through a text turn, a tool-call turn with an allowed call, and a denied call; the transcript survives an adapter swap
- [x] #3 bhh-claude:agent exposes registry tools to the SDK and routes can_use_tool through the registry's guards (tested with fakes, no login)
- [x] #4 Every layer file resolves; chat, ask, agent and loop compositions boot with fake rows in tests; CLI has `bhh`, `bhh ask`, `bhh --agent`
- [x] #5 Gate passes with rules for ports, providers, consumer, shell and cordis-in-wiring/effects; pytest, mypy, ruff pass; CLAUDE.md and bhh/README.md rewritten

- [x] #6 Each plugin is its own workspace member named `<name>-cordis-plugin` (import `<name>_cordis_plugin`) with a pyproject, entry point, README and tests; `bhh` is only cli, bootstrap and layer files and imports no plugin but the `llm` port; no plugin imports another plugin (gate rule `plugin-layering`, verified to fire)

- [x] #7 No workspace package depends on another (every plugin's pyproject lists only cordis, plus the SDK for the Claude plugin); the shared keys and shapes live in CONTRACTS.md
- [x] #8 cordis: a dependency's key is the parameter's name and its class annotation is the consumer's contract, checked structurally when the value is committed, before the first effect; `bind` accepts anything; a new `acquire` effect keeps a registration's return value as its undo; invariants pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built on branch rebuild/broker after reading cordis's runtime, effects, decisions, inspection and testing modules in full, the paper's sections 3.2.3, 4.2, 6.2 and 6.3, and DeepSeek Harness's tools/llm registries and permission gate. Mid-build the owner asked for one workspace member per plugin with the `-cordis-plugin` suffix, no `bhh` prefix anywhere, and the Claude plugin named for the SDK it wraps; done. Ports ship `testing` modules so plugin tests never import another package's tests. Both custom rules verified to fire on planted violations. Not verified in this session: the Claude agent path against a live login (MCP server + can_use_tool are unit-tested with fakes) and the Ollama adapter against a live server (translation unit-tested).

Third pass, at the owner's request to go all the way: no dependencies between workspace packages at all. Required one cordis change (name-keyed dependencies with consumer-side contracts, closing the paper's 6.6 on the consumer's side) plus the `acquire` effect; llm-cordis-plugin and ui-cordis-plugin were deleted, their content becoming CONTRACTS.md. Each consumer now declares its own Protocol for what it needs; data crosses as dicts. 501 tests, mypy, ruff, gate; plugin-layering verified to fire on a planted cross-plugin import.

Added `cordis-helpers`, a library member (not a plugin) holding the domain-free half of the broker: `Registry[T]` and `Hooks[F]`, each registration returning its remover. `tools-cordis-plugin` is built on it and keeps only the tool domain (specs, decide, call). The layering rule now names `cordis` and `cordis_helpers` as the libraries every plugin may import.
<!-- SECTION:NOTES:END -->
