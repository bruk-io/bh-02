---
id: TASK-0069
title: Close the gaps between auto memory's instructions and Claude Code's
status: Done
assignee: []
created_date: '2026-10-10 03:34'
updated_date: '2026-10-14 15:03'
labels:
  - memory
  - docs
  - size-1
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`auto_section` (memory_cordis_plugin/auto.py) tells the model the four kinds of memory, a topic file per memory with `name`/`description`/`type` frontmatter, and a line for each in MEMORY.md. Claude Code's auto memory prompt (read from the CLI bundled with claude-agent-sdk 0.2.159, 2.1.281; it varies behind feature flags) also tells its model these, which bh-02's leaves out:
- Before saving, check for a memory that already covers it, and update that one rather than add a duplicate.
- For `feedback` and `project`, write the rule or fact, then a **Why:** line and a **How to apply:** line.
- Turn relative dates into absolute ones.
- Write `description` as one specific line: it is what decides, later, whether the memory is relevant.
- Don't save what CLAUDE.md, the code or git history already records, or what only matters to this conversation; asked to remember one of those, ask what was non-obvious about it and save that.
- A memory naming a file, function or flag is a claim that it existed when the memory was written: check it still does before recommending it, and for the repository's current state read the code or git log rather than a memory's snapshot.
- Keep each memory file short (Claude Code's recall shows only its first 200 lines or 4 KB) and organised by topic: split or summarise one that outgrows that.

These are judgement rules, so they are prose. The mechanical ones (a slug name, a known `type`, a one-line `description`, the index matching the files) are code in TASK-0068's memory tool, and this task adds no checks for them. Split from TASK-0068 by the owner (2026-10-10); independent of it, so whichever lands second keeps the other's text in the section. The section is in every request's system prompt, so each rule takes as few words as it needs, in bh-02's voice; a conversation started after the change gets it (the prompt stays fixed for one).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `auto_section` tells the model each rule the description lists: check for an existing memory before saving; the **Why:** / **How to apply:** body for `feedback` and `project`; absolute dates; a specific one-line `description`; what not to save, and what to save instead when asked; checking a memory against the code before recommending from it; keeping each memory file short and organised by topic
- [x] #2 test_memory_auto.py checks that the section says each rule
- [x] #3 The memory plugin's README and docs/bh-02/using/memory.md, where they say what the model is told about auto memory, say the same
- [x] #4 `scripts/check` passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) tests first in bh-02/plugins/memory-cordis-plugin/tests/test_memory_auto.py: one parametrised test, one case per rule, each a distinctive phrase absent from the current auto_section text; run it and record the failures. (2) Add the seven rules to auto_section in src/memory_cordis_plugin/auto.py, short, in bh-02 voice, no em dashes, Canadian spelling, existing sentences kept; rerun until green. (3) Same short list of what the model is told in the README Auto memory section and in docs/bh-02/using/memory.md (reference/plugins/memory.md includes the README). (4) Memory plugin tests as root, then scripts/check, exit codes read directly. Risks: every request carries the section, so words are kept to what each rule needs; a phrase matching existing text would pass before the change, so each is checked absent first. Proof: failing run and passing run recorded in notes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-1 (2026-10-11): prompt text, a test that it says each rule, two docs; nothing unknown.

Changed: memory_cordis_plugin/auto.py auto_section (seven rules added in the section text, existing sentences kept; the section is now 316 words, MEMORY.md line unchanged); tests/test_memory_auto.py (one parametrised test, 11 cases, one distinctive phrase per rule, each absent from the old text: grep count 0 before the edit); README.md Auto memory section and docs/bh-02/using/memory.md (the same seven-bullet list in both; reference/plugins/memory.md includes the README). Seen failing first: test_memory_auto.py before the prompt edit gave 11 failed, 6 passed (all 11 new cases failed); after it, 17 passed, exit 0. Memory plugin tests as root: uv run pytest bh-02/plugins/memory-cordis-plugin -q gave 59 passed, exit 0. scripts/check as root (log in the scratchpad, read by exit code, not piped): format ok, lint ok, types ok (187 files), tests 2802 passed 31 skipped, gates ok, docs ok (mkdocs build), tokens skipped (no bh-01 dist beside the repo); exit 0. No em dashes in the changed text; Canadian -ise spellings (organised, summarise). Not run: scripts/linux-jail-check (not touched by this change) and the tester-user run (memory plugin tests are unprivileged-safe but were run as root per the brief).

Close review (Opus low, independent): CLOSE, no blocking findings. All seven rules present and correct; removing any one rule's sentence in a scratch copy fails at least one test case; memory tests 59 passed; scripts/check exit 0 (2802 passed). Should-fix joined TASK-0068 (it rewrites this section next): the README and memory.md bullets leave out 'read the code or git log for the current state' and 'split or summarise one that outgrows that'; the 'don't save what CLAUDE.md, the code or git records' rule is spread over two sentences that name it differently. Nits answered: '4 KB' vs '25KB' spacing; the example date is the commit's date; 'split or summarise' has no test phrase; the docs give the cap without Claude Code's reason, as the prompt does. Suggested trims (about 15 words) are in the review, for TASK-0068's pass.
<!-- SECTION:NOTES:END -->
