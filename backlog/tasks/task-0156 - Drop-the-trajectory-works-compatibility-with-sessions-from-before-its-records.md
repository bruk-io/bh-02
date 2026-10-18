---
id: TASK-0156
title: Drop the trajectory work's compatibility with sessions from before its records
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 14:39'
updated_date: '2026-10-18 14:46'
labels:
  - agent
  - app
  - size-2
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner's rule (root CLAUDE.md, Conventions, 2026-10-18): no backwards compatibility before a supported release. TASK-0136's work kept two paths for sessions written before its records: /compact's _is_seed still recognises a seed by its wording (_SEEDED_START) as well as by its seed field (agent plugin conversation.py), and bh-02 trajectory has handling for a transcript from before the records, which it prints with no times (bh_02 trajectory.py, viewing.py). Tests pin both, and decision-0009 promises old sessions read unchanged.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _is_seed recognises a seed only by its seed field; the wording check and its test (test_agent_conversation.py, a file from before the field) are gone
- [x] #2 bh-02 trajectory has no code or docstring for a transcript from before the records, and the tests that pin one are gone (test_trajectory.py, test_trajectory_view.py, and the agent plugin's test that a transcript from before the records resumes unchanged); where a field is legitimately absent today (decision-0009 says when), that stays
- [ ] #3 decision-0009 is amended where it promises old sessions read unchanged, citing the rule; the notes say which old files stop working; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. conversation.py: _is_seed checks the seed field only; drop _SEEDED_START (inline into _SEEDED), the wording docstrings; test_agent_conversation.py: drop LEGACY_SEEDED and its parametrized case (plant first: show the legacy case passes today and a seed with only wording must now be compacted). 2. Agent plugin: drop test_a_transcript_from_before_the_records_resumes_and_is_sent_exactly_as_it_was (test_agent_records.py); records.py, README, CONTRACTS.md, GLOSSARY.md: drop the 'from before them reads as it did' sentences. 3. bh_02 trajectory.py module docstring, viewing.py _rows docstring, tests (test_trajectory.py: old-transcript test replaced by one pinning what is legitimately absent today: an answer to a message never asked has no step, a call refused before approval has no answer; the 'no times' half of the reload test; test_trajectory_view.py: the rows-file test keeps only the live reason). Docs: command-line.md, sessions.md, app README, GLOSSARY. 4. decision-0009: amend the 'every field is optional' sentence and the Consequences line, citing the rule. 5. Proof: scripts/check agent plugin (gates+docs), then bh-02/app with --no-gates --no-docs, scripts/arch-check --no-fix not needed unless non-member files change (decisions/docs/CONTRACTS are docs; run it once anyway if a script/pyproject changes). Risk: tolerance for hand-edited/torn files in trajectory.py stays (own reason), so only the old-session statements and tests go.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed. Seed: conversation.py _is_seed is now `"seed" in message`; _SEEDED_START is gone (its text is inlined into _SEEDED, same wording); docstrings no longer mention the wording. test_agent_conversation.py: LEGACY_SEEDED and the parametrized 'a file from before the field' case removed; test_a_conversation_that_only_reads_like_a_seed_is_compacted docstring says 'no seed field'. Planted: with only the wording check removed from _is_seed and the legacy case still in the test, test_compact_with_nothing_to_compact_says_so_and_asks_nothing[legacy] failed (the model was asked to summarise, IndexError from the empty Scripted model); the case is then deleted and the file passes (40 passed, 1 skipped). Trajectory: test_agent_records.py test_a_transcript_from_before_the_records_resumes_and_is_sent_exactly_as_it_was removed (the whole-transcript-sent-unchanged case with records stays in test_agent_unanswered_calls.py). bh_02 trajectory.py module docstring no longer says a transcript from before the records prints with no times; it names the absences that stay for their own reason (answer to a message never asked: no step; call refused before approval: no answer). viewing.py _rows docstring: only 'rows have not loaded yet'. test_trajectory.py: test_a_conversation_from_before_the_records_prints_with_no_times_and_does_not_fail replaced by test_what_the_loop_leaves_out_for_its_own_reason_is_left_out_of_the_line (planted: with the 'not put to approval' line removed from _answer_text it failed, restored and it passes); the reload test lost its 'no times' half and name; test_trajectory_view.py's no-rows-file test is kept for a session whose rows have not loaded yet (a real case while following), its comment no longer says 'from before they were kept'. Kept on purpose: the reader's check of every field (a hand-edited or half-written file must not stop the view; test_a_field_of_the_wrong_type... stays), the mtime fallback for ordering a backup with no `at`, and the lines-with-no-time placement of reloads, since all three also serve those cases. Docs amended: records.py, agent README (records, seed), CONTRACTS.md (transcript), GLOSSARY.md (step record, call record, bh-02 trajectory), app README, docs/bh-02 command-line.md and sessions.md. decision-0009: the records' 'every new field is optional...' sentence, the Consequences 'Old sessions read unchanged' line and the Rejected 'format header' reason amended, and an Amended section citing the rule (root CLAUDE.md, Conventions) and TASK-0156. Old files that stop working: (1) a /compact seed written before the seed field (its first entry has the wording and no `seed`): /compact no longer refuses it as 'nothing said since the last /compact', so /compact on that conversation summarises the summary and replaces its backup; (2) a transcript from before the step/call/at records is promised nothing: the trajectory reader still skips a missing field, so it prints with whatever times it lacks left out, but nothing reads or tests it as a supported form, and a resume of it is only what the loop does with any entry (no code changed there). Not touched, left to TASK-0157's sweep: loop.py _unanswered_calls 'an older bh-02 resumed it as it was' (TASK-0142), agent README lines on asides/edits from before, tui README 'an older bh-02 emptied the file', CONTRACTS.md asides/edits 'from before'. Checks: scripts/check bh-02/plugins/agent-cordis-plugin exit 0 (193 passed, 1 skipped; gates, docs ok); scripts/check bh-02/app --no-gates --no-docs exit 0 (347 passed, 1 skipped); scripts/arch-check --no-fix exit 0. AC3's 'scripts/check passes' is left for the reviewer's full run, so AC3 is unticked.
<!-- SECTION:NOTES:END -->
