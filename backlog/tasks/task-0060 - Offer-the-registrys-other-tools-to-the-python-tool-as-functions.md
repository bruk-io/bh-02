---
id: TASK-0060
title: Offer the registry's other tools to the python tool as functions
status: Done
assignee: []
created_date: '2026-10-09 00:37'
labels:
  - kernel
  - tools
dependencies:
  - TASK-0056
references:
  - >-
    https://github.com/deepseek-ai/deepseek-harness/blob/main/.agents/notes/implemented/feature/2026-06-15-ptc.md
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Where a provider cannot add a tool mid-conversation without losing its cache (an OpenAI-compatible or local model renders the tool list into the start of the prompt), a tool registered later, such as an extension's, is unusable until the next conversation. CodeAct needs no change to the tool list: an input can call the registry's tools as Python functions generated from their specs, and a note says they are there. DeepSeek Harness's `both` mode is this shape (an SDK generated from its tool registry beside the native tools). The registry stays the one place tools live; the namespace is a view of it, never where a tool is registered, which keeps it within the cordis model.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each registered tool other than `python` can be called from an input as a function generated from its spec, and the call goes the same way a native call does (`approval`, `notes`)
- [x] #2 A tool added or removed mid-conversation appears in or leaves the namespace, and the model is told with the next result
- [x] #3 The docs explain the difference between a function the model defines in its REPL and a registered tool
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- `tools` (agent): `serve(call) -> remover`, the loop row's (`tools.serve(loop.nested)`), and `call(name, input) -> {"content", "failed"}`, which passes a call on to it (with no loop serving, failed, saying so). The broker stays where tools live; the namespace is a view.
- `LoopModel.nested(name, input)`: a call a tool's own call makes, run as the model's are: the tool its name has now, `malformed` checked, `approval` (`Asked`: the rule, then the person) with the tool's own `show`, `called`, then `notes` on `executor`. Its notes are kept (`_nested`) and told with the result of the call that made it, recorded in that call's `notes`. `called` now also says whether the tool failed.
- Python worker (stdlib only): each `exec` carries `tools`, the specs of every tool but `python`; the namespace's `tools` (`_Offered`) is rebuilt from them before the input (none: no `tools` at all; an input that bound `tools` itself keeps its own). `tools.NAME(**arguments)` asks the host (`{"op": "call"}` over the existing ask/answer channel) and returns the content, or raises `tools.Error` (`ToolError`) when it did not run or failed; each function has the spec's description and arguments as its docstring and a keyword-only signature.
- `Kernel` (python row): given `tools` (`Calls`: `specs`, `call`); sends the specs with each input, answers `call` through `tools.call` (never `python` itself), and tells before an input's own output which tools there are (the first time) or what was added, redefined or removed (`_offered`). The `python` section says so, statically, and says a function the model defines is its alone while a tool is bh-02's.
- Docs: the python tool page's new section (with a table of a REPL function against a registered tool), CONTRACTS (`serve`, `call`, the python tool), the agent and python READMEs, bh-02/CLAUDE.md, GLOSSARY (`tools` in an input).
- Tests: agent (`call` with no loop; a nested call's approval, refusals and notes told with the outer call), python (the real worker: calls, `tools.Error`, the first and changed notes, an input's own `tools` kept, none offered), app (booted from the shipped layers with a layer row's `echo`: an input's call put to the person as a model call would be, a no raising `tools.Error`).
<!-- SECTION:NOTES:END -->
