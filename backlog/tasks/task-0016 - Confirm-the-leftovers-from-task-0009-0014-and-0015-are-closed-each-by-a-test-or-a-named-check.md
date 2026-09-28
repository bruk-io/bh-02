---
id: task-0016
title: >-
  Confirm the leftovers from task-0009, 0014 and 0015 are closed, each by a test
  or a named check
status: Done
assignee: []
created_date: '2026-09-28 12:26'
updated_date: '2026-09-28 12:41'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Done notes of task-0009, task-0014 and task-0015 named items left open. Reading the current code suggests several were closed later, but nothing ties each closure to a test. This task proves each one closed, with a test that exercises the behaviour (added if missing) or, for an operational item, a named check that can be repeated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A meta.json that is not JSON, lacks a key, or has a wrongly typed value neither crashes startup nor listing; a named test covers it
- [x] #2 permission_for denies an MCP tool name from any server other than bh (e.g. mcp__other__python) and a bare built-in name; a named test covers it
- [x] #3 Events gathered while the app draws a batch are drawn once it finishes, even when no further event arrives (a reply pausing mid-stream); a named test covers it
- [x] #4 /clear removes the earlier conversation from the screen, not only from the model; a named test covers it
- [x] #5 The REPL's lifecycle line printing onto a live prompt is moot: the REPL no longer exists (bh-02 is a Textual TUI)
- [x] #6 The bhh-final tag is on the remote (bruk-io/bhh), pointing at 4b7852c
- [x] #7 No saved bh-02 session names the pre-rename tool (mcp__bhh__), and no bhh session state is left under XDG_STATE_HOME; checked on this machine
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Every item was already closed by later work; each is now tied to a check (7 named tests run, all pass):
1. Broken meta.json: bh_02/sessions.py returns Broken for an unreadable record. Tests: app/tests/test_session_dirs.py::test_a_broken_record_is_skipped_and_named_with_what_is_wrong, ::test_the_sessions_value_lists_a_broken_record_after_the_sessions, app/tests/test_command_line.py::test_sessions_skips_a_broken_record_and_names_it_on_stderr, app/tests/test_real_launch.py::test_a_broken_session_record_is_named_once_and_the_app_still_starts.
2. permission_for (models_cordis_plugin/claude_code/declared.py:128) allows only mcp__bh__<declared>. Test: models-cordis-plugin/tests/test_claude_code_permission.py::test_only_the_declared_python_tool_is_allowed_and_nothing_else_is_asked_about (denies Bash, Write, bare python, mcp__bh__write_file, mcp__other__python). strict_mcp_config=True also keeps other servers out (claude_code/provider.py:350).
3. Batch flush: tui_cordis_plugin/ports.py show() re-flushes from the draw future's callback. Test: tui-cordis-plugin/tests/test_ports.py::test_what_gathered_is_posted_once_the_app_has_drawn_even_if_the_reply_pauses.
4. /clear on screen: the cleared event clears the transcript widget (widgets/transcript.py:229). Test: tui-cordis-plugin/tests/test_transcript.py::test_cleared_drops_the_conversation_from_the_screen_and_a_resume_starts_after_it.
5. The lifecycle line on a live prompt was the old REPL's; bh-02 is a Textual TUI and row lifecycle shows in the status bar (frame.py/status.py).
6. gh api repos/bruk-io/bhh/tags: bhh-final -> 4b7852c on the remote.
7. grep -rl mcp__bhh__ ~/.local/state/bh-02 -> 0 files (12 sessions); ~/.local/state/bhh does not exist. The check was run on this machine only.
<!-- SECTION:NOTES:END -->
