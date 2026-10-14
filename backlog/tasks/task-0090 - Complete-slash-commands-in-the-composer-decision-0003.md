---
id: TASK-0090
title: Complete slash commands in the composer (decision-0003)
status: Done
assignee:
  - '@claude'
created_date: '2026-10-14 00:01'
updated_date: '2026-10-14 06:02'
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
- [x] #1 Typing a one-line / (stripped as the broker strips it) shows, between the transcript and the composer, the palette's entries that match: prefix matches first in the palette's order, then substring matches, case-insensitive, arguments through choices (/model h shows /model haiku); at most 8 one-line rows, help dimmed and cut to the width; the composer keeps focus and the transcript keeps its newest line in view
- [x] #2 Entries are read once per opening (a spec whose choices counts its calls is called once per opening, not per key) and filtered per key; the frame's commands changing while open does not re-read them; a stale entry chosen is answered as an unknown command
- [x] #3 While open: Up/Down move the highlight; Tab completes without running; Enter follows decision-0003's rule (takes the highlight only when moved, or when no space is typed and the text is a strict prefix of the highlighted call; otherwise sends as typed); Esc closes it for the line and TextArea never sees it; Ctrl-J and Shift+Enter close it. With the list closed every key behaves as today
- [x] #4 It closes on send, on focus loss and when a question is put up, and never opens while one is up; a click on a row runs it through choose; Ctrl-P's choose writing /name opens it on that command's choices
- [x] #5 palette_entries strips C0, DEL and C1 control characters from each entry's call, help and usage, and rows in both views are built as Content with markup escaped; a test of each
- [x] #6 frame.completions is pure, in frame.py's __all__, unit-tested (prefix before substring, order, case, arguments, not a / line, a leading space, more than one line, an empty /); Pilot tests cover the decision's list, including a 15-row and a 40-column terminal and a reply streaming
- [x] #7 Nothing outside the tui plugin changes but docs: CONTRACTS.md's frame row (read when the palette is searched and when the list opens), the tui README's palette paragraph, docs/bh-02/using/commands.md; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1 frame.py: completions() pure + __all__; palette_entries strips C0/DEL/C1 (unit tests first, seen failing with strip removed). 2 widgets/completions.py: OptionList subclass (can_focus False, Content rows, 8-row cap, display none when empty), takes PaletteEntry. 3 composer.py: key routing while open (Up/Down/Tab/Enter rule/Esc/Ctrl-J/Shift+Enter) via a small pure decision function. 4 app.py: layout between transcript and composer, snapshot per opening, open/close rules (TextArea.Changed, blur, question, send, choose), on_frame_changed doc. 5 Pilot tests per decision Tests list; plant violations (Enter replacing typed text, snapshot per key, strip removed, focusable list) and see each fail. 6 docs: CONTRACTS frame row, tui README palette paragraph, commands.md. 7 scripts/check, arch-check, mypy, bh-02/app tests. Risks: transcript anchoring with 8 rows on 15-row terminal; Esc reaching TextArea; Enter-rule edge cases; pypeeker purity/privacy gates. Proof: planted failures noted.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted by the owner, 2026-10-14 (promoted from a draft), with decision-0003's defaults as written.

Built per decision-0003: frame.py (completions, slash_line, enter_takes pure, in __all__; palette_entries strips C0/DEL/C1 and drops empty names), widgets/completions.py (Completions OptionList, can_focus False, Content rows via row(), snapshot per opening), composer.py (list keys while open, Chose message), app.py (layout, follow composer, close on blur/palette/question, click and Chose go through choose), docs (CONTRACTS frame row, tui README, commands.md). Tests: tests/test_completions_list.py (21 Pilot/unit) and 6 new in test_frame.py. Planted violations seen failing then restored: Enter always taking highlight -> enter-rule test failed; snapshot re-read per key -> once-per-opening test failed; control-char strip removed -> control-character test failed; can_focus True -> click/focus test failed; Esc case removed -> Esc test failed. Results: tui plugin tests 183 passed; scripts/arch-check exit 0 (first run caught row() impure via Content.truncate, rewritten with rich.cells); uv run mypy clean; scripts/check exit 0 (2558 passed, 31 skipped; tokens step skipped, no bh-01 dist), run as root without tini. Judgments: substring match compares what follows the leading / (so /ea finds /clear; with the / included it could never match); a trailing space is kept when matching so '/model ' lists the choices; Ctrl-P opening and palette choose close the list explicitly because pushing the palette screen does not blur the composer.

Closed on review (Opus, low) of 0b88057: CLOSE, all seven criteria met, nothing blocking. Driven with Pilot at 60x20: /mo lists /model and its choices with help cut; Tab gives /model with choices; Enter on /model sends it (the broker strips the space); Esc keeps the text and the list stays shut; Ctrl-J closes it; a question arriving hides the list and it does not reopen after the answer. Plants each failed their tests: Enter always taking the highlight, prefix-only Enter, reading per key, no Esc, no strip, markup rows, allowed=True under a question. Wide characters cut within the width (rich.cells). tui 183 passed; bh-02/app 195 passed; arch-check and mypy exit 0; scripts/check's tests 2558 passed (its gates passed alone). The worker's calls judged sound: substring after the /, trailing space kept, explicit close on Ctrl-P, /model sent with its space. Should-fix filed (blocking-only rule): TASK-0089.01. Nits left: palette_entries drops a bare / call (harmless); each key resets the highlight to the first row (not in the decision).
<!-- SECTION:NOTES:END -->
