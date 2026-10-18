---
id: TASK-0158
title: Drop the models file's migration message for an endpoint table with its own id
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 19:09'
updated_date: '2026-10-18 19:17'
labels:
  - models
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner's no-compatibility rule (root CLAUDE.md, Conventions), decided 2026-10-18 after TASK-0157. named.py _endpoint_problem refuses an endpoint table that has its own id with a message written for the move from one model per table to endpoints with nested models (TASK-0104.01). It exists only to recognise that old shape. Dropped, such a table gets the generic error for a built-in provider (id is not a setting of the endpoint), and a factory provider (module:attribute) takes a stray id as it takes any other setting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _endpoint_problem has no check for an id on an endpoint table, and no message, docstring or doc page describes the old one-model-per-table shape
- [x] #2 The test files that used an old-shape table as their broken models file use another broken table, and still prove what they proved (each test's assertion is about its own subject, not the old shape)
- [ ] #3 A test shows an endpoint table with an id on a built-in provider is refused with the generic error; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order of work:
1. Add the new test in test_named_models.py in place of the old-shape test test_a_single_model_s_table_from_before_endpoints_says_how_to_rewrite_it (deleted: its subject is the old shape). Run it: it must FAIL on the current code (the old id message), which is the planted check.
2. named.py: remove the 'if "id" in table' branch of _endpoint_problem. _EXAMPLE stays (used by parsed() and to_add), so it is not removed. Re-run the new test: it must pass.
3. Swap old-shape broken tables for an unknown setting (colour = "red"), keeping each assertion about its own subject: test_session_dirs.py (app), test_models_discovery.py (_BROKEN, _why, match), test_models_discover_names.py (two cases), test_named_models.py (one parametrized case), test_models_broken_file.py (_BAD_DEFAULTS and _ENDPOINT_PROBLEMS key, renamed with its reference).
4. Docs: models-cordis-plugin README (lines ~74, ~119, ~261) and docs/bh-02/using/models.md (~143, ~202): drop the sentences and the 'an id' examples about the old shape; the generic unknown-setting error is what a built-in endpoint says now.
5. Proof: uv run pytest on the touched files while iterating; then scripts/check bh-02/plugins/models-cordis-plugin (gates and docs), scripts/check bh-02/app --no-gates --no-docs, scripts/arch-check --no-fix once (docs/ changed outside a member). Not the full scripts/check.
Risks: _why in test_models_discovery must reproduce the generic message exactly (allowed-setting list sorted); tests that match on the message must agree with named.py's wording. The factory path is unchanged (factory endpoints never reached the id branch's exclusion; they now take a stray id like any setting), no test added for it beyond what exists.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented. Changed: models_cordis_plugin/named.py (removed the 'if "id" in table' branch of _endpoint_problem; _EXAMPLE stays, used by parsed() and the to_add message); tests: test_named_models.py (deleted test_a_single_model_s_table_from_before_endpoints_says_how_to_rewrite_it, whose subject was the old shape, and added in its place a parametrized test over claude-code and openai: an id on an endpoint is refused with 'id is not a setting of a <provider> endpoint; it takes ...'; a parametrized case of test_a_table_with_a_problem now uses colour), test_models_discovery.py (_BROKEN is now a 'colour' setting; _why is the generic message), test_models_discover_names.py (two cases), test_models_broken_file.py (_BAD_DEFAULTS case and _ENDPOINT_PROBLEMS key renamed to 'an unknown setting beside discover', with its reference), app/tests/test_session_dirs.py (the broken table is colour). Docs: models-cordis-plugin/README.md (the 'format before endpoints' sentence, the 'an id on the endpoint itself' problem, the 'an id' example in the endpoint-problem sentence) and docs/bh-02/using/models.md (the sentence that a table with an id is refused and how to move it, the 'an id' example). Old files: a models file whose endpoint table has an id now gets the generic 'is not a setting of' error for claude-code and openai; a factory endpoint (module:attribute) with an id now takes it as a setting (problem() returns None, probed). Planted check: before removing the branch the new test failed in both cases with the old 'names an id, as a single model's table did' message (2 failed); after, 2 passed. Commands and real results: uv run pytest on the 5 models test files and app test_session_dirs.py: 191 passed; ruff check and ruff format --check on the touched paths: passed (first lint run failed on two lines over 110 columns, fixed); scripts/check bh-02/plugins/models-cordis-plugin: exit 0 (format, lint, types, 364 passed 2 skipped, gates, docs); scripts/check bh-02/app --no-gates --no-docs: exit 0 (347 passed, 1 skipped); scripts/arch-check --no-fix: exit 0. Not run: the full scripts/check, so the 'scripts/check passes' part of AC #3 is left unticked for the reviewer; scripts/linux-jail-check not run (per the delegation). decision-0009 read: it covers the trajectory and has nothing on endpoint tables; the task names no section.
<!-- SECTION:NOTES:END -->
