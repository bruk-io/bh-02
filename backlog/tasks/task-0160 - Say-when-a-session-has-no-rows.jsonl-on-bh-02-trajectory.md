---
id: TASK-0160
title: 'Say when a session has no rows.jsonl, on bh-02 trajectory'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 19:32'
updated_date: '2026-10-18 22:18'
labels:
  - app
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0149's ruling (Fable, 2026-10-18). The shell makes <session>/rows.jsonl at boot, before any reply (bootstrap.py, around 488-489), so a session with a conversation and no rows.jsonl had its row log removed or never written. bh-02 trajectory then shows no reloads with no sign why. test_trajectory_view.py (around 123-125) calls that case 'its rows have not loaded yet', which is not what it is.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bh-02 trajectory prints one line, rows.jsonl not found: row reloads are not shown, for a session with a conversation and no rows.jsonl, and nothing new otherwise (tests)
- [ ] #2 test_trajectory_view.py's no-rows test says what the case is; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Failing tests first (bh-02/app/tests/test_trajectory_view.py): the no-rows test asserts the one line and no reload lines; a follow test that the line is printed once and not before the session has a conversation; the exact follow test (no rows file in it) expects the line. A pure test in test_trajectory.py: trajectory(files) with no rows gives reloads None and rendered starts with the line; b'' gives none; no conversation gives none. Seen failing before the change.
2. viewing._rows returns None for a missing rows.jsonl (still b'' for an empty one; Refused for a link or unreadable as now); shown() passes it on unchanged.
3. trajectory.py: trajectory(conversations, rows: bytes | None = None); Trajectory.reloads is None when there is no rows.jsonl; rendered() puts one line 'rows.jsonl not found: row reloads are not shown' first (depth 0, no time, key (_ROWS, 'missing')) when reloads is None and the session has an own conversation. Pure: no I/O, nothing in trajectory() decides the line.
4. Docs in step with the output: the module docstrings, GLOSSARY.md bh-02 trajectory entry, docs/bh-02/reference/command-line.md trajectory section.
Risks: the default of trajectory() changes, so callers that pass no rows now get the line (test_trajectory_records checks only with any(); test_trajectory.py's helper passes b'' explicitly). Exact-list follow test gains the line. Proof: uv run pytest on the two test files; scripts/check bh-02/app once at the end; scripts/arch-check --no-fix once because docs change outside the member.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementation notes (worker). Changed: bh-02/app/src/bh_02/viewing.py (_rows returns None for a missing rows.jsonl; an empty one is still b''; a link or unreadable file is refused as before); bh-02/app/src/bh_02/trajectory.py (trajectory(conversations, rows: bytes | None = None); Trajectory.reloads is None when there is no rows.jsonl; rendered() puts one line first, 'rows.jsonl not found: row reloads are not shown', at depth 0 with no time, key (rows, missing), when reloads is None and the session has an own conversation; docstrings updated); bh-02/app/tests/test_trajectory_view.py (the no-rows test renamed and asserting the exact lines; the exact follow test expects the line first; new follow test: the line printed once when the conversation begins); bh-02/app/tests/test_trajectory.py (new pure test); bh-02/GLOSSARY.md (bh-02 trajectory entry); docs/bh-02/reference/command-line.md (trajectory section).

Planted check, seen failing before the change: uv run pytest on test_trajectory_view.py and test_trajectory.py gave 4 failed, 82 passed; the failures were test_a_session_with_a_conversation_and_no_rows_file_says_so_in_one_line, test_following_prints_what_is_new_every_second_across_a_clear_and_a_compact, test_following_a_session_without_rows_says_so_once_when_its_conversation_begins and test_a_conversation_with_no_rows_file_has_no_reloads_and_is_said_so_first, each on the missing line. After the change those files plus test_trajectory_records.py and test_row_log.py: 98 passed.

Real command, scratch state dir (XDG_STATE_HOME set), TZ=UTC: session with transcript and no rows.jsonl prints the line first, then conversation, reply and step lines. Session with rows.jsonl (a run line and one reload) prints no line and shows row first load. Session with an empty rows.jsonl prints no line. Session with no transcript, not followed, is refused as before (exit 1).

scripts/check bh-02/app (member, with gates and docs): exit 0. format ok, lint ok, types ok (9 files), tests 371 passed 1 skipped (the skip is test_python_repl.py:1151, seatbelt is darwin's), gates ok for (root) and every libs member, docs build ok, tokens skipped (no bh-01). scripts/arch-check --no-fix: exit 0 (docs changed outside the member). Not run: the whole-repo scripts/check, which is the reviewer's to prove, so AC 2 stays unticked: its first half (the test says what the case is) is done, its second half is the reviewer's. Tasks created: none.
<!-- SECTION:NOTES:END -->
