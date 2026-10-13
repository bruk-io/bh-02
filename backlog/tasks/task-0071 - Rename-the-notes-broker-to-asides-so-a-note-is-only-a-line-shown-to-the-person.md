---
id: TASK-0071
title: >-
  Rename the notes broker to asides, so a note is only a line shown to the
  person
status: Done
assignee: []
created_date: '2026-10-10 03:58'
updated_date: '2026-10-10 04:46'
labels:
  - size-3
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
"Note" means five things in bh-02: the `notes` key (agent:notes, a broker of functions that add text to a call's result: how on-demand CLAUDE.md files and rules arrive), the `notes` field on a transcript `tool` entry (what they told, kept for a resume), "told as a note" (the loop telling the model a change, a tool added or the prompt edited, on its next message), the `note` event (the shell speaking to the person: a command's answer, or a line showing what the model was told), and auto memory as "notes the model keeps for itself". The broker's name says nothing of what it does, and in one sentence about memory two of these meet.

Decided with the owner (2026-10-10):
- The broker, its row, key, component and transcript field become `asides`: an aside is text told to the model beside what it reads, a call's result now (and the person's message too, if TASK-0070's recall takes that route).
- The loop's own change messages are asides too: "told as an aside".
- Auto memory is "memories", never "notes".
- `note` stays the event's name, so it means one thing: a line shown to the person.
- No backwards compatibility. Nothing at run time accepts the old name, and a transcript written before reads without its `notes` field, so a resumed old conversation may tell an instruction again. `update-layer`'s rename maps (`bh_02/outdated.py`) get `notes` → `asides` and `agent:notes` → `agent:asides`, as every renamed row does: that rewrites a layer once, it is not a second name. `scripts/model-friction` reads the new field; a session saved before reads as one from before the loop kept the field, which it already handles.
- The docs page `how-it-works/prompt-and-notes.md` becomes `prompt-and-asides.md`, every link with it.

TASK-0068, TASK-0069 and TASK-0070 say `notes` where they mean the broker; once this lands, read `asides`. TASK-0064 renamed names that collided before: same approach, mechanical where a tool can do it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The broker, its row, key, component and the transcript `tool` entry's field are `asides` everywhere (code, tests, the shipped layer, CONTRACTS.md, the READMEs, bh-02/CLAUDE.md, GLOSSARY.md, the docs site); nothing at run time accepts `notes`
- [x] #2 The loop's own change messages are called asides wherever they are described; auto memory is described as memories, never notes
- [x] #3 `note` is used only for the event, a line shown to the person, and the glossary says so
- [x] #4 `bh-02 update-layer` rewrites a layer naming the `notes` row or `agent:notes` to `asides` and `agent:asides` (tested)
- [x] #5 The docs page is prompt-and-asides.md, and the docs build (mkdocs --strict) finds no broken link
- [x] #6 `scripts/check` passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Agent plugin: `loop.Notes`/`Note`/`noted` become `Asides`/`Aside`/`asides_for`; the `tool` entry's field `notes` is `asides`; the loop's change message (`note` in `_asked`, `_told`'s result) is an aside; the component `wiring.notes` is `wiring.asides` (`agent:asides`, key `asides`). The `{"type": "note"}` events stay.
2. Memory plugin: `touch.Notes` is `Asides`; `on_touch` takes `asides`; `OnTouch` reads the `asides` field; its prose says aside where it means what is told with a result; auto memory is memories.
3. Shell: `bh-02.toml`'s row; `outdated.py` maps `notes` -> `asides` (`_RENAMED`) and `agent:notes` -> `agent:asides` (`_RENAMED_USES`), and `agent:memory` goes straight to `asides`; a test in `test_outdated_layers.py`.
4. Tests across the family that mount the row, add to the broker or read the field.
5. `scripts/model-friction` reads `asides`.
6. Docs: CONTRACTS.md, GLOSSARY.md (asides, aside, note = the event only, memories), bh-02/CLAUDE.md, READMEs, `docs/bh-02/` (page renamed to prompt-and-asides.md, mkdocs nav, every link).

### Risks
- "note" has five senses; a blind replace would rename the `note` event. Each hit is read, not substituted.
- A transcript written before reads without the field: `OnTouch` falls back to searching the entry's text, so an instruction may be told again (accepted in the description).

### Proof
- `grep` finds no `notes` meaning the broker or field in code, tests, layer or docs.
- `test_outdated_layers.py` covers the rewrite; `mkdocs build --strict` passes; `scripts/check` passes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Names: the key and row `asides`, component `agent:asides` (`wiring.asides`); `loop.Asides`, `Aside`, `asides_for` (were `Notes`, `Note`, `noted`); `memory_cordis_plugin.Asides` (was `Notes`); the `tool` entry's field `asides`. Nothing at run time reads `notes`: `OnTouch` searches an entry without `asides` as it did one from before the loop kept them.
- The loop's own change messages are asides (`_asked(..., aside)`, `_told`). The python tool's startup lines before an input's output are asides too (`client._told`), and its section of the prompt says so.
- `note` is only a line shown to the person: the `note` event, and the command line's `note:` lines. GLOSSARY.md has **note**, **aside**, **asides** and **notes** (the old row, renamed by update-layer); CONTRACTS.md's event shape says "a line shown to the person, never the model".
- Auto memory is memories in code, docs, the shipped layer's comment and the runner's test.
- `update-layer`: `notes` -> `asides` in `_RENAMED`, `agent:notes` -> `agent:asides` in `_RENAMED_USES`, and `agent:memory` straight to `asides`. Tests: `test_the_notes_broker_reads_as_asides`, `test_update_layer_rewrites_a_layer_naming_the_notes_broker`.
- `scripts/model-friction` reads `asides`; its shell-hint pattern is `_SHELL_HINT` (was `_NOTE`). An entry with `notes` goes through the text fallback (checked by hand: the result comes back without its asides either way).
- Docs: prompt-and-notes.md is prompt-and-asides.md, its nav entry and every link with it; the extensions page's example is `keep` (was `notes`).
- Where "note" meant something else, it says what: `/compact`'s seed is bh-02's message, the claude-code provider's prompt opens with a line naming the tools, `/model` marks a shadowing model, the cli's reports.
- `scripts/check`: format, lint, types, gates and docs pass. Its tests step stops at collecting the warden systray tests on Linux (`rumps` is darwin-only), which this change does not touch.

- Close review (a reviewer who did not do the work): all six criteria met; verdict close. Its findings, fixed before close: a comment in `models_cordis_plugin/openai/testing.py` still said the loop's note; update-layer's clash message read "has a 'asides' row", now "has a row 'asides' too" (every clash message, its tests with it); `test_loop.py`'s list of note events is `shown`.
- Full workspace run (no systray): 2092 passed, 12 failed, all in `libs/brig` (egress proxy, kill group, teardown, probe runner, subset), which this change does not touch (`git diff -- libs` is empty): the container, not this change. bh-02's own: 782 passed, and its real-launch tests passed in the full run.
<!-- SECTION:NOTES:END -->
