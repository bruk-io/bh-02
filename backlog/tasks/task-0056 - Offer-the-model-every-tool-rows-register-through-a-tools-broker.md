---
id: TASK-0056
title: 'Offer the model every tool rows register, through a tools broker'
status: To Do
assignee: []
created_date: '2026-10-09 00:36'
updated_date: '2026-10-09 03:07'
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
- [ ] #1 `agent:tools` binds a `tools` broker: a row registers a tool (a standard spec and an async function that runs a call) and gets back its remover; adding or removing a tool reloads nothing; CONTRACTS.md has the key and its shape
- [ ] #2 `agent:loop` depends on `tools`, not `kernel`: it offers every registered spec and runs each call through the tool it names; a call to a name nothing registered gets an unknown-tool result
- [ ] #3 The kernel row registers `python` with `tools`; with the kernel row disabled, a composition with another registered tool runs a turn end to end (a test with a fake tool)
- [ ] #4 `agent:system` names no tool. What the python tool tells the model (its REPL, what its jail lets it read and write) changes with each start, so the python row adds it as a `system` section of its own (`system.add("python", ...)`), never in the tool's description, which sits at the start of the cache prefix
- [ ] #5 A call returns its result together with the files it opened (no `touched()` asked after it); `notes` functions receive the call's tool name, its input and those files instead of `code`; `memory:on_touch` works from that for any tool
- [ ] #6 The loop offers the registered specs sorted by name, so the order rows register in, or register again in after a restart, means nothing
- [ ] #7 The loop reads the tool list once, at a conversation's first request, and keeps it for that conversation (TASK-0057 tells later changes). Its config `requires` (the shipped layer: `requires = ["python"]`) names the tools a conversation can't begin without: a message typed right after `/clear` waits until they have registered again, and one that never registers is said, not answered by a turn with no tools
- [ ] #8 A registration also says where its calls run (in a runner, or in bh-02's own process) and how a call is shown to the person; the loop asks `approval` about each call with those, and the approval modal and the transcript show a call that way, not as `input.code`
- [ ] #9 `agent:compact` asks `tools` for the specs
- [ ] #10 Restarting the Python process re-registers `python` without reloading the loop, and an identical re-registration is not a change to the tool list
- [ ] #11 bh-02/CLAUDE.md, CONTRACTS.md, GLOSSARY.md, the agent and kernel READMEs and the docs site describe the broker
<!-- AC:END -->
