---
id: TASK-0159
title: 'Say an openai endpoint, not a openai endpoint, in the models file''s errors'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 19:28'
updated_date: '2026-10-18 19:58'
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
- [x] #2 The tests that match the message follow it; scripts/check passes
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

Review: not closed. All criteria met (full scripts/check exit 0, 3817 passed, 118 skipped; AC1 verified in named.py diff). close-task refused: a bug needs its repro recorded via record-check --repro or a 'No repro:' note. The worker's planted check (12 failed before the fix) is described in prose but not recorded; the worker should record it or say why not.

Repro at 80aaa95f8349, test files: bh-02/plugins/models-cordis-plugin/tests/test_named_models.py, bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py, bh-02/plugins/models-cordis-plugin/tests/test_models_discover_names.py, bh-02/plugins/models-cordis-plugin/tests/test_models_broken_file.py, bh-02/app/tests/test_session_dirs.py; command: `uv run pytest bh-02/plugins/models-cordis-plugin/tests/test_named_models.py bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py bh-02/plugins/models-cordis-plugin/tests/test_models_discover_names.py bh-02/plugins/models-cordis-plugin/tests/test_models_broken_file.py bh-02/app/tests/test_session_dirs.py -q --tb=line` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
.......F.......F....F...........F........................FFF............ [ 37%]
......F...............F.................F....F.......................... [ 75%]
............F..................................                          [100%]
=================================== FAILURES ===================================
E   assert 'base-url is not a setting of an openai endpoint' in "endpoint 'm' (/c/models.toml): base-url is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
     +  where "endpoint 'm' (/c/models.toml): base-url is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" = str("endpoint 'm' (/c/models.toml): base-url is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature")
     +    where "endpoint 'm' (/c/models.toml): base-url is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" = problem(Named(name='m', provider='openai', id='', table={'provider': 'openai', 'base_url': 'https://h/v1', 'models': {'x': {'id': 'x'}}, 'base-url': 'y'}, source='/c/models.toml', endpoint=True))
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_named_models.py:160: assert 'base-url is not a setting of an openai endpoint' in "endpoint 'm' (/c/models.toml): base-url is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
E   assert 'key is not a setting of an openai model (m/x)' in "endpoint 'm' (/c/models.toml): key is not a setting of a openai model (m/x); a model takes id, max_tokens, temperature, and its endpoint the rest"
     +  where "endpoint 'm' (/c/models.toml): key is not a setting of a openai model (m/x); a model takes id, max_tokens, temperature, and its endpoint the rest" = str("endpoint 'm' (/c/models.toml): key is not a setting of a openai model (m/x); a model takes id, max_tokens, temperature, and its endpoint the rest")
     +    where "endpoint 'm' (/c/models.toml): key is not a setting of a openai model (m/x); a model takes id, max_tokens, temperature, and its endpoint the rest" = problem(Named(name='m', provider='openai', id='', table={'provider': 'openai', 'base_url': 'https://h/v1', 'models': {'x': {'id': 'x', 'key': 'K'}}}, source='/c/models.toml', endpoint=True))
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_named_models.py:160: assert 'key is not a setting of an openai model (m/x)' in "endpoint 'm' (/c/models.toml): key is not a setting of a openai model (m/x); a model takes id, max_tokens, temperature, and its endpoint the rest"
E   assert 'colour is not a setting of an openai endpoint; it takes' in "endpoint 'm' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
     +  where "endpoint 'm' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" = str("endpoint 'm' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature")
     +    where "endpoint 'm' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" = problem(Named(name='m', provider='openai', id='', table={'provider': 'openai', 'base_url': 'https://h/v1', 'models': {'x': {'id': 'x'}}, 'colour': 'red'}, source='/c/models.toml', endpoint=True))
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_named_models.py:160: assert 'colour is not a setting of an openai endpoint; it takes' in "endpoint 'm' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
E   assert False
     +  where False = <built-in method startswith of str object at 0x7fdaf38e2170>("endpoint 'm' (/c/models.toml): id is not a setting of an openai endpoint; it takes ")
     +    where <built-in method startswith of str object at 0x7fdaf38e2170> = "endpoint 'm' (/c/models.toml): id is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature".startswith
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_named_models.py:183: assert False
E   assert ('model_config' == 'model_config'
      
        model_config and "endpoint 'lo..., temperature" == "endpoint 'lo..., temperature"
      
      Skipping 114 identical leading characters in diff, use -v to show
      - tting of an openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature
      ?           -
      + tting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature)
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py:173: assert ('model_config' == 'model_config'
E   assert "endpoint 'lo..., temperature" == "endpoint 'lo..., temperature"
      
      Skipping 114 identical leading characters in diff, use -v to show
      - tting of an openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature
      ?           -
      + tting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py:189: assert "endpoint 'lo..., temperature" == "endpoint 'lo..., temperature"
E   assert ("endpoint 'lo..., temperature" == "endpoint 'lo..., temperature"
      
      Skipping 114 identical leading characters in diff, use -v to show
      - tting of an openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature
      ?           -
      + tting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature)
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py:201: assert ("endpoint 'lo..., temperature" == "endpoint 'lo..., temperature"
E   assert 'colour is not a setting of an openai endpoint; it takes' in "endpoint 'x' (/c/m.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
     +  where "endpoint 'x' (/c/m.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" = str("endpoint 'x' (/c/m.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature")
     +    where "endpoint 'x' (/c/m.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" = problem(Named(name='x', provider='openai', id='', table={'provider': 'openai', 'base_url': 'http://h/v1', 'discover': True, 'colour': 'red'}, source='/c/m.toml', endpoint=True))
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_models_discover_names.py:81: assert 'colour is not a setting of an openai endpoint; it takes' in "endpoint 'x' (/c/m.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
E   assert ("endpoint 'local' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" is not None and 'colour is not a setting of an openai endpoint; it takes' in "endpoint 'local' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature")
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_models_discover_names.py:192: assert ("endpoint 'local' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" is not None and 'colour is not a setting of an openai endpoint; it takes' in "endpoint 'local' (/c/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature")
E   assert 'colour is not a setting of an openai endpoint' in "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_a_default_that_can_not_be4/models.toml): colour is not a setti...ndpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
     +  where "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_a_default_that_can_not_be4/models.toml): colour is not a setti...ndpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" = ModelsError("endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_a_default_that_can_not_be4/models.toml): colour is...dpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature").message
     +    where ModelsError("endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_a_default_that_can_not_be4/models.toml): colour is...dpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature") = <ExceptionInfo ModelsError("endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_a_default_that_can_not_be4/models.t...t takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature") tblen=4>.value
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_models_broken_file.py:143: assert 'colour is not a setting of an openai endpoint' in "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_a_default_that_can_not_be4/models.toml): colour is not a setti...ndpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
E   assert ('colour is not a setting of an openai endpoint' in "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_the_status_bar_names_a_de4/models.toml): colour is not a setti...ndpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" or "not a model's name" in "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_the_status_bar_names_a_de4/models.toml): colour is not a setti...ndpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature")
/home/user/bh-02/bh-02/plugins/models-cordis-plugin/tests/test_models_broken_file.py:163: assert ('colour is not a setting of an openai endpoint' in "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_the_status_bar_names_a_de4/models.toml): colour is not a setti...ndpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature" or "not a model's name" in "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_the_status_bar_names_a_de4/models.toml): colour is not a setti...ndpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature")
E   AssertionError: Regex pattern did not match.
      Expected regex: 'colour is not a setting of an openai endpoint'
      Actual message: "endpoint 'local' (/tmp/pytest-of-root/pytest-2515/test_the_model_flag_naming_a_m0/config/bh-02/models.toml): colour is not a setting of a openai endpoint; it takes base_url, discover, include, key, key_command, key_ttl_ms, max_tokens, models, provider, temperature"
/home/user/bh-02/bh-02/app/tests/test_session_dirs.py:120: AssertionError: Regex pattern did not match.
=========================== short test summary info ============================
FAILED bh-02/plugins/models-cordis-plugin/tests/test_named_models.py::test_a_table_with_a_problem_says_what_to_fix[table5-base-url is not a setting of an openai endpoint]
FAILED bh-02/plugins/models-cordis-plugin/tests/test_named_models.py::test_a_table_with_a_problem_says_what_to_fix[table13-key is not a setting of an openai model (m/x)]
FAILED bh-02/plugins/models-cordis-plugin/tests/test_named_models.py::test_a_table_with_a_problem_says_what_to_fix[table18-colour is not a setting of an openai endpoint; it takes]
FAILED bh-02/plugins/models-cordis-plugin/tests/test_named_models.py::test_an_id_on_an_endpoint_of_a_built_in_provider_is_refused_as_any_setting_it_does_not_take[table0-an openai endpoint]
FAILED bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py::test_a_layer_s_default_naming_a_model_of_a_broken_endpoint_binds_a_model_that_says_why
FAILED bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py::test_the_models_file_s_default_naming_a_model_of_a_broken_endpoint_is_refused_the_same_way
FAILED bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py::test_slash_model_name_of_a_broken_endpoint_s_model_is_refused_and_the_status_bar_says_none
FAILED bh-02/plugins/models-cordis-plugin/tests/test_models_discover_names.py::test_a_table_that_discovers_wrongly_is_that_table_s_problem[table3-colour is not a setting of an openai endpoint; it takes]
FAILED bh-02/plugins/models-cordis-plugin/tests/test_models_discover_names.py::test_an_endpoint_whose_table_has_a_problem_names_no_model_and_says_that_problem[table0-colour is not a setting of an openai endpoint; it takes]
FAILED bh-02/plugins/models-cordis-plugin/tests/test_models_broken_file.py::test_a_default_that_can_not_be_used_is_the_row_s_error_and_everything_else_still_works[a broken endpoint's model]
FAILED bh-02/plugins/models-cordis-plugin/tests/test_models_broken_file.py::test_the_status_bar_names_a_default_that_can_not_be_used_and_says_it_is_unusable[a broken endpoint's model]
FAILED bh-02/app/tests/test_session_dirs.py::test_the_model_flag_naming_a_model_of_a_broken_endpoint_starts_the_session_and_its_model_says_why
12 failed, 179 passed in 7.52s
```

Review round 2, finding 1 (no repro on record). The planted check is now recorded as the repro, above: record-check TASK-0159 --repro -- uv run pytest on the five test files, at commit 80aaa95 (the test files there are the committed ones, unchanged since bfb348e). How it ran: for the run only, named.py was set to its pre-fix text (git show bfb348e^:bh-02/plugins/models-cordis-plugin/src/models_cordis_plugin/named.py) in the working tree, so the tests expect "an openai" and the code says "a openai": 12 failed, 179 passed, pytest exit 1, record-check recorded it (exit 0). Then named.py was restored with git checkout; git status was clean and named.py equals HEAD. The same five files on the fix: uv run pytest, the five paths, -q: 191 passed in 7.20s, exit 0. Closing check (read-only): scripts/board-check close TASK-0159 printed "ok: TASK-0159 can close", exit 0. close-task was not run and the task was not closed. No code changed in this round; the fix is bfb348e and no test file has changed since 80aaa95. Criteria as before.

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
........s......ssss...s..sss.ss..ss..ss..ss.s.s..s..s.ssss.s.......s.... [ 49%]
........................................................................ [ 51%]
................................................s....................... [ 53%]
.........................................sssssssssssssssssssssssssssssss [ 54%]
ssssssssssssssssssssssssssss.ssssss......ss.....................ssssssss [ 56%]
ssss.................................................................... [ 58%]
........................................................................ [ 60%]
........................................................................ [ 62%]
.................sss.................................................... [ 64%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
.......................s................................................ [ 71%]
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
3817 passed, 118 skipped in 215.61s (0:03:35)
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
INFO    -  Documentation built in 5.30 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review round 3: closed. Full scripts/check exit 0 (recorded). AC1: named.py's three provider messages use _article; repro recorded (12 failed pre-fix, 191 pass after). AC2: tests follow the wording; check green. No findings.
<!-- SECTION:NOTES:END -->
