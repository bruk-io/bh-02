---
id: TASK-0060
title: Offer the registry's other tools to the python tool as functions
status: To Do
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
- [ ] #1 Each registered tool other than `python` can be called from an input as a function generated from its spec, and the call goes the same way a native call does (`approval`, `notes`)
- [ ] #2 A tool added or removed mid-conversation appears in or leaves the namespace, and the model is told with the next result
- [ ] #3 The docs explain the difference between a function the model defines in its REPL and a registered tool
<!-- AC:END -->
