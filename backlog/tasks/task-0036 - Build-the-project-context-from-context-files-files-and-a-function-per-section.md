---
id: TASK-0036
title: 'Build the project context from context files: files and a function per section'
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:05'
labels:
  - context
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/7'
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The project context was hard-wired to CLAUDE.md. Guidance comes in many shapes (AGENTS.md, CLAUDE.md in the home or the project, path-scoped rules with frontmatter, Cursor rules), so what is read and how it is told to the model became configuration: TOML sections, each a set of file patterns and the full module path of the function that turns the matched files into prompt text, organised as Claude Code organises its context.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A context file is TOML `[[section]]`s, each `files` (patterns) and `function` (`package.module:function`)
- [x] #2 bh-02's own file is read first, then the person's, then the project's; each appends its sections or starts afresh with `replace = true`
- [x] #3 bh-02 ships `place`, `rules`, `whole` and `named`; rules apply as their frontmatter says (always, paths/globs, description, manual)
- [x] #4 A guidance or rule file added, moved or removed reaches the model's next message without a restart
- [x] #5 A section that fails says so in one line and the others still say theirs
- [x] #6 Tests, gates and docs (README, CONTRACTS, GLOSSARY, CLAUDE.md) cover it
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged in PR #7 (c5e1d6c, a0888f6): context_cordis_plugin.context_file and sections; the shipped context.toml reads AGENTS.md/CLAUDE.md (home and project) with `place` and .claude/rules + .cursor/rules with `rules`; wildcard searches are redone only when a directory they looked in changed. Verified with the context plugin's tests and the full suite at merge.
<!-- SECTION:FINAL_SUMMARY:END -->
