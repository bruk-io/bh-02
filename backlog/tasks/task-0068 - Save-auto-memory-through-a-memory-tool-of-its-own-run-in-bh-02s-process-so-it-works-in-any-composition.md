---
id: TASK-0068
title: >-
  Save auto memory through a memory tool of its own, run in bh-02's process, so
  it works in any composition
status: To Do
assignee: []
created_date: '2026-10-10 03:31'
labels:
  - memory
  - runner
  - tools
  - docs
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
memory:auto tells the model to keep auto memory but names no tool: it assumes some tool in the composition can write files (the python tool, in the shipped one). A composition with no python tool and no file-writing tool is told to save memories it cannot write and to read topic files it cannot open, so the model may say it saved something it did not. The save rules (a topic file per memory, `name`/`description`/`type` frontmatter, one line in MEMORY.md, no duplicates) are prose the model has to follow.

The memory plugin registers a `memory` tool of its own, so auto memory works in any composition: save, read and delete a memory by name, MEMORY.md kept from the topic files' frontmatter, each save checked (a slug name, a known `type`, a one-line `description`) and refused with what to fix. Like any registered tool it is also a function in a python input (`tools.memory(...)`).

Decided with the owner (2026-10-10): the tool runs in bh-02's process, not in the jail. The code that writes is bh-02's own, not the model's, and it writes only beneath the auto memory directory, which the jailed model can already write without being asked, so jailing it or asking adds no protection there; a jailed program per save would be a whole process for a small file write. So runner:approval gets one narrow case that lets this tool run unasked (every other host tool is still asked), and the tool writes through no link: a link the model planted in the directory is refused, never followed, with the writer in host_paths beside `directory_beneath`. A write that reaches past the jail is easy to misread as a hole, so the docs say so plainly, and why, wherever the tool, the jail or the approval rule is described.

## Open questions
- [ ] The approval case's shape: a `runs` value of its own, or the request naming the one directory the call writes beneath, which `approval.unasked` checks against `host.auto_memory`.
- [ ] What happens to a hand-written MEMORY.md already there: regenerate over it, or keep its lines that point at no topic file.
- [ ] With the python tool present: point saves at `memory` in the prompt only, or also check the memory files an input wrote (an `asides` function; python's `touched` covers only the project root, so it would look at the directory).
- [x] Fold in the prompt gaps found against Claude Code's (check for an existing memory first, a **Why:** and **How to apply:** body, absolute dates, verify a memory against the code before acting on it), or leave them to a task of their own. Answered by the owner (2026-10-10): a task of their own, TASK-0069.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 memory-cordis-plugin registers a `memory` tool that saves, reads and deletes an auto memory by name; in a composition with no python tool the model can do all three, and the next conversation's prompt lists a saved memory in the index
- [ ] #2 A save whose name is not a slug, whose `type` is missing or unknown, or whose `description` is longer than one line is refused with a message saying what to fix; saving a name that exists updates that memory, never a second file
- [ ] #3 MEMORY.md always matches the topic files: a saved memory has its line, a deleted one loses it
- [ ] #4 The tool runs in bh-02's process and runs without asking under runner:approval; every other `runs="host"` call is still asked, jailed and under `--no-jail`
- [ ] #5 The tool reads and writes only beneath `host.auto_memory`, through no link: a link or a second name the model planted there is refused, not followed, and nothing outside the directory is written (tested, a link to a file outside it among the cases)
- [ ] #6 The docs say plainly that the memory tool writes outside the jail, from bh-02's own process, and why: the memory plugin's README, the runner plugin's README where approval is described, CONTRACTS.md (`tools`, `approval`), bh-02/CLAUDE.md's list for the running harness, and the docs site's jail-and-approval page
- [ ] #7 `scripts/check` passes
<!-- AC:END -->
