---
id: TASK-0059
title: Let the model's extensions register tools
status: To Do
assignee: []
created_date: '2026-10-09 00:37'
updated_date: '2026-10-09 03:07'
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
- [ ] #1 An extension can register a tool through a fourth key, `tools`; the host checks each spec (a valid name and JSON Schema, a size cap, `python` and every layer row's tool names reserved) and says in status.json why one is refused
- [ ] #2 A call to an extension's tool runs in the extensions worker, in the jail; the host only forwards the call and its result
- [ ] #3 The host registers each extension tool as running in the extensions process's runner, and how a call is shown (its name and arguments); `approval` decides each call by the rule TASK-0058 separates, as it decides an input: confined, it runs; unconfined, the person is asked, shown the call that way
- [ ] #4 Editing the extension redefines its tool; deleting the file removes it, and a later call gets an unknown-tool result
- [ ] #5 The tool reaches the model as TASK-0057 says: told as a change, without losing the cache where the provider allows it
- [ ] #6 The extensions system section tells the model how to register a tool, and a test registers, calls, redefines and removes one through the real worker
<!-- AC:END -->
