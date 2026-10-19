---
id: DRAFT-0014
title: 'Say each fact about bh-02 once, so the prose stops drifting'
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-19 03:46'
labels:
  - docs
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
I'll have to remember to clean up the prose. bh-02's documentation is heavy: CONTRACTS.md rows are single cells that run for paragraphs, READMEs and docstrings carry a lot of reasoning, and the same fact is often written in three to five places (a docstring, the plugin's README, CONTRACTS.md, GLOSSARY.md, the docs site). Every behaviour change has to find and update each copy, and the copies drift: in the 2026-10-18 run, TASK-0163 and TASK-0167 existed only to bring wording back in line with a change another task had made. Workers and reviewers also have to read all of it before they can start.

## Affected users and systems
- Me, reading and maintaining it.
- The agents that work on bh-02: workers read the CLAUDE.md files, READMEs and CONTRACTS.md before a plan; reviewers judge against them.
- bh-02/CONTRACTS.md, bh-02/GLOSSARY.md, each plugin's README, module and function docstrings, docs/bh-02 (the docs site), the CLAUDE.md files.

## Open questions
- [ ] The one-home map: which kind of fact lives where (a key's shape and promise, a row's behaviour, the reason for a design, a term, how to use a command).
- [ ] Whether a check guards against drift mechanically: a word budget per file or cell (as DeepSeek Harness's verify-doc-budgets), a check that every GLOSSARY term and CONTRACTS key still names something in the code, or both.
- [ ] Whether the docs site and the plugin READMEs overlap enough that one should link to the other instead.
- [ ] How the work splits: per plugin, per kind of document, or one sweep.

Drafted by the orchestrator from a conversation with the owner (2026-10-19); the owner corrects it before anyone accepts it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each fact about how bh-02 behaves has one home, and every other place that needs it links there instead of restating it (checked on a sample of facts across the plugins)
- [ ] #2 CONTRACTS.md gives each key's shape and promise briefly enough to read as a table
- [ ] #3 Docstrings say what a function does and its contract; reasoning that spans modules lives in the one document it belongs to
- [ ] #4 Must not break: no behaviour changes, and scripts/check passes
- [ ] #5 Must not break: nothing a worker needs to work safely is lost, the rules in the CLAUDE.md files above all
<!-- AC:END -->
