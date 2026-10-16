---
id: TASK-0121
title: >-
  Say what a claude-code endpoint runs on, not 'on the subscription', in the
  docs and messages a gateway has made untrue
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 13:35'
updated_date: '2026-10-16 22:07'
labels:
  - models
  - docs
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0104.02, whose scope was the detached launcher only. Since TASK-0104.01 a claude-code endpoint with base_url and key_command runs the Claude Code CLI against a company gateway with no subscription token, but these still say bh-02 runs Claude on the subscription: bh-02/GLOSSARY.md (about line 51), CLAUDE.md (about line 46), bh-02/app/README.md (about line 4), docs/bh-02/how-it-works/loop.md (about lines 65-66), README.md (about line 128), the models plugin README's intro (about line 343), and a message in bh-02/plugins/models-cordis-plugin/src/models_cordis_plugin/named.py (about line 555). A test name in test_claude_code_credential.py (about line 99) says 'subscription' too: rename it only if it now says something false.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each listed place says what is true with both routes (the subscription token in local.env, or a gateway's base_url and key_command), and git grep for 'on the subscription' outside backlog/ finds only text that is about the subscription route itself
- [x] #2 No behaviour changes but the message's wording, and its test (if one quotes it) follows; scripts/check for each member touched passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Find: git grep 'on the subscription' outside backlog/ (8 hits) plus the unlisted 'on your subscription' / 'on a Claude subscription' phrases, each classed as the subscription route itself (leave) or stale (reword).
2. Reword the listed places, keeping each line's length: root CLAUDE.md uv-run-bh-02 line; bh-02/GLOSSARY.md model provider line; bh-02/app/README.md opening; docs/bh-02/how-it-works/loop.md claude-code bullet (settings: a gateway's one layer); root README.md models example comment (the [claude] table is the subscription route, so say what it is, no 'on the subscription'); models README claude-code section intro (line ~343); named.py's gateway-needs-both message (one of the two alone is refused, so 'without either runs on the subscription' is false; the message now says give both or neither). test_named_models quotes only 'a gateway needs both', which stays.
3. The test name test_the_detached_launcher_drops_every_variable_that_would_leave_the_subscription: the scrub guards the gateway route as well, so the name is false; rename with uv run pypeeker rename, not by hand.
4. Leave (about the subscription route itself): CLAUDE.md e2e line and test_claude_code_live (the only e2e test, subscription-only), models README line 29 and named.py:36 (a claude-code endpoint with no base_url), named.py:589 (the token), test_models_gateway name (contrasts the token with the key_command).
5. Proof: scripts/check bh-02/plugins/models-cordis-plugin (gates and docs), scripts/check bh-02/app --no-gates --no-docs (app README touched), scripts/arch-check --no-fix (docs and root files touched), grep again. No safety gate changes: wording and one test name, so no planted violation; the test quoting the message is run.
Risks: pypeeker rename of a test symbol in a module named by path; mkdocs strict on the README include; line length 110 in named.py.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed (8 files): root CLAUDE.md (the uv run bh-02 commands line), bh-02/GLOSSARY.md (model provider), bh-02/app/README.md (opening paragraph), docs/bh-02/how-it-works/loop.md (claude-code bullet: a gateway's one layer of bh-02's own settings is loaded), README.md (the [claude] example comment: the table is the subscription token's endpoint, no base_url), bh-02/plugins/models-cordis-plugin/README.md (claude-code section intro, 'on a Claude subscription' -> 'with a subscription token or through a company gateway'), models_cordis_plugin/named.py (the refusal of a claude-code endpoint with one of base_url/key_command: was 'without either, Claude Code runs on the subscription token', which is false for one alone (it is refused, not the subscription); now 'give both, or neither, which uses the subscription token in local.env'). Test: test_claude_code_credential.py test_the_detached_launcher_drops_every_variable_that_would_leave_the_subscription renamed to ..._that_would_change_the_steps with uv run pypeeker rename (tx c706b894ca3d): the scrub guards the gateway route as well, so 'would leave the subscription' says something false now. test_named_models.py quotes only 'a gateway needs both', which the new message keeps, so it follows without a change. No heading renamed (TASK-0122).

Searches: git grep -n -i 'on the subscription' -- ':!backlog' after the change finds 5 hits, all about the subscription route itself, left: CLAUDE.md:54 (the e2e command; the only e2e test is test_claude_code_live.py, subscription-only), models README:29 ('Claude on the subscription is a claude-code endpoint' with no base_url), claude_code/credential.py:3 (the token on the subscription), named.py:36 (a claude-code endpoint with no base_url runs on the subscription token), test_claude_code_live.py:1 (the e2e test). Also left, already naming both routes: app/src/bh_02/cli.py:85 ('on the Claude subscription, ... or through a gateway'). Not in the list, not matched by the grep, left and reported: docs/bh-02/get-started.md:40 ('bh-02 reaches Claude through Claude Code, on your subscription'), claude_code/__init__.py:1 ('on a Claude subscription'), README.md:96 (the setup block is only the subscription's token).

Proof (run from the worktree, exit codes read directly):
- uv run pytest on test_claude_code_credential.py, test_named_models.py, test_models_gateway.py: 64 passed.
- tini -s -- scripts/check bh-02/plugins/models-cordis-plugin: exit 0 (format ok, lint ok, types 23 files ok, tests 349 passed 2 skipped, gates ok, docs mkdocs strict ok, tokens skipped: no bh-01 checkout).
- tini -s -- scripts/check bh-02/app --no-gates --no-docs: first run exit 1 (238 passed 1 skipped; 3 failures: two jail tests in test_python_repl.py, which found a .bashrc/.profile in the project and a .git/config, and test_booting.py's 'stopped early' test with a 2 s wait_for, under load). Each of the three passed when run alone (exit 0, 3 passed), and the second full run exit 0: 238 passed, 1 skipped. The machine was shared with two other workers, load average 4.7. None of the three reads a gateway message or a doc, so they look like the shared host, not this change.
- tini -s -- scripts/arch-check --no-fix: exit 0 (root, brig, cordis, cordis-helpers, host-paths ok).
Planted violation: none, no safety property changed (wording and a test name). Timing: none recorded.

Widened the list to three more places, on the coordinator's direction: docs/bh-02/get-started.md (line 40 and the credential section after it, which said bh-02 reaches Claude 'on your subscription' and that a missing token is a subscription error), the module docstring of models_cordis_plugin/claude_code/__init__.py ('on a Claude subscription'), and the README.md setup block (its 'Claude Code makes a token for your subscription' comment now says the token is the subscription's and that a gateway endpoint, base_url and key_command, needs none). Why: each says Claude runs only on the subscription, the stale claim this task is about; my earlier grep missed them because they say 'on your subscription' and 'on a Claude subscription', not 'on the subscription'. Also reworded, beyond those three and noted here so it can be reverted: the 'What you need' bullet at get-started.md:10, which named a Claude subscription as the only Claude option (same claim, same file). No heading renamed; the only new link is using/models.md#claude-through-a-gateway, an existing heading, which resolves in the built site (href ../using/models/#claude-through-a-gateway, id present).

Re-run after these doc edits: tini -s -- scripts/check bh-02/plugins/models-cordis-plugin exit 0 (format, lint, types, 349 passed 2 skipped, gates, docs, tokens skipped); tini -s -- scripts/arch-check --no-fix exit 0. git grep -i for 'on the subscription|on your subscription|on a Claude subscription' outside backlog/ now finds only text about the subscription route itself (CLAUDE.md:54 e2e, models README:29, credential.py:3, named.py:36, test_claude_code_live.py:1, get-started.md:62 'For Claude on your subscription:' and models.md:7/132) plus cli.py:85, which names both routes.
<!-- SECTION:NOTES:END -->
