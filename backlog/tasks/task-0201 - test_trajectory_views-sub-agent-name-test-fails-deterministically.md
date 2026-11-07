---
id: TASK-0201
title: test_trajectory_view's sub-agent name test fails deterministically
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-07 04:27'
updated_date: '2026-11-07 06:45'
labels:
  - app
  - tests
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02/app/tests/test_trajectory_view.py::test_a_sub_agent_is_a_name_in_the_agents_directory_that_bh_02_makes_and_no_other fails in 0.15 s on macOS 27.0.1 (2026-11-06): the expected 'fine' is not in the output, which begins 'rows.jsonl not found: row reloads are not shown'. TASK-0169.04's review called it pre-existing on the base commit; nobody filed it. Check on Linux too.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The cause is in the notes and the test passes on macOS and Linux, still asserting what it was written to
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Confirm cause: run the test standalone under testlock, confirm failure (already reproduced: macOS APFS is case-insensitive-but-case-preserving, so agents/General-1 and agents/general-1 are the same directory entry; the test's put() for General-1 overwrites the real general-1/transcript.jsonl, so 'fine' is replaced by 'SECRET General-1' before os.listdir ever sees two entries). 2. Verify code (_agents in viewing.py, refused_agent in watching.py) is already correct and that case-sensitivity of the regex is independently covered by test_watching.py's parametrized refused()/watched() test (which uses the literal string General-1, no filesystem involved) - so this is a test bug, not a product bug. 3. Fix the test: replace the colliding planted name General-1 with one that exercises the same uppercase-rejection shape but does not fold onto general-1 on a case-insensitive filesystem (e.g. Helper-1), add a one-line comment saying why, and add an assertion that every planted bad name is actually its own entry in agents/ (os.listdir) so a future collision cannot silently pass again. 4. Plant the violation: temporarily remove the refused_agent filter in viewing._agents, confirm the fixed test now fails with SECRET present, then restore and confirm it passes. 5. Run the single test, then bh-02/app's test suite for the touched files, then scripts/check bh-02/app (gates+docs) under testlock; note any pre-existing unrelated failures (pty/jail tests per TASK-0169.04's notes) without trying to fix them. Risk: scripts/check bh-02/app may hang on jail/pty tests on this machine - if so report the 124 rather than retry. Proof: failing-then-passing run of the planted violation, plus the real test's pass, captured in the notes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause (reproduced): on macOS (APFS, case-insensitive-but-case-preserving), planting a directory
named agents/General-1 is the same filesystem entry as agents/general-1, so the test's own
put() for "General-1" overwrote the real sub-agent's transcript.jsonl, replacing "fine" with
"SECRET General-1" before os.listdir ever saw two entries. Confirmed by running the test alone
under testlock: it failed in 0.60s with 'fine' not in output. Verified this is a test bug, not a
product bug: _agents/refused_agent (viewing.py / watching.py) use _AGENT = re.compile(r"[a-z]...")
with no re.IGNORECASE, so "General-1" is correctly refused on the string alone, independently of
any filesystem - test_watching.py's parametrized test already covers exactly this case with the
literal string "General-1", no filesystem touched.

Fix: replaced the colliding planted name "General-1" with "Helper-1" (same uppercase-first-letter
shape, no case-fold collision with "general-1"), with a comment saying why, and added an
assertion (len(os.listdir(agents dir)) == expected count) so a future planted-name collision on
a case-folding filesystem fails loudly instead of silently dropping a "SECRET" entry.

Planted violation (proof): first attempt removed the refused_agent filter in _agents entirely -
the fixed test did fail, but for the wrong reason (Refused: can't read .../agents/stray-file,
Not a directory - the test never reached the "SECRET" assertion). Re-planted narrowly instead:
refused_agent(name.lower()) in _agents, so only the uppercase-starting "Helper-1" slips past the
filter (every other planted name is refused by shape, not case) - the test then failed exactly on
`assert "SECRET" not in out` with "SECRET Helper-1" in the output. Restored the original line
(`refused_agent(name)`), confirmed `git diff bh-02/app/src/bh_02/viewing.py` is empty, and
re-ran the real test: 36 passed.

Verification:
- bh-02/app/tests/test_trajectory_view.py: 36 passed (macOS, testlock uv run pytest, -n 4)
- Linux: scripts/linux-jail-check -- bh-02/app/tests/test_trajectory_view.py -q, in the
  ubuntu 24.04 container (Python 3.15.2, aarch64-linux): 36 passed in 0.44s
- bh-02/app full suite: testlock uv run pytest bh-02/app -q -n 8 --dist loadgroup: 354 passed,
  14 skipped, 3 failed - all three pre-existing and unrelated to this change (none touch
  viewing.py, watching.py or test_trajectory_view.py, and this change touched no other file):
  test_python_repl.py::test_a_session_run_from_home_..., test_real_launch.py::
  test_a_keyed_model_s_key_never_reaches_an_input_s_environment, test_xdist_groups.py::
  test_every_test_file_that_starts_a_jail_is_in_a_group.
- scripts/check bh-02/app: format, lint and types all passed ("ok"); the tests step hung and
  testlock killed it at 1500s (exit 124), as the plan's own risk note anticipated (scripts/check
  runs pytest with -n auto, which appears to overload this 28-core machine on bh-02/app's
  pty/jail-adjacent tests - the same suite passed cleanly above under -n 8/-n 4). Not retried, and
  not fixed: it is a pre-existing machine/environment issue, out of this task's scope. Leaving
  "scripts/check passes" for the reviewer.

Note: another worktree (worktree-wf_a31c136d-eaf-18) had already started this task and written
this Implementation Plan (commits 8bbdfede/6f8f045a) without committing a code fix - a duplicate
dispatch of the same task. I brought that task file in via `git checkout 6f8f045a -- <path>`
rather than re-deriving the plan, and worked independently from there, verifying every claim in
it myself (reproduced the failure, confirmed the regex, confirmed test_watching.py's coverage,
ran my own planted-violation proof) before relying on it.
<!-- SECTION:NOTES:END -->
