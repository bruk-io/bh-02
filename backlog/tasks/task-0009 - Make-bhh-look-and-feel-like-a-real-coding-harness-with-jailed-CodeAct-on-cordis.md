---
id: task-0009
title: >-
  Make bhh look and feel like a real coding harness, with jailed CodeAct on
  cordis
status: Done
assignee: []
created_date: '2026-09-22 23:36'
updated_date: '2026-09-23 00:37'
labels:
  - bhh
  - cordis
  - codeact
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bhh streams text only, so a run under --tools can't show what the model did, approvals interleave with the reply, and Ctrl-C kills the process. This initiative makes a turn visible (tool calls, results, thinking, usage, stop), asks for approval through the ui, cancels a turn rather than the program, and adds the owner's CodeAct pattern (harness/ARCHITECTURE.MD): one `python(code)` tool whose namespace is the tool registry, run in a persistent kernel inside a brig jail. It uses cordis where cordis fits: keys and rows for jail, kernel and what the model is offered; the broker for the namespace; a new effect where a component needs something from the runtime.

Reviewed by three Fable passes (cordis fidelity, CodeAct fidelity, UX/gate). Decisions from those: the `actions` key split (not a realm); no AST split of @component out of cells; one jailed subprocess kernel, one channel out; the SDK stack only observes stop reasons; approval point follows the jail; row reloads reach the ui through a new `observe` effect.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every subtask is Done
- [x] #2 `uv run bhh --tools --codeact` runs a jailed python kernel whose namespace is the tool registry
- [x] #3 pytest, ruff, mypy and scripts/arch-check pass
- [x] #4 CONTRACTS.md, the READMEs and CLAUDE.md describe what exists
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order (user said "go all the way", approving the reviewed plan):
1. 0009.01 brig in (done)
2. 0009.02 events contract: CONTRACTS event shape; chat Model/Output take events; LoopModel and ClaudeModel yield tool_call/tool_result/thinking/usage/stop; TerminalOutput renders (rich, already allowed in stdio); fakes updated.
3. 0009.03 approval via ui: Output.confirm(request) -> bool; terminal:approver depends on tools + output.
4. 0009.04 Ctrl-C: Input.interrupted(); converse races the reply against it; SIGINT handler entered by the console row; LoopModel closes dangling tool calls with an "interrupted" result.
5. 0009.05 stop classification (pure `classify` in agent loop, harness's table) + bounded nudges; provider message kept on the transcript entry and replayed by the ollama completion.
6. 0009.06 cordis `observe(fn)` effect over rt.listeners; console shows reload/failed lines.
7. 0009.07 `actions` key (tools:actions binds the registry), model rows depend on it; `system` key from a context plugin (cwd + CLAUDE.md/AGENTS.md) plus actions.instructions().
8. 0009.08 kernel-cordis-plugin: jail contract, kernel:unjailed, stdlib-only worker launched by path over a unix socket, Kernel client with run/interrupt.
9. 0009.09 brig-cordis-plugin: brig:jail.
10. 0009.10 codeact-cordis-plugin: codeact:python binds `actions` (one spec); codeact.toml; `--codeact` / `--no-jail` flags.
11. 0009.11 fs edit_file + diffs.
Each step: tests, ruff, mypy, arch-check green before the next.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
All eleven subtasks Done. Final state: 1386 tests pass (8 skipped: brig's platform-gated), ruff format/check clean, mypy strict clean (115 files), scripts/arch-check (workspace gate + brig's own gate) clean. Verified live with Claude haiku: Ctrl-C mid-reply keeps the session; --tools system prompt carries cwd/branch/CLAUDE.md; --codeact runs cells in the brig jail (raw open outside the project → PermissionError), Ctrl-C interrupts a running cell and the namespace survives; editing a watched layer shows `↻ row reloaded` / `✗ row failed`. Not verified live: an Ollama server (none on this machine; the loop+codeact path is covered by a composed test with a scripted completion); Linux jailing (brig:jail refuses off darwin and names kernel:unjailed). Nothing committed: the working tree also carries the earlier uncommitted warden work in shared files (pyproject.toml, CLAUDE.md, uv.lock, pypeeker_rules/bhh.py). Checkpoints of every step are in the session scratchpad (checkpoints/*.patch + *.untracked.tgz).

Out of scope, not started: slash commands (/clear /model /rows /explain), session log + resume, rich/Textual UI, model-written components mounted through a performer (the reviewers' `mount(source)` namespace call), Linux jail via strict_linux, fixing brig.mech's import cycle so brig's gate can turn no-import-cycles back on.

Final checks after the advisor's review: (1) real-repo jail probe: under the `bhh` console script the project is writable while member src, the shipped layer files, the venv's .pth, .git/hooks and CLAUDE.md are denied. Under `python -m` the project root is itself on sys.path and was being denied (project read-only); spec_for now never denies a host path equal to a writable root, with the residual risk (a module written at the root could shadow a not-yet-imported one) documented in the brig plugin README. (2) Live approval with the approver on: --tools shows the call, then asks on its own line; y runs it, n returns 'the user said no'. --codeact: a jailed cell's read_file call is asked mid-cell and the answer flows back into the cell. (3) The worker now exits when its host disconnects (os._exit from the reader thread), so a spinning cell can't outlive bhh; unjailed stop/interrupt tolerate darwin's EPERM for a zombie-only group. 1387 tests pass. Known cosmetic gap: a lifecycle line (↻ reloaded) can print onto a live `you> ` prompt.
<!-- SECTION:NOTES:END -->
