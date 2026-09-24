---
id: task-0003
title: 'Restructure bhh as ports, providers, a consumer and a shell'
status: Done
assignee: []
created_date: '2026-09-16 17:15'
updated_date: '2026-09-16 17:51'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bhh mixed the chat's contracts, the Claude backend, the terminal and its cordis integration in one flat package. As a stress test of cordis, restructure it so the layout shows the one dependency direction cordis's model implies: ports (`bhh.llm`: Model/ModelError, `bhh.ui`: Input/Output) import nothing; providers (`bhh.claude`, `bhh.terminal`) bind a value under a port from a `wiring.py`, their values being plain libraries free of cordis; the consumer (`bhh.chat`) holds the modes `session` and the new one-shot `ask`; the shell (`bhh.app`) is the click command, the bootstrap and two layer files, naming plugins as `cordis.plugins` entry points.

Design settled after two independent reviews: the error type lives on the `llm` port (no shared errors module); `ask.toml` is a layer over `chat.toml`; entry-point names are prefixed `bhh-`; `converse`/`one_shot` close a reply the output stopped reading; rows are `llm`/`ui`/`mode`. Review findings about cordis itself were split into follow-up tasks.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Ports `bhh.llm` and `bhh.ui` import nothing from bhh; providers import only their port; `bhh.chat` imports only ports; `bhh.app` imports only `bhh.llm` (gate rule `bhh-layering`, verified to fire on a planted violation)
- [x] #2 Only `*/wiring.py`, `bhh.app.bootstrap` and `bhh.app.cli` import cordis (gate rule `bhh-cordis-in-wiring-only`, verified to fire)
- [x] #3 `chat.toml` and `ask.toml` name every row as a `cordis.plugins` entry point and resolve through it; `bhh ask PROMPT` and `bhh ask < file` stream the reply alone to stdout and exit 1 on a ModelError
- [x] #4 `cordis.loader.resolve` has a test for its entry-point branch and names the installed plugins when a spec resolves to nothing
- [x] #5 Tests mirror the packages (tests/claude, terminal, chat, app), none needs a login; pytest, mypy, ruff and scripts/arch-check pass; CLAUDE.md and bhh/README.md describe the layout
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reset the abandoned app/wiring attempt. 2. Write ports, providers (value + wiring), chat (loop + wiring), app (cli, bootstrap, chat.toml, ask.toml), entry points in bhh/pyproject.toml, `uv sync`. 3. Tests per package with shared fakes in tests/conftest.py; CLI tests via CliRunner with the llm row patched to a fake. 4. Gate: re-point terminal rules, add bhh-layering and bhh-cordis-in-wiring-only, fix `*test_*` allow patterns, update exclude/allow entries; plant violations to confirm both new rules fire. 5. cordis: `resolve` lists installed plugins on a miss; test the entry-point branch with the existing `plugin` fixture. 6. Docs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built on branch refactor/ports. Two Fable reviewers assessed the proposal; accepted: ModelError on the llm port instead of a shared errors module, ask.toml as a patch layer, bhh- prefixed entry points, closing an abandoned reply in the loop (a real bug: the Claude provider's interrupt only ran on generator close), `*test_*` gate patterns, rows llm/ui/mode, a resolve test for the entry-point branch. Rejected: expressing bhh's layering with the builtin import-boundaries (without a root it polices top-level packages only, verified in pypeeker's rules.py), renaming `app` to `shell`. Both new gate rules were verified to fire on planted violations. cordis findings became task-0004, task-0005, task-0006.
<!-- SECTION:NOTES:END -->
