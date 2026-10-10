---
id: TASK-0065
title: 'Give each fact one home in the docs, and cut the files agents load'
status: Done
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 23:55'
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
- [x] #1 Each of these has one owning document, and every other place links to it instead of restating it: the credential rules, the jail policy, the prompt-caching rationale, memory's loading order, `/compact`
- [x] #2 bh-02/CLAUDE.md is about 100 lines: the invariants an agent must keep and pointers to where the rest is
- [x] #3 app/README.md is about 150 lines; the user guide and the plugin tutorial are on the docs site only
- [x] #4 CONTRACTS.md is about 210 lines: each key its signature, its guarantees, who binds and who consumes it
- [x] #5 GLOSSARY.md is one line per term again, and adds the senses harness has and the senses stack has
- [x] #6 bh-02.toml's comments are one line each
- [x] #7 The Claude Code CLI version is stated in one place, matching the pin
- [x] #8 `uv run mkdocs build --strict` passes, and no fact the old docs stated is lost (a list of what moved where in the PR)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- The five facts' owners: the credential rules, models-cordis-plugin/README.md "The credential" (the jail's side in the runner README); the jail policy, runner-cordis-plugin/README.md (`spec_for`); the prompt-caching rationale, docs/bh-02/how-it-works/prompt-and-notes.md "Why the prompt stays fixed for a conversation" (now the tool list and the date too); memory's loading order, memory-cordis-plugin/README.md "What loads at launch" / "on demand"; `/compact` and `/clear`, agent-cordis-plugin/README.md (the conversation row). CONTRACTS.md, both CLAUDE.md files, the app README, the glossary, get-started, contributing, and the using/ pages link to them. The root CLAUDE.md keeps its credential rule whole: it is an instruction to every coding agent, not documentation.
- Sizes: bh-02/CLAUDE.md 405 -> 113 lines (invariants, each with a pointer); app/README.md 413 -> 151 (the user guide is on the docs site: layers, sessions, models, jail, commands, command line; the plugin tutorial and the fake models in extending/plugins.md); CONTRACTS.md 428 -> 206 (each key's signature, guarantees, binder and readers; Shapes gains `report` and `tools entry`); GLOSSARY.md one line per term (125), with the senses of harness and stack; bh-02.toml 220 -> 142, every comment one line.
- The Claude Code CLI version is stated once, in the models README's "Pinned, and why" (2.1.280, the one `claude-agent-sdk==0.2.158` bundles); the code comments that cited 2.1.282 or 2.1.280 now say "measured" or point there.
- The list of what moved where is in PR #15's description. Loose ends found on the way: the runner README's stale mention of the removed context plugin, and two code comments citing "CONTRACTS.md: jail" (now `report`).
<!-- SECTION:NOTES:END -->
