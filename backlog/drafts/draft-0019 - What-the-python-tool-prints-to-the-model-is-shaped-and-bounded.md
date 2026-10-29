---
id: DRAFT-0019
title: What the python tool prints to the model is shaped and bounded
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-29T13:37:00Z'
labels:
  - python
  - codeact
  - context
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
We need tighter control over what the python tool prints to the model. Today an input's stdout, its stderr and the repr of its last expression go into one buffer. The only control is the cap: 20,000 characters (about 5,000 tokens) per input, the first 6,000 and last 14,000 kept, the whole saved to a file (worker.py). Under the cap nothing is shaped. A big list or dict as the last expression is shown whole. Colour codes and progress-bar redraws count against the cap. Warnings on stderr can push the result out. The model is not told what a cut cost, or how to read the rest.

Other harnesses (survey, 2026-10-29): smolagents caps prints at 50,000 and the last value at 20,000 separately. OpenHands cuts at 30,000 from the middle and strips ANSI. TaskWeaver gives each of stdout, stderr and error 1,500. MetaGPT's Data Interpreter keeps the first 5,000 of a success and the last 5,000 of an error, and strips ANSI.

Candidate split, in order (for sizing):
1. Measure: the distribution of output size per input from the owner's transcripts (scripts/model-friction or its own script), so we know whether the cost is a few huge dumps or a steady stream of medium outputs. This is the baseline.
2. Cap the last expression's repr with reprlib (items per container, string length, depth), leaving print to the model.
3. Clean the text before it counts: strip ANSI codes, collapse carriage-return redraws to their last state, fold runs of identical lines into one with a count.
4. Keep stderr apart from stdout, each with its own budget and label, an error's tail kept.
5. A smaller default cap, and a cut that says what it cost and how to read the rest from the saved file.

## Affected users and systems
- The person running bh-02: context and money spent on output the model didn't need, and work redone when a cut hid what mattered.
- python-cordis-plugin: worker.py (output capture, the cap, the done message), python.py (what the python section says about output), README.
- scripts/model-friction (cut_output) and TASK-0174's cache-efficiency script, which see the effect.

## Open questions
- [ ] What is the right default cap? Too small, and the model reruns things, which works against TASK-0173 (its reuse_miss count is the check).
- [ ] Should the model control the cap per input (a helper, or a comment directive), or is the saved file enough?
- [ ] Does cleaning ever lose something the model needs (colour that marks a failure, a redraw that matters)?
- [ ] Is stderr kept apart in the transcript record too, or only in what the model reads?
- [ ] Out of scope unless the owner says otherwise: what the model may see (secrets in a project file such as .env) is redaction or an access rule on reads, not output shaping.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The output-size baseline over the owner's sessions is recorded in this intent's notes, and the same measure after the changes is recorded beside it
- [ ] #2 An input whose last expression is a large container is shown within a fixed size, the cut marked
- [ ] #3 ANSI codes, carriage-return redraws and runs of identical lines no longer count against the cap
- [ ] #4 When output is cut, the model is told how much was cut and how to read the rest
- [ ] #5 Must not break: print stays the model's explicit channel; what it prints under the cap reaches it unchanged, apart from the cleaning above
- [ ] #6 Must not break: the full output is still saved when it is cut, and a line stays under the host's 1 MiB read limit
- [ ] #7 Must not break: the reuse_miss count (TASK-0173.01) does not rise because of a smaller cap
<!-- AC:END -->
