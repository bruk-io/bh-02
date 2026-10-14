---
id: TASK-0090
title: Complete slash commands in the composer (decision-0003)
status: To Do
assignee: []
created_date: '2026-10-14 00:01'
updated_date: '2026-10-14 00:03'
labels:
  - tui
  - size-2
dependencies: []
references:
  - >-
    backlog/decisions/decision-0003 -
    Complete-slash-commands-in-the-composer-from-the-commands-the-palette-already-reads.md
modified_files:
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/frame.py
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/widgets/completions.py
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/widgets/composer.py
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/widgets/__init__.py
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/app.py
  - bh-02/plugins/tui-cordis-plugin/README.md
  - bh-02/CONTRACTS.md
  - docs/bh-02/using/commands.md
parent_task_id: TASK-0089
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first task under TASK-0089 (Make bh-02's TUI comfortable for everyday use with small quality-of-life changes). Its spec is decision-0003 (backlog/decisions/decision-0003 - Complete-slash-commands-in-the-composer-from-the-commands-the-palette-already-reads.md), reviewed three times (composition, boundaries, Textual) with every finding taken; read it whole before planning.

In short: an inline list between the transcript and the composer, in the tui plugin alone, reading palette_entries(), the Ctrl-P palette's own list. No new key, no new row, no change to commands or tui:palette; tui:ui keeps depending on nothing. Entries are read once each time the list opens and filtered as the person types; a pure frame.completions matches them; palette_entries strips control characters for both views; the widget takes no focus; Up/Down, Tab, Enter, Esc, Ctrl-J and Shift+Enter behave as the decision's Keys section says, only while the list is open.

The decision's defaults stand unless the owner changes them before this starts: the Enter rule (never replace typed text the person did not pick), an 8-row cap, and the list opening on Ctrl-P's choose.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Typing a one-line / (stripped as the broker strips it) shows, between the transcript and the composer, the palette's entries that match: prefix matches first in the palette's order, then substring matches, case-insensitive, arguments through choices (/model h shows /model haiku); at most 8 one-line rows, help dimmed and cut to the width; the composer keeps focus and the transcript keeps its newest line in view
- [ ] #2 Entries are read once per opening (a spec whose choices counts its calls is called once per opening, not per key) and filtered per key; the frame's commands changing while open does not re-read them; a stale entry chosen is answered as an unknown command
- [ ] #3 While open: Up/Down move the highlight; Tab completes without running; Enter follows decision-0003's rule (takes the highlight only when moved, or when no space is typed and the text is a strict prefix of the highlighted call; otherwise sends as typed); Esc closes it for the line and TextArea never sees it; Ctrl-J and Shift+Enter close it. With the list closed every key behaves as today
- [ ] #4 It closes on send, on focus loss and when a question is put up, and never opens while one is up; a click on a row runs it through choose; Ctrl-P's choose writing /name opens it on that command's choices
- [ ] #5 palette_entries strips C0, DEL and C1 control characters from each entry's call, help and usage, and rows in both views are built as Content with markup escaped; a test of each
- [ ] #6 frame.completions is pure, in frame.py's __all__, unit-tested (prefix before substring, order, case, arguments, not a / line, a leading space, more than one line, an empty /); Pilot tests cover the decision's list, including a 15-row and a 40-column terminal and a reply streaming
- [ ] #7 Nothing outside the tui plugin changes but docs: CONTRACTS.md's frame row (read when the palette is searched and when the list opens), the tui README's palette paragraph, docs/bh-02/using/commands.md; scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted by the owner, 2026-10-14 (promoted from a draft), with decision-0003's defaults as written.
<!-- SECTION:NOTES:END -->
