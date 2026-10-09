---
id: TASK-0056
title: 'Offer the model every tool rows register, through a tools broker'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-09 00:36'
updated_date: '2026-10-09 04:22'
labels:
  - agent
  - tools
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/10'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop is CodeAct-only: it offers exactly one spec (`kernel.spec`), reads `call["input"]["code"]`, asks `kernel.touched()` after each call, and puts `kernel.instructions()` in the prompt; `agent:compact` offers `[kernel.spec]` too, and `agent:system` tells the model python is its only tool. bh-02 is meant to be like the pi harness: CodeAct (the python tool) is the shipped default, not a requirement, so a composition without the kernel row should still have a working loop with whatever tools other rows offer. A tool is a standard tool-calling schema (name, description, parameters), so the shape is a broker (paper 6.2) like `commands`, `system` and `notes`: rows register a spec and a function that runs a call, and the loop offers what is registered. This revisits TASK-0009.10, where the registry's only presentation was functions inside one python tool. Tool definitions are the very start of a model server's cache prefix (tools, then system, then messages), so the list must stay as stable as the system prompt is today: an identical re-registration must not count as a change.

Refined by the review against cordis of 2026-10-09 (the separation, duplicates and docs review): the python tool's instructions change with each start (what its jail lets it read and write), so in its description they would redefine the tool and cost the cache, and they go in a `system` section of the python row's instead; a call returns the files it opened with its result, rather than the loop asking `touched()` after; the specs are offered in name order, as `system`'s named sections are since df21009, so a re-registered `python` doesn't move to the end; the loop reads the list at a conversation's first request, after the tools it requires have registered, so a message typed right after `/clear` can't begin a conversation without `python`; and a registration says where its calls run and how one is shown, because approval today assumes every call is Python code run in the jail (the modal shows only `input.code`).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `agent:tools` binds a `tools` broker: a row registers a tool (a standard spec and an async function that runs a call) and gets back its remover; adding or removing a tool reloads nothing; CONTRACTS.md has the key and its shape
- [x] #2 `agent:loop` depends on `tools`, not `kernel`: it offers every registered spec and runs each call through the tool it names; a call to a name nothing registered gets an unknown-tool result
- [x] #3 The kernel row registers `python` with `tools`; with the kernel row disabled, a composition with another registered tool runs a turn end to end (a test with a fake tool)
- [x] #4 `agent:system` names no tool. What the python tool tells the model (its REPL, what its jail lets it read and write) changes with each start, so the python row adds it as a `system` section of its own (`system.add("python", ...)`), never in the tool's description, which sits at the start of the cache prefix
- [x] #5 A call returns its result together with the files it opened (no `touched()` asked after it); `notes` functions receive the call's tool name, its input and those files instead of `code`; `memory:on_touch` works from that for any tool
- [x] #6 The loop offers the registered specs sorted by name, so the order rows register in, or register again in after a restart, means nothing
- [x] #7 The loop reads the tool list once, at a conversation's first request, and keeps it for that conversation (TASK-0057 tells later changes). Its config `requires` (the shipped layer: `requires = ["python"]`) names the tools a conversation can't begin without: a message typed right after `/clear` waits until they have registered again, and one that never registers is said, not answered by a turn with no tools
- [x] #8 A registration also says where its calls run (in a runner, or in bh-02's own process) and how a call is shown to the person; the loop asks `approval` about each call with those, and the approval modal and the transcript show a call that way, not as `input.code`
- [x] #9 `agent:compact` asks `tools` for the specs
- [x] #10 Restarting the Python process re-registers `python` without reloading the loop, and an identical re-registration is not a change to the tool list
- [x] #11 bh-02/CLAUDE.md, CONTRACTS.md, GLOSSARY.md, the agent and kernel READMEs and the docs site describe the broker
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. agent: a `Tools` broker (tools.py) over cordis_helpers.Registry: register(spec, run, *, runs="jail", show=None) -> remover (name from spec, unique), specs() sorted by name, get(name), and `await ready(names, timeout)` -> the names still missing (an asyncio.Event set on each change). `agent:tools` binds it, depending on nothing. CONTRACTS.md: the key, a registration, a call's result ({"content", "touched"?}).
2. agent:loop depends on `tools`, not `kernel`. At a loop's first request it waits for its config's `requires` (the shipped layer: ["python"]) up to `wait` seconds, saying so while it waits; a name that never registers raises a recoverable error (kind "tools_missing", the message saying which and where to look) before the message is kept. Then it snapshots the specs, sorted, and offers that list for its life; each call runs through the registration its name has now; a name with none answers "no tool named X; your tools are ...".
3. Each call: approval.approve({"name", "input", "runs", **show(input)}) (default show: "Call NAME?" and the input as JSON); approval asks whenever runs is "host", and by confinement for "jail". The tui's approval modal shows the request's `lines` (in `language`) when given, else input.code as today. The transcript already renders any call generically (name, short args, a `code` arg as a block).
4. notes functions get {"name", "input", "result", "touched"}; memory:on_touch reads "touched" as before (any tool).
5. kernel: Kernel.call(input) -> {"content", "touched"} (refuses a missing `code` as text); kernel:kernel acquires tools.register(PYTHON, call, show=python's) and system.add("python", kernel.instructions). python.py stops saying it is the only tool. agent:system's _HARNESS names no tool.
6. agent:compact offers tools.specs().
7. Tests: the broker (sorted, unique, remover, ready/timeout, identical re-register); the loop with a fake tool and no kernel row (end to end through the runtime); unknown tool; requires timeout; a kernel restart re-registers without reloading the loop; approval host vs jail; the modal's lines; compact's specs. Update existing tests and the app/test fakes.
8. Layers: bh-02.toml gains the tools row and the loop's requires; update-layer: a layer naming agent:loop without tools gets it (check how outdated layers are handled).
9. Docs: bh-02/CLAUDE.md, CONTRACTS.md, GLOSSARY.md, agent/kernel/memory READMEs, app README, docs site; then the full check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decisions made while building it: (1) a registration is register(spec, run, *, runs="jail", show=None); a run answers {"content": str, "touched"?: [...]}, and the loop turns a raise or another shape into an error the model reads. (2) A tool that runs on the host (runs="host") is put to the person whatever the jail grades: nothing the model asks for runs unconfined unasked. No host tool exists yet. (3) The list is kept by the loop instance, for its life (a /model switch makes a new loop, which reads it again); keeping it in the transcript is TASK-0057. (4) requires defaults to [] (CodeAct is a default, not a requirement); the shipped layer sets ["python"]. A layer that overrides the loop row's config replaces it, as any override does. (5) The loop checks a call's input against the spec (required keys, simple JSON types) before approval, so a malformed call is never put to the person, as before. (6) The transcript view already renders any call generically (name, short args, a `code` argument as a block), so `show` changes only the approval modal. (7) update-layer no longer drops a row with the id `tools`: only a row using the pre-CodeAct `tools:` plugin is dropped; a `tools` row naming no plugin is now a change to agent:tools. (8) The kernel row now depends on `tools` and `system`, both brokers that never reload; editing the system row's config would now restart the kernel. Validation: ruff, mypy, scripts/arch-check, mkdocs --strict all pass. Full suite under tini: 1924 passed; the 2 failures (test_real_launch terminal-going-away, test_shell_command program-left-holding-output) fail identically on main in this VM. brig's network integration tests were excluded (environmental here).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The loop no longer knows python. agent:tools binds a broker (ToolBroker): rows register a spec and a run function (plus runs and show), and the loop offers every registered spec in name order, read once at its first request after its config's `requires` have registered (the shipped layer requires python; it waits up to `wait` seconds, else the message fails with kind tools_missing). Each call runs through its tool's registration (one restarting is waited for); a name the loop did not offer, or an input that does not fit the spec, is answered as text and put to nobody. The approval request carries `runs` and the tool's way of showing the call: a host tool is always asked, and the tui modal shows `lines` in `language`. notes functions get {name, input, result, touched}. kernel:kernel registers python (Kernel.call, shown_call) and adds its instructions as the system section `python`; agent:system names no tool; /compact offers tools.specs(). update-layer keeps a tools row naming no plugin. Verified by new tests in agent (test_agent_tools: broker order, uniqueness, removers, ready/timeout, an end-to-end turn with no kernel row, waiting for and failing on a required tool, a tool row restarting without reloading the loop, a call waiting for a restarting tool, the snapshot), kernel (the row's registrations and section, call, host approval), tui (approval lines and language), agent system (no tool named), and the updated loop, compact, app and outdated-layer tests. Docs: CONTRACTS.md (the tools key, the tool result and request shapes, tools_missing), bh-02/CLAUDE.md, GLOSSARY.md, the agent, kernel, models, memory and app READMEs, the root README, the docs site and the shipped layer's comments.
<!-- SECTION:FINAL_SUMMARY:END -->
