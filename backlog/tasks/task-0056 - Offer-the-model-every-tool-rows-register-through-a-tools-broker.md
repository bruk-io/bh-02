---
id: TASK-0056
title: 'Offer the model every tool rows register, through a tools broker'
status: To Do
assignee: []
created_date: '2026-10-09 00:36'
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
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `agent:tools` binds a `tools` broker: a row registers a tool (a standard spec and an async function that runs a call) and gets back its remover; adding or removing a tool reloads nothing; CONTRACTS.md has the key and its shape
- [ ] #2 `agent:loop` depends on `tools`, not `kernel`: it offers every registered spec and runs each call through the tool it names; a call to a name nothing registered gets an unknown-tool result
- [ ] #3 The kernel row registers `python` with `tools`; with the kernel row disabled, a composition with another registered tool runs a turn end to end (a test with a fake tool)
- [ ] #4 `agent:system` names no tool; what the python tool tells the model (its REPL, its jail, how to use it) arrives with that tool, in its description or a section its own row adds
- [ ] #5 `notes` functions receive the call's tool name and input instead of `code`, and a tool may report the files a call opened; `memory:on_touch` works from that for any tool
- [ ] #6 `agent:compact` asks `tools` for the specs
- [ ] #7 Restarting the Python process re-registers `python` without reloading the loop, and an identical re-registration is not a change to the tool list
- [ ] #8 bh-02/CLAUDE.md, CONTRACTS.md, GLOSSARY.md, the agent and kernel READMEs and the docs site describe the broker
<!-- AC:END -->
