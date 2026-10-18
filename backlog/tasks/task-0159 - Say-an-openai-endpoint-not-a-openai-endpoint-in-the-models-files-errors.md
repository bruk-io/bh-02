---
id: TASK-0159
title: 'Say an openai endpoint, not a openai endpoint, in the models file''s errors'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 19:28'
updated_date: '2026-10-18 19:51'
labels:
  - models
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0158's review. named.py _endpoint_problem builds 'is not a setting of a {provider} endpoint', which reads 'a openai endpoint'. Error messages are part of the product (root CLAUDE.md, Conventions). TASK-0158 added tests that match the full message (test_models_discovery.py _why, test_named_models.py), so they change with it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The models file's errors say 'an openai endpoint' and 'a claude-code endpoint' (the article follows the provider's name), and no other message in the models plugin builds an article before a provider name wrongly
- [ ] #2 The tests that match the message follow it; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Sites: named.py builds 'a {named.provider}' at 384 (model), 405 (endpoint), 451 (model); the factory branch returns before all three, so only 'openai' and 'claude-code' reach them. Tests that match the wrong article: test_named_models.py (119, 127, 132, 180), test_models_discovery.py (157, 191), test_models_discover_names.py (68, 176), test_models_broken_file.py (52), app/tests/test_session_dirs.py (120). claude-code tests stay as they are.
2. Tests first: change the expected text to 'an openai ...' at those sites (the parametrized id case takes the whole phrase, not a provider it would have to article itself), run the touched files, watch the openai expectations fail against the current message: that is the planted check.
3. Fix: a private pure helper in named.py picks 'an' for a name starting with a vowel, 'a' otherwise (openai, claude-code; the rule is by the letter, the names are the two built-ins), used at the three sites. No public name added.
4. Re-run the touched test files, ruff format/check on the touched files, then scripts/check bh-02/plugins/models-cordis-plugin (with gates and docs, the first member), scripts/check bh-02/app --no-gates --no-docs (it has test_session_dirs.py), and scripts/arch-check --no-fix if outside a member (not expected).
Risk: a message the grep misses. Mitigation: grep the whole repo (py, md, toml) for 'a openai', 'a claude-code', 'a {provider}' after the change. Proof for AC1: the tests in step 2 show each message with its article; the grep shows none left.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented. Changed: models_cordis_plugin/named.py: a private pure helper _article(provider) ('an' when the name starts with a, e, i, o or u, else 'a'), used at the three messages that built 'a {provider}' (the model message in problem, the endpoint message in _endpoint_problem, the model message in _models_problem; the factory branch returns before all three, so only the built-in names reach them). Lines reflowed to 110 columns. Tests: the expected text now reads 'an openai ...' in test_named_models.py, test_models_discovery.py, test_models_discover_names.py, test_models_broken_file.py and app/tests/test_session_dirs.py; in test_named_models.py the parametrized id case takes the whole phrase ('an openai endpoint', 'a claude-code endpoint') instead of a provider name it articled itself. The claude-code expectations are unchanged.
Planted check: with the test expectations changed and named.py not yet fixed, uv run pytest on the five files gave 12 failed, 179 passed; every failure was an openai expectation, e.g. 'Expected regex: colour is not a setting of an openai endpoint' against the actual 'colour is not a setting of a openai endpoint'. After the helper: the same five files, 191 passed.
Sweep (AC 1): grep -rnIE for 'a openai', 'a OpenAI', 'a claude-code' and 'a {...provider' across py, md, toml and txt, excluding site/ and backlog/: no article-before-provider wording left; the remaining 'a claude-code' hits are correct. Every provider interpolation in the models and app source (models src/tests, app src/tests) is quoted (provider 'x'), 'via' (trajectory.py) or _article(...). No stored format or name changed: a wording change, so no old file is affected. No docs page quoted the old wording.
Commands and real results: scripts/check bh-02/plugins/models-cordis-plugin: exit 0 (format: 47 files already formatted; lint: all checks passed; types: no issues in 23 source files; tests: 364 passed, 2 skipped; gates: root and libs ok; docs: built). scripts/check bh-02/app --no-gates --no-docs: exit 0 (format: 30 already formatted; lint: passed; types: no issues in 9 files; tests: 347 passed, 1 skipped). ruff format --check and ruff check on the six touched files: exit 0 after ruff format reflowed one test line.
AC 2 left unticked on purpose: its 'scripts/check passes' part is the reviewer's to prove. The test half is done: the five files pass (191), and both member checks above pass. Not run: the full scripts/check (reviewer's), scripts/arch-check (nothing changed outside a member; the models member check ran the root and libs gates, all ok), scripts/linux-jail-check (per the delegation).

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
..........ss...ssss.s..ss.s...s.s..sss.ss.s.s..s.ss..sssss........s..... [ 49%]
........................................................................ [ 51%]
........................................................................ [ 53%]
.........................................sssssssssssssssssssssssssssssss [ 54%]
ssssssssssssssssssssssssssssssssssss..............................ssssss [ 56%]
ssss...........s.........s.............................................. [ 58%]
.....s.................................................................. [ 60%]
........................................................................ [ 62%]
.................s.ss................................................... [ 64%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 98%]
.............................................                            [100%]
3817 passed, 118 skipped in 210.65s (0:03:30)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 4.70 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
