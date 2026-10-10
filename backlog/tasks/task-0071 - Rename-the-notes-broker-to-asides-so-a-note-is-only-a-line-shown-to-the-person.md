---
id: TASK-0071
title: >-
  Rename the notes broker to asides, so a note is only a line shown to the
  person
status: To Do
assignee: []
created_date: '2026-10-10 03:58'
labels:
  - agent
  - memory
  - docs
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
- [ ] #1 The broker, its row, key, component and the transcript `tool` entry's field are `asides` everywhere (code, tests, the shipped layer, CONTRACTS.md, the READMEs, bh-02/CLAUDE.md, GLOSSARY.md, the docs site); nothing at run time accepts `notes`
- [ ] #2 The loop's own change messages are called asides wherever they are described; auto memory is described as memories, never notes
- [ ] #3 `note` is used only for the event, a line shown to the person, and the glossary says so
- [ ] #4 `bh-02 update-layer` rewrites a layer naming the `notes` row or `agent:notes` to `asides` and `agent:asides` (tested)
- [ ] #5 The docs page is prompt-and-asides.md, and the docs build (mkdocs --strict) finds no broken link
- [ ] #6 `scripts/check` passes
<!-- AC:END -->
