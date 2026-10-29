---
id: DRAFT-0019
title: Models reuse what they keep in the python REPL
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-29T01:43:00Z'
updated_date: '2026-10-29T01:44:00Z'
labels:
  - size-8
  - python
  - codeact
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
The models don't end up reusing what they persist to the REPL. The python tool's namespace lasts for the run, and the python section says so, but sessions show models redoing work (searching, reading, running a program again) instead of using a variable an earlier input already bound. The model is only ever told what is in the namespace through its own history of inputs and outputs, and after /compact through its own summary of them.

A survey of other CodeAct harnesses (2026-10-29: smolagents, OpenHands, TaskWeaver, DSPy RLM, marimo, MetaGPT Data Interpreter, langgraph-codeact, Anthropic's code execution with MCP and programmatic tool calling, Cloudflare Code Mode, Manus) found almost none show the model its live namespace. marimo (name, type, preview) and DSPy RLM (type, length, head and tail preview) list variables, but not the ones the model makes. TaskWeaver's compaction writes a variable list (name, type, description) into its summary. No harness sends a per-input namespace diff, and none publishes evidence that a variable listing improves reuse.

Candidate split, in order (for sizing):
1. A reuse count in scripts/model-friction, as the baseline.
2. The live variable list carried into the /compact summary, read from the Python process rather than the model's memory (TaskWeaver's practice).
3. Rebalance the python section: an explicit look-before-you-recompute rule (smolagents, DSPy RLM), with less of its length on startup-file checks, which could be told when the model writes the file.
4. A line before each input's output naming what that input bound, rebound or deleted, by type and size, after PythonProcess._offered; the whole list after a restart, a resume or /compact.

## Affected users and systems
- The person running bh-02: steps and context spent on work already done.
- python-cordis-plugin: worker.py (the done message), client.py (what an input's output is told), python.py (the python section), README.
- The /compact path (agent and chat plugins) for item 2.
- scripts/model-friction.

## Open questions
- [ ] What counts as a reuse miss the friction script can see: the same program or search run again, a name assigned again from the same expression, a file read again unchanged? Carried forward: the baseline task (split item 1) answers it, since its finish line is that definition written in SIGNALS.
- [ ] Is the cause forgetting a name, not trusting that state lasts, or not knowing what a variable holds? The baseline should tell these apart if it can. Carried forward: the baseline task tries; whatever it can't separate, the before-and-after comparison of items 3 and 4 shows indirectly.
- [ ] How much context a per-input line may cost, and its cap. Carried forward: the per-input line task (item 4) sets the cap; it doesn't block the baseline or the compaction list.
- [ ] Is in-place mutation (a list appended to) worth reporting, or only bindings? Carried forward: decided in item 4's plan, bindings first; only item 4 depends on it.
- [ ] Can /compact ask the Python process for its namespace, and what does it say when the process is not running? Carried forward: the compaction task (item 2) answers it in its plan; nothing else depends on it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/model-friction reports reuse misses per session, and its definition of one is written in its SIGNALS
- [ ] #2 A before-and-after comparison on the same kinds of session shows fewer reuse misses, or the intent records that it did not and what was learned
- [ ] #3 After /compact, the model is told the REPL's live variables by name and type
- [ ] #4 Must not break: the system prompt stays fixed for a conversation (the prompt cache); namespace news goes in tool results
- [ ] #5 Must not break: no value's repr reaches the model unasked; a variable is described by type, size and signature only
- [ ] #6 Must not break: an input's output stays within the 20,000-character cap, and a namespace line has its own cap
<!-- AC:END -->
