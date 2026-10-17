---
id: TASK-0101
title: >-
  Say a boot failure plainly: no app drawn first, no traceback, no false resume
  hint
status: To Do
assignee: []
created_date: '2026-10-15 02:27'
updated_date: '2026-10-17 02:34'
labels:
  - app
  - size-2
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Moved out of the naming intent TASK-0099 (was TASK-0099.09), deferred by the owner (2026-10-15): this run fixes only critical bugs, and this is not critical (the error is said and bh-02 exits; nothing is lost). Three ways a boot failure reads worse than it should: (1) a layer naming a use no plugin provides fails at boot with the loader's error, but the ui row starts first and the TUI draws its banner, composer and status bar for 1 to 2 seconds before bh-02 shuts down and prints the error; look at whether the shell can check the rows' states before the ui row starts, or hold the ui row until the chat row's dependencies are met, without making the ui depend on rows it must not reload with (a design question: say what is chosen in the notes). (2) A layer row with no use (a --patch, a session.toml) makes cordis's compose raise ValueError, which bh_02.cli's _run does not catch, so the person sees a traceback instead of a layer error naming the row and what to add (found by TASK-0099.08's close review). (3) When a session fails at boot, bh-02 still prints 'session ... (uv run bh-02 --resume to continue it)', offering a resume that fails the same way (found by TASK-0099.07's close review). Not to be started without the owner's word.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A launch whose composition cannot start prints the error without first drawing the app (checked in a pty: the screen never shows the composer), or the notes say why that cannot be done without a worse dependency
- [ ] #2 A layer row with no use makes bh-02 exit with a layer error naming the row and what to add, never a traceback; a test through the real launch
- [ ] #3 A session that fails at boot is not offered a resume; the message says it failed and what to change
- [ ] #4 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Orchestrator, 2026-10-17: the owner's word to start it, which the earlier deferral asked for: "ok wrap up all tasks that you are able to" (in conversation, this date).
<!-- SECTION:NOTES:END -->
