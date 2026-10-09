---
id: TASK-0065
title: 'Give each fact one home in the docs, and cut the files agents load'
status: To Do
assignee: []
created_date: '2026-10-09 03:08'
labels:
  - docs
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The docs state the same facts in many places and have grown past what a reader, or an agent loading them every turn, can hold. The credential rules, the jail policy, the prompt-caching rationale, memory's loading order and `/compact` are each stated in 8 to 12 places. bh-02/CLAUDE.md (342 lines) is loaded into a coding agent's context on every turn, so it should keep the invariants and pointers, not explain the product. app/README.md (387 lines) carries a user guide and a plugin tutorial the docs site now has; CONTRACTS.md (329 lines) explains where it should state signatures and guarantees; GLOSSARY.md has drifted from one line per term; and bh-02.toml's comments explain the design. The Claude Code CLI version is cited as 2.1.282 in some places and 2.1.280 in others. Found by the review against cordis of 2026-10-09 (the separation, duplicates and docs review).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of these has one owning document, and every other place links to it instead of restating it: the credential rules, the jail policy, the prompt-caching rationale, memory's loading order, `/compact`
- [ ] #2 bh-02/CLAUDE.md is about 100 lines: the invariants an agent must keep and pointers to where the rest is
- [ ] #3 app/README.md is about 150 lines; the user guide and the plugin tutorial are on the docs site only
- [ ] #4 CONTRACTS.md is about 210 lines: each key its signature, its guarantees, who binds and who consumes it
- [ ] #5 GLOSSARY.md is one line per term again, and adds the senses harness has and the senses stack has
- [ ] #6 bh-02.toml's comments are one line each
- [ ] #7 The Claude Code CLI version is stated in one place, matching the pin
- [ ] #8 `uv run mkdocs build --strict` passes, and no fact the old docs stated is lost (a list of what moved where in the PR)
<!-- AC:END -->
