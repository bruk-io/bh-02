---
id: DRAFT-0002
title: 'Tidy auto memory in the background, as Claude Code''s auto-dream does'
status: Draft
assignee: []
created_date: '2026-10-10 12:15'
labels:
  - memory
dependencies:
  - TASK-0068
priority: low
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Auto memory only grows: the model adds and edits topic files as it works, and nothing goes back over them, so duplicates, stale facts and relative dates pile up. Claude Code tidies its auto memory with auto-dream (read from the CLI bundled with claude-agent-sdk 0.2.159, 2.1.281; not in its docs; the `autoDreamEnabled` setting overrides a server-side default). Once at least 24 hours and 5 sessions have passed since the last one (`minHours: 24`, `minSessions: 5`, under a lock so one runs at a time), a background agent run goes over the memory directory and recent session transcripts in four phases: orient (list the directory, read the index), gather (recent session logs, memories that drifted from the code, narrow greps of the transcripts), consolidate (merge into existing topic files, turn relative dates absolute, delete facts since contradicted), and prune (keep the index short). Its tools are read-only shell commands plus deleting `.md` files in the memory directory; it never edits CLAUDE.md, and flags a memory that contradicts it instead. The Dreams API (Managed Agents, research preview) is the same idea on Anthropic's servers, and does not fit bh-02: it needs an API key, memory stores and Managed Agents sessions.

In bh-02 a dream would be a conversation of its own whose only way to change anything is TASK-0068's memory tool, which keeps its writes to the memory directory by construction. MEMORY.md is generated there (TASK-0068), so pruning is about topic files. A draft until it is accepted; acceptance criteria come with accepting it.

## Open questions
- [ ] Where it runs: in a session, in the background on a trigger like Claude Code's, or as a command the person runs.
- [ ] What it reads besides the memory files: bh-02's session transcripts are in its state directory, which the jail keeps from the model (`host.secrets`), so a dream reading them hands their text to the model from the host.
- [ ] Which model runs it, and whether the person sees or approves what it changed (Claude Code's returns a summary).
<!-- SECTION:DESCRIPTION:END -->
