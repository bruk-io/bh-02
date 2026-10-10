---
id: TASK-0059
title: Let the model's extensions register tools
status: Done
assignee: []
created_date: '2026-10-09 00:37'
updated_date: '2026-10-09 21:30'
labels:
  - extensions
  - tools
dependencies:
  - TASK-0056
  - TASK-0057
  - TASK-0058
references:
  - >-
    https://github.com/deepseek-ai/deepseek-harness/blob/main/.agents/notes/implemented/architecture/2026-09-16-creator-persistent-plugin-management.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The model can already extend bh-02 by writing `.bh-02/plugins/NAME.py`: `extensions:extensions` loads it in the jailed extensions worker, through `approval`, and it reaches bh-02 only through three add-only keys (`commands.register`, `frame.status`, `system.add`). It cannot add a tool, so a capability the model builds for itself is either a function in its REPL (scratch: gone with the process, never approved or recorded, callable only from python) or nothing. A tool an extension registers is part of the composition instead: a file that survives restarts, approved when it loads, recorded in the transcript, and offered to whichever model runs. DeepSeek Harness first ran model-written tools inside its host process, then removed that ("the sandbox isolates globals but is not a security boundary"); bh-02's extensions already run in a separate jailed process, and an extension tool's run function must stay there. Unconfined (`--no-jail`), every input is put to the person; an approved extension tool such as `shell(cmd)` would otherwise skip that question, so each call needs the same rule.

Refined by the review against cordis of 2026-10-09 (the separation, duplicates and docs review): the approval modal shows only `input.code`, so a call to an extension's `shell(cmd)` would read as "Run this shell code (0 lines)?". A registration says where its calls run and how a call is shown (TASK-0056), and the rule is `runner:approval`'s alone (TASK-0058).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An extension can register a tool through a fourth key, `tools`; the host checks each spec (a valid name and JSON Schema, a size cap, `python` and every layer row's tool names reserved) and says in status.json why one is refused
- [x] #2 A call to an extension's tool runs in the extensions worker, in the jail; the host only forwards the call and its result
- [x] #3 The host registers each extension tool as running in the extensions process's runner, and how a call is shown (its name and arguments); `approval` decides each call by the rule TASK-0058 separates, as it decides an input: confined, it runs; unconfined, the person is asked, shown the call that way
- [x] #4 Editing the extension redefines its tool; deleting the file removes it, and a later call gets an unknown-tool result
- [x] #5 The tool reaches the model as TASK-0057 says: told as a change, without losing the cache where the provider allows it
- [x] #6 The extensions system section tells the model how to register a tool, and a test registers, calls, redefines and removes one through the real worker
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Worker: a fourth key, `tools` (`_Tools.register(spec, run)`), bound per extension and isolated like the other three; it sends `add` with `kind: tool` and keeps `run`. A new wire op, `call` (`call`, `tool`, `input`), runs it and answers `ran` with the text the model reads: a string as it is, anything else as JSON, an exception as `error: Type: message`, an unloaded extension's as `error: this tool's extension has been unloaded`.
- Host: nothing the worker sends is trusted. `offered.offered_tool(spec, reserved)` (pure) rebuilds the spec from `name`, `description` and `parameters`, refusing a bad name (lowercase letters, digits, `_`, 48 at most, so `mcp__bh__NAME` fits), a missing or over-4,000-character description, parameters that are no object schema (each property typed, `required` naming properties), anything not plain JSON, and a spec over 16 KiB as JSON. Reserved: `python` always, and every name a row of bh-02's own has registered, noted on each look and kept even after that row's tool goes (a restart). A refusal is a `problem` in status.json, which now also lists each extension's `tools`.
- The host registers the tool with `runs = "jail"` and `show = offered.shown_tool_call` (its name, its extension, its arguments as JSON), so the loop's `Asked` puts each call to the `approval` rule as it does an input, and unconfined the person sees the call that way. `Extensions._call` forwards the call and its answer; a worker gone answers `error: ...`.
- Redefining or deleting the file is the existing unload/load path: the remover unregisters the tool, the loop's `toolset` tells the change on the next message (TASK-0057), and a later call to a removed tool gets the loop's removed-tool answer. With both shipped providers' `fixed` list, a tool added mid-conversation is offered from the next conversation; the system section and the change note say so.
- Tests: `test_extensions_offered.py` (the spec rules, the shown call), and in `test_extensions_host.py` the real worker with `agent_cordis_plugin.ToolBroker`: register, call, error, redefine, delete; refusals (`python`, a layer row's name while it restarts, a non-object schema); unconfined, the call is not unasked.
<!-- SECTION:NOTES:END -->
