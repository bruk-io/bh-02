---
id: TASK-0070
title: 'Recall the auto memories a message needs, told with the person''s message'
status: To Do
assignee: []
created_date: '2026-10-10 03:45'
labels:
  - memory
  - agent
  - docs
dependencies:
  - TASK-0068
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02 loads auto memory as Claude Code does at a conversation's start, the MEMORY.md index in the system prompt, and no more: a topic file reaches the model only if it opens it, and only with a tool that can. Claude Code also recalls (read from the CLI bundled with claude-agent-sdk 0.2.159, 2.1.281; behind feature flags, not in its docs). For each message of more than one word, a side request to Sonnet sees every memory file's name and description and the message, and returns up to 5 names as structured JSON. Its prompt is conservative: only memories clearly useful, careful with profile and project-overview memories ("Match on what the question IS ABOUT, not on surface keyword overlap"), never one already recalled this conversation. The chosen files, each cut at 200 lines or 4 KB with a pointer to the rest, are attached to the message in a `<system-reminder>` and shown as "Recalled from memory"; the main prompt says they are background, true when written, not instructions, and to be checked against the code before acting on them. It waits at most 2 s for the selector (a late answer joins a later step of the turn), recalls at most 60 KB a session, and skips subagents, compaction and dreams. Behind another flag, a local search index over the files (ranked terms, a relevance cut-off) replaces the Sonnet call.

In bh-02:
- The prompt stays fixed for a conversation, so recalled memories are told with the person's message, as the date is. No seam does that today (`asides` speaks only after a tool call): it needs a broker like `asides` for the person's message, with what it told recorded on the user entry so a resumed conversation does not tell it again.
- Choosing is one swappable step: a row bound under a key of its own, given the message and the memories and returning the names to recall, so a layer can replace it. Two choosers ship first, both plain code: by path (a memory's `paths` globs, told with the result of a call that opens a matching file, as memory:on_touch tells rules with `paths`; the memory tool's checks accept the key) and by words (the message against each memory's name and description, with a cut-off). A model chooser (Claude Code's default; it needs a second model row under its own key, as the advisor's option B does), embeddings or qmd are rows to add only if the labelled set shows misses that matter.
- Claude Code's limits: each memory cut at 200 lines or 4 KB, pointing to the rest through the memory tool's read (TASK-0068, which this depends on: a composition with no file tool has no other way to read it); a budget per conversation; each memory recalled at most once a conversation.
- Memories are written by the model, so recalled text is framed as background from when it was written, never as instructions, and the person sees what was recalled, as a note.

Logged by the owner (2026-10-10) as its own task.

## Open questions
- [ ] The seam's shape: a broker of its own for the person's message, or `asides` widened to it (TASK-0071 named an aside as text told beside what the model reads, which covers both).
- [ ] A chooser that answers slowly (a later model or qmd row): wait as Claude Code does (2 s, then a later step of the turn), or allow only choosers that answer at once.
- [ ] The budget per conversation (Claude Code's is 60 KB a session).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A message whose words match a memory's name or description has that memory told with it, and a call that opens a file under a memory's `paths` has that memory told with its result; each memory is told at most once a conversation, a resumed one included
- [ ] #2 Each told memory is cut at 200 lines or 4 KB with a line saying how to read the rest, and recall stops once the conversation's budget is spent
- [ ] #3 Told memories are framed as background from when they were written, not as instructions, and the person sees which were recalled
- [ ] #4 The chooser is a row a layer can replace; the shipped choosers are plain functions with tests
- [ ] #5 A labelled set of messages, each with the memories it should recall, scores the shipped choosers' precision and recall, and the numbers are in the task's notes
- [ ] #6 CONTRACTS.md, the memory plugin's README and docs/bh-02/using/memory.md describe recall
- [ ] #7 `scripts/check` passes
<!-- AC:END -->
