---
id: TASK-0068
title: >-
  Save auto memory through a memory tool of its own, run in bh-02's process, so
  it works in any composition
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-10 03:31'
updated_date: '2026-10-17 04:04'
labels:
  - memory
  - runner
  - tools
  - docs
  - size-5
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
- [x] The approval case's shape: a `runs` value of its own, or the request naming the one directory the call writes beneath, which `approval.unasked` checks against `host.auto_memory`. Answered by the owner (2026-10-17): a `runs` value of its own that is never asked, jailed or under `--no-jail` (not `"harness"`, which is asked under `--no-jail`, nor a directory check).
- [x] What happens to a hand-written MEMORY.md already there: regenerate over it, or keep its lines that point at no topic file. Answered by the owner (2026-10-17): keep them; the tool adds and removes only its own lines, one per topic file.
- [x] With the python tool present: point saves at `memory` in the prompt only, or also check the memory files an input wrote (an `asides` function; python's `touched` covers only the project root, so it would look at the directory). Answered by the owner (2026-10-17): the prompt only; a file written through Python is not checked.
- [x] Fold in the prompt gaps found against Claude Code's (check for an existing memory first, a **Why:** and **How to apply:** body, absolute dates, verify a memory against the code before acting on it), or leave them to a task of their own. Answered by the owner (2026-10-10): a task of their own, TASK-0069.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 memory-cordis-plugin registers a `memory` tool that saves, reads and deletes an auto memory by name; in a composition with no python tool the model can do all three, and the next conversation's prompt lists a saved memory in the index
- [x] #2 A save whose name is not a slug, whose `type` is missing or unknown, or whose `description` is longer than one line is refused with a message saying what to fix; saving a name that exists updates that memory, never a second file
- [x] #3 MEMORY.md always matches the topic files: a saved memory has its line, a deleted one loses it
- [x] #4 The tool runs in bh-02's process and runs without asking under runner:approval; every other `runs="host"` call is still asked, jailed and under `--no-jail`
- [x] #5 The tool reads and writes only beneath `host.auto_memory`, through no link: a link or a second name the model planted there is refused, not followed, and nothing outside the directory is written (tested, a link to a file outside it among the cases)
- [x] #6 The docs say plainly that the memory tool writes outside the jail, from bh-02's own process, and why: the memory plugin's README, the runner plugin's README where approval is described, CONTRACTS.md (`tools`, `approval`), bh-02/CLAUDE.md's list for the running harness, and the docs site's jail-and-approval page
- [ ] #7 `scripts/check` passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) host_paths: write_beneath and remove_beneath beside directory_beneath (the file is made under a random name beneath the directory by descriptor, then renamed over the name; a final link, a second hard-linked name or a non-file is refused, never followed), tests first incl. a link to a file outside the directory, then plant a following writer to see them fail. (2) approval: a runs value of its own ('memory'), unasked jailed and unconfined, host still asked; the tools broker accepts it; tests first. (3) memory plugin: a pure keeping module (spec, understood input -> Save|Read|Delete|refusal, topic text, MEMORY.md line edits that touch only the line for the name), the effectful keep over host_paths, run off the event loop; registered by memory:auto (so a sub-agent, which never gets memory:auto, never gets it); auto_section rewritten to point saves at memory only and trimmed per TASK-0069's review; tests first. (4) docs: memory README, docs memory.md and jail-and-approval.md, runner README, CONTRACTS tools/approval/request, GLOSSARY runs, bh-02/CLAUDE.md, decision-0002 note. Risks: the root gate's purity budget and over-exposed names; the new tools dependency of memory:auto in other tests' compositions. Proof: the new tests seen failing, then memory/runner/agent/subagents/host-paths tests, scripts/check for memory (gates, docs) and runner (no gates/docs), arch-check once.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-5 (2026-10-11): a host-side tool, an approval-rule case whose shape is still open, a no-link writer in host_paths, and docs in five places.

From TASK-0069's close review (2026-10-14), for when this task rewrites auto_section: bring the README and docs/bh-02/using/memory.md bullets level with the prompt ('read the code or git log for the current state'; 'split or summarise one that outgrows that'); say the 'don't save what CLAUDE.md, the code or git history records' rule in one place; trim where the review suggests (absolute dates, the file/function/flag sentence, 'later' in the description sentence); give the 200-line / 4 KB cap one spelling. Whether the tool refuses an oversized memory is DRAFT-0005, deferred.

Done 2026-10-17 on branch wt-0068 (machine shared with two other workers).

Which row registers the tool: memory:auto's own (it now consumes `tools` and registers `memory` with `runs="memory"` beside the prompt section), so a composition without the row, a host with no auto_memory, and a sub-agent (which never gets memory:auto, TASK-0080.07) have no tool. Checked: test_no_child_composition_includes_auto_memory_though_the_parent_has_it now also asserts the parent's tools have `memory` and the child's own broker does not.

Owner's answers (2026-10-17) as built: (1) a `runs` value of its own, "memory", never asked jailed or under --no-jail (approval.unasked: `runs in _UNASKED or (runs in _UNASKED_WHEN_CONFINED and confined)`; "harness" stays asked under --no-jail, every other "host" call stays asked); (2) MEMORY.md: only lines opening with a link to the memory's own file (`- [name](name.md): description`) are the tool's; a save replaces the first in place (extras dropped) or appends, a delete removes them, every other line is kept byte for byte (CRLF, no final newline, non-UTF-8 bytes via surrogateescape); (3) prompt points saves at `memory` only ("not by writing files there"); files written through Python are not checked.

Changed: libs/host-paths (write_beneath, remove_beneath beside directory_beneath: the file is made under a random name by descriptor beneath the directory with O_CREAT|O_EXCL|O_NOFOLLOW and renamed over the name; a final link, a second hard-linked name or a non-regular file is refused with Linked/NotOneFile and never followed; a link planted after the check is replaced by the rename, not followed). agent plugin tools.py (MEMORY value in the broker). runner plugin approval.py (the rule, its docstring says why it is safe). memory plugin: keeping.py (pure: spec, understood -> Save|Read|Delete|refusal, topic_text, with_line), directory.py (keep/call over host_paths, call runs keep in asyncio.to_thread), auto.py (auto_section rewritten, 25 KB one spelling), wiring.py (auto consumes tools). Docs: memory README, docs memory.md, runner README, jail-and-approval.md (new section), using/jail.md, CONTRACTS.md (tools, approval, request, host, memory rows, extensions line), GLOSSARY, bh-02/CLAUDE.md, host-paths README/CLAUDE.md, root CLAUDE.md, app README, rows-and-layers.md, subagents/extensions/agent READMEs, bh-02.toml comment, decision-0002 (dated amendment: the memory tool no longer uses the harness case). TASK-0069's close-review items done in the same rewrite: README and docs bullets level with the prompt, the don't-save-what-is-recorded rule said once, trims, "25 KB"/"4 KB" one spelling.

Proof (planted checks seen failing): (a) host-paths writer replaced by a plain O_TRUNC open through the name: 5 of the writing tests failed (link at the name, dangling link, hard link, replace/return value, cleanup), restored, 14 passed; the new test file failed at import before the code existed. (b) with_line changed to drop hand-written lines: 11 memory tests failed, restored, 150 passed. (c) new approval test, broker test and auto_section/row tests failed before their code (approval: 1 failed; broker: ValueError message; test_memory_auto: 9 failed with the old auto.py/wiring.py stashed).
Criterion evidence: #1 test_memory_tool_composition.py (real agent loop/tools/system and runner:approval, no python row; saves, reads, deletes by a scripted model; restart of memory-auto then system.text() lists the line) and test_memory_directory.py. #2 test_memory_keeping.py (names, type, description, body refusals; save under an existing name updates: one file, one line). #3 test_memory_directory.py/test_memory_keeping.py. #4 test_runner_approval.py (memory unasked with confined, unenforced and empty reports; host asked in all) and the composition test parametrised jailed/no-jail (the memory calls never reach output.confirm, a runs="host" tool does). #5 test_host_paths_writing.py and test_memory_directory.py (link/dangling link/hard link to a file outside for the index and for a topic file, read and delete included; outside file unchanged). #6 docs listed above; mkdocs build --strict ok.
Commands (read by exit code): scripts/check bh-02/plugins/memory-cordis-plugin exit 0 (format, lint, types, 150 tests, gates, docs); scripts/check --no-gates --no-docs for runner (88 passed, 1 skipped), agent (116, 1 skipped), subagents (130), extensions (44), libs/host-paths (41), each exit 0; scripts/arch-check --no-fix exit 0; bh-02/app/tests -m "not real_launch" 209 passed 1 skipped; two real-launch tests passed (shipped layer with a real memory dir).
Not ticked: #7 (scripts/check passes) is the reviewer's to prove.
Seen but not done (unsized): two sessions on one project share the memory directory (worktrees do) and a save is read-modify-write on MEMORY.md with no lock, so two simultaneous saves can lose a line; the cap on one read/save is the 4 MiB reading limit (DRAFT-0005 owns oversized memories).

Review (2026-10-17): READY, only #7 left for the orchestrator's full check. #1-#6 verified: only memory:auto (wiring.py:124) claims runs="memory"; extensions hardcode runs="jail" (host.py:565, tested for both spec and kwarg claims); subagents use harness. write_beneath/remove_beneath: O_EXCL|O_NOFOLLOW temp by dir_fd, rename never follows; slug checked before any path. 338 passed, 1 skipped (memory, host-paths, approval, agent, extensions host). Findings: nit - MEMORY.md read-modify-write without lock can lose a line on concurrent saves (worker noted).
<!-- SECTION:NOTES:END -->
