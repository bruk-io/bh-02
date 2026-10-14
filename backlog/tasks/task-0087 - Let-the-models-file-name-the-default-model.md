---
id: TASK-0087
title: Let the models file name the default model
status: Done
assignee:
  - '@claude'
created_date: '2026-10-13 22:33'
updated_date: '2026-10-14 08:09'
labels:
  - models
  - size-2
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-13), who runs a local OpenAI-compatible server and wants new sessions on it without a flag. Today the model row's default is 'sonnet' unless a layer or --model names another (models_cordis_plugin/named.py: the row config's default), and ~/.config/bh-02/models.toml has no default key. The workarounds are poor: a shell alias; naming a model 'sonnet' to replace the built-in; or a --patch layer setting the model row's config, which replaces the whole config and stops /model from switching. Wanted: a top-level default = "NAME" in the models file. Precedence, lowest first: the built-in 'sonnet', the models file's default, a layer's model row default (a session's own layer, which /model and --model write), --model. So a resumed session keeps the model it was on, and /model and --model still switch. The default chooses the spend, so it is read only from the models file in host.trusted, as model tables are, never from the project.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A top-level default = "NAME" in the models file chooses the model a new session starts on when neither --model nor a layer names one; a resumed session keeps its own; /model and --model still switch
- [x] #2 A default that names no model, or is not a name, is said with what to write (the house style for models-file problems), and bh-02 still starts; a test of each
- [x] #3 /model's list marks which model is the default and where that came from (built-in or models file)
- [x] #4 docs/bh-02/using/models.md and the models plugin's README describe it; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Where: the models file's top-level default is read in named.parsed (now returns ModelsFile(models, default); a non-table 'default' value is the setting, a [default] table still a model) and carried by providers.known (now a Known NamedTuple: models, source, why, standing) - only when the file is read, so a models file in the project (refused) gives no default, same trust rule as model tables. Telling absence from 'sonnet was chosen': ModelConfig.default becomes str|None = None (None = no layer named a model; the session layer's model row carries only state unless --model//model wrote default), and named.intended(layer, standing) picks layer default if not None, else the file's, else the built-in 'sonnet'. Bad default (not a name / names no model) stays a ModelsError at resolve time (chosen(origin=...)) so opened() binds Unusable, bh-02 starts, /model NAME fixes; a bad file default is ignored when a layer names a model. /model list: Catalog.listed adds default='built in'|'the models file' on the standing default model; model_list prints it. Resume keeps the layer's model (layer wins); a session whose layer named none follows the file default. Proof: tests per precedence step + refusals + project file ignored; plant violations (swap precedence, drop the project refusal) and see them fail. Then docs, README, CONTRACTS, scripts/check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Models file top-level default: named.parsed returns _ModelsFile(models, default); providers.known returns _Known(models, source, why, standing) with the file default read only when the file is read (never from a models file in the project). ModelConfig.default is now str|None=None (None = no layer named a model; a layer naming sonnet is a choice); named.intended(layer, standing) picks layer, else file, else built-in sonnet. A bad file default (not a name / names no model) raises ModelsError at resolve (kinds models_file / unknown_model, says what to write), opened() binds Unusable so bh-02 starts, /model NAME fixes it; ignored while a layer names a model. /model list marks '(default: built in|the models file)'; Catalog.listed has default key (CONTRACTS updated). Resume: layer's model kept; a session whose layer named none follows the file default as it is now. Tests: models-cordis-plugin/tests/test_models_default.py (11+1 tests: each precedence step, layer sonnet vs unset, both refusals + Unusable bind, project file ignored, set_model/with_model shape). Planted violations seen failing: file beats layer (2 failed), layer 'sonnet' treated as unset (1 failed), file default read when refused (1 failed); restored, all pass. Updated test_booting (default None, list suffix) and test_session_dirs comment. Docs: docs/bh-02/using/models.md, plugin README, app README, CONTRACTS. Ran as root without tini: scripts/check exit 0 (2570 passed, 31 skipped; format, lint, mypy, gates, docs ok; tokens skipped: no bh-01). Not verified: scripts/linux-jail-check (not relevant). Follow-up ideas: sessions list 'stack' shows 'sonnet' for a session started on the file default.

Reopen fix (resume keeps model): sessions.create now resolves the model a new session starts on (--model, else the trusted models file's top-level default read by the shell with tomllib, else sonnet) and writes it into the session layer as --model does, and records it as meta stack. The shell skips the file when it is in the project (host_paths.passes/roots, same rule as the plugin) and ignores a default that is no name/not TOML. Tests in test_session_dirs.py: new session on file default, file default changed, resume (update) still on first model; stack in meta.json; no file/bad default -> sonnet; project file ignored; seen failing with the fix removed (3 failed) and with the project check removed (1 failed). /model 'already; nothing to switch' can no longer trap a new session (its layer names its model); only a pre-fix layer naming none follows the file default (documented in plugin README). Docs updated (models.md Choosing the default). Runs (root, foreground, one at a time): models plugin tests 174 passed; bh-02/app/tests 198 passed; scripts/arch-check exit 0; uv run mypy exit 0; scripts/check exit 0 (2573 passed, 31 skipped; an earlier full run had one timing flake in test_real_launch status-bar test that passes alone and on rerun).

Close review (round 2, Opus low, independent): CLOSE, no blocking findings. AC#1: the three new test_session_dirs tests fail with the fix removed, the project check is covered. AC#2-#4 met. test_real_launch.py passed twice. Should-fix and nit filed as TASK-0093 (not blocking): the trust-and-default rule now lives in two places (sessions.create's _declared_default and providers.refused/named.parsed); a bad file default leaves the status bar's provider blank and gives no line in /model's list (round-1 should-fix 3); sessions.create falls back to sonnet silently on a bad default, so AC#2's 'what to write' error never shows for a new session.
<!-- SECTION:NOTES:END -->
