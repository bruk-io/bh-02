---
id: TASK-0055
title: >-
  Memory as Claude Code has it: CLAUDE.md, AGENTS.md, imports, rules and auto
  memory, in a memory plugin
status: In Progress
assignee: []
created_date: '2026-10-08 13:06'
updated_date: '2026-10-08 13:19'
labels:
  - memory
  - context
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Claude Code's memory (https://code.claude.com/docs/en/memory) as one cordis plugin, replacing the context plugin's context files with Claude Code's fixed places. The system prompt stays out of it: agent:system binds `system` and memory adds a section; the after-input broker is `notes` (agent:notes).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 agent:system binds the system prompt (who the model is, the directory and branch, the sections rows add); agent:notes binds the after-input broker
- [x] #2 memory:memory loads at launch the managed policy, ~/.claude/CLAUDE.md and ~/.claude/rules/, each directory's CLAUDE.md, .claude/CLAUDE.md and CLAUDE.local.md from the filesystem's root down to the project's, the project's rules without paths, and AGENTS.md as instruction_files says
- [x] #3 @path imports (four hops, not in code), block-level HTML comments out, excludes, 4 MiB limit, as Claude Code
- [x] #4 memory:on_touch tells a subdirectory's CLAUDE.md files and rules, and every rule whose paths match, with the first input that opens a file they cover; one the model opened itself is not told after
- [x] #5 No link the model could have made is followed and a file in the project imports nothing outside it
- [x] #6 /memory lists every memory file and how it loads
- [x] #7 update-layer rewrites layers naming context:project, context:on_touch or agent:memory
- [ ] #8 Auto memory: MEMORY.md and topic files the model writes in $XDG_STATE_HOME/bh-02/projects/<project>/memory/, which the runner lets an input write; the index's first 200 lines or 25KB told each session
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
memory-cordis-plugin replaces context-cordis-plugin (git history kept: reading.py was context_file.py, rules.py was sections.py, touch.py). agent:system binds the system prompt; agent:notes the after-input broker (was agent:memory). Claude Code's memory: managed policy, ~/.claude/CLAUDE.md and rules, the hierarchy from / to the project (CLAUDE.md, .claude/CLAUDE.md, CLAUDE.local.md), project rules without paths, AGENTS.md by instruction_files; @imports (4 hops, code skipped, a project file imports nothing outside the project), block HTML comments out, excludes, 4 MiB. On demand: a subdirectory's CLAUDE.md/CLAUDE.local.md/AGENTS.md and .claude/rules, every rule whose paths match; a memory file the model opened itself is not told after. /memory lists. Auto memory: bh_02.bootstrap.memory_directory (XDG_STATE_HOME/bh-02/projects/<project>/memory, project = git root or a worktree's main repo, named as Claude Code names it), made by the command line, layers.memory; brig:jail writes it (verified under real bubblewrap, and refused without it); memory:auto tells how to keep it and MEMORY.md (200 lines/25KB) once a conversation. update-layer rewrites context:project, context:on_touch, agent:memory. Differences from Claude Code: imports out of the project from a project file are not followed (no dialog); /memory lists rather than opens; no modified timestamp on writes.
<!-- SECTION:NOTES:END -->
