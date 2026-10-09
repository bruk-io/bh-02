---
id: TASK-0067
title: >-
  Ask before a file is read or written, so instructions can arrive before a
  write
status: Done
assignee:
  - '@claude'
created_date: '2026-10-09 14:05'
updated_date: '2026-10-09 14:28'
labels:
  - agent
  - kernel
  - memory
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Instructions a file is covered by (a subdirectory's CLAUDE.md, a rule whose `paths` match) arrive with the result of the first call that opens it (memory:on_touch, a `notes` function), so they arrive after the call: one python input can read a file and write it, and the rule arrives after the write. Claude Code avoids this by construction: its Edit and Write refuse a file not Read first, and the instructions come with the Read. The model reads nothing mid-call, so an event before a file is opened only helps if it can stop the open: a gate, not a notification. An `access` broker (agent:access) takes `before_read(fn)` and `before_write(fn)`, each `fn(path) -> None` to allow or text to refuse. The tool raises the events: the python tool's worker asks bh-02 from its audit hook before Python opens a project file, only for the kinds some row is asking about, once per file per input; a refusal raises PermissionError in the input, and is told with the input's result whether or not the code caught it. memory:on_touch subscribes to `before_write`: the first write to a file covered by instructions the conversation has not been told is refused, and the instructions follow as the call's note, so the next write goes ahead. Decided with the owner (2026-10-09): implement both events now and say plainly what they do not see.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 agent:access binds an `access` broker: `before_read(fn)` and `before_write(fn)` each return a remover; `asking()` names the kinds some function is registered for; `refusal(kind, path)` is the refusals joined (sorted), None when all allow; a function that raises refuses, saying so
- [x] #2 The python tool's worker asks bh-02 before an input's own Python opens a file under the project (`open`, `pathlib`) for each kind asked about (read, write, or both for `+`), once per file and kind per input; an input with no kind asked about sends no question
- [x] #3 A refused open raises PermissionError in the input (the file is not opened), and every refusal is told with the input's result even when the code caught the error; the refused file is in `touched`
- [x] #4 memory:on_touch refuses the first write to a file covered by instructions this conversation has not been told (not a memory file itself), and those instructions follow as the call's note, so the next write to it goes ahead; reads are not refused by any shipped row
- [x] #5 Tests: the broker; the worker's question and answer, a refused read and write, a caught refusal still told, one question per file per input; on-touch's refusal; the shipped composition end to end (a refused write, the instructions told, the write again goes ahead)
- [x] #6 The limitations are written where the events are documented (CONTRACTS.md, the kernel, agent and memory READMEs, bh-02/CLAUDE.md, the docs site): only what the tool reports (python: Python's own `open`, not a program it runs, not `os.open`, rename, replace or delete); mid-call the model is told nothing, so a refused write can leave an input half done; no shipped row refuses reads; another tool raises them only if its author does
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. agent:access broker (before_read, before_write, asking, refusal; a failing function refuses). 2. Worker: the exec names the kinds asked about; the audit hook asks bh-02 over the socket before an input's own Python opens a project file, once per file and kind an input, any thread; a refusal raises PermissionError at the open (worker frames left out of the traceback) and is listed in `refused`. 3. Kernel client answers questions via access.refusal in a thread and ends the input's text with each refusal in brackets; kernel:kernel depends on access. 4. memory:on_touch subscribes before_write (refuse the first write to a file whose on-demand instructions are untold; they follow as the call's note). 5. Shipped layer row, tests, docs with limitations.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Choices: a failing access function refuses (a check that could not be made is not a yes). The refusal text names the instruction files, not their text: the text follows as the on-touch note, which keeps the transcript's `notes` record (what a resume reads) the one place a told instruction is recorded. Answers are kept per input, not across inputs, so a new CLAUDE.md is seen at the next input. The worker's own frames are left out of every input traceback now (they only ever appeared for this). Validation: ruff, mypy, scripts/arch-check, mkdocs --strict pass; the touched suites (agent, kernel, memory, tui, app python_repl/booting/outdated) 452 passed. Full suite under tini: 1933 passed, 3 failed: the two that fail on main in this VM (real-launch terminal-going-away, shell-command program-left-holding-output) and brig's property test test_ec1_narrowed_to_is_subset_of_both, which passed three times on rerun and is in a library this change does not touch.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
bh-02 can now be asked before a file is read or written. agent:access binds a broker (before_read, before_write, asking, refusal). The python tool asks from its audit hook before an input's own Python opens a project file, only for the kinds some row asks about, once per file and kind an input; a refusal is a PermissionError at the input's own line and ends the result in brackets even when the code caught it. memory:on_touch refuses the first write to a file whose on-demand CLAUDE.md or rule this conversation has not been told; the instructions follow as that call's note, so the next write goes ahead (Claude Code's read-before-edit, in bh-02's terms). Limitations, documented in CONTRACTS.md, bh-02/CLAUDE.md, the agent, kernel and memory READMEs and the docs site: only what the tool hears (Python's own open, not a subprocess, os.open, rename, replace or delete, nor files outside the project); the model hears nothing mid-call, so an input may be half done; no shipped row refuses reads; other tools ask only if their authors made them. Verified by test_agent_access (the broker), test_kernel (a refused write and read, a caught refusal still told, one question per file per input, kinds asked only when asked, nothing outside the project, the row asking access), test_memory_touch (the guard and the row), and test_python_repl (the shipped composition: refused, told, written).
<!-- SECTION:FINAL_SUMMARY:END -->
