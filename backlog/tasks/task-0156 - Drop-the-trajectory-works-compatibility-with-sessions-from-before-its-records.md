---
id: TASK-0156
title: Drop the trajectory work's compatibility with sessions from before its records
status: To Do
assignee: []
created_date: '2026-10-18 14:39'
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
- [ ] #1 _is_seed recognises a seed only by its seed field; the wording check and its test (test_agent_conversation.py, a file from before the field) are gone
- [ ] #2 bh-02 trajectory has no code or docstring for a transcript from before the records, and the tests that pin one are gone (test_trajectory.py, test_trajectory_view.py, and the agent plugin's test that a transcript from before the records resumes unchanged); where a field is legitimately absent today (decision-0009 says when), that stays
- [ ] #3 decision-0009 is amended where it promises old sessions read unchanged, citing the rule; the notes say which old files stop working; scripts/check passes
<!-- AC:END -->
