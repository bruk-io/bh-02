---
id: TASK-0148
title: >-
  Say when a sub-agent's event log stopped being written, as the row log now
  does
status: To Do
assignee: []
created_date: '2026-10-18 12:33'
updated_date: '2026-10-18 19:31'
labels:
  - subagents
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0145. A child's events.jsonl (subagents plugin, eventlog.py) stops writing on a failed write and the child goes on, and nothing tells the person, so bh-02 watch and the trajectory of a sub-agent are missing its later events with no sign why. The row log now says so once after the app exits (bootstrap._row_log, through run()'s report). Decide how a plugin's event log reaches that channel without the plugin importing bh_02 (plugin-layering), then say it the same way. The owner's call is whether the sub-agent log should speak at all, since eventlog.py documents it as best-effort.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A sub-agent whose event log stops after a failed write, or at its close, is said once as a note through the parent's output.show when its run ends, naming the file, when the failure was found, the error, and that bh-02 watch shows nothing after it and must be left with Ctrl-C
- [ ] #2 A run whose logs never failed, or whose log could not be opened (already a note), says nothing new
- [ ] #3 Subagents tests with no monkeypatch: the file removed under the appender mid-run (Replaced) gives one note, a healthy run none; scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ruled 2026-10-18 by Fable, at the owner's request ("for 1 and 2, ask fable"): tell the person, as a note through the parent's output.show when the child's run ends, not after the app exits. The criteria above replace the after-exit one (finish-moved).
Why: the agents row already speaks for this file through output (a log that cannot be opened is a note, agents.py around 692-706; each child ends with a note and its usage, around 680-690). The after-exit channel is the shell's report, a parameter of run() (bootstrap.py around 406-411) that no key carries, and a key for one line is what decision-0009 refuses. Best effort (eventlog.py around 11-13) is the write policy, not silence: once _broken is set, agent_end is dropped (around 65-72), and bh-02 watch ends only at agent_end, so it follows forever. A shown note is kept in the ui's history, so a resume replays it.
Shape: eventlog.py's _broken becomes _stopped (a frozen at and error), set by write on the first OSError and by close when none was (close suppresses its OSError today, around 79, so a failure found at close is lost); a read-only stopped property. child.py: a pure log_stopped(name, kind, path, stopped) -> str beside lost and watch_command. agents.py _run's finally, after log.close(): one note before the usage note. Docs: eventlog.py docstring, the README's event log bullet, CONTRACTS.md (subagents:parent's show list), GLOSSARY (event log).
Order: after TASK-0147 (the failure's own time), which serves both lines.
<!-- SECTION:NOTES:END -->
