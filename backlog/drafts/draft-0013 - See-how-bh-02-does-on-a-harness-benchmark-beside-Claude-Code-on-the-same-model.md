---
id: DRAFT-0013
title: >-
  See how bh-02 does on a harness benchmark, beside Claude Code on the same
  model
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-19 03:46'
labels:
  - app
  - eval
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
I don't know whether bh-02's harness helps the model or gets in its way. The checks prove bh-02 is correct, and the trajectory shows what happened in a session, but nothing compares it with another harness on the same tasks and the same model, and so far its trajectories come from fake models, not real work. Harness benchmarks exist for this: Terminal-Bench 2.0, run with Harbor, takes a custom agent and ships Claude Code as a built-in one. bh-02 already reaches Claude through Claude Code, so bh-02 beside plain Claude Code on the same model isolates what bh-02's own layer adds (CodeAct in a jailed REPL, the fixed prompt, asides, the approval rule). It is a yardstick, not a target.

## Affected users and systems
- Me, deciding where bh-02 goes next.
- bh-02 itself: it is a TUI today and needs a way to run a task with nobody at the keyboard (headless), which is useful beyond an eval.
- The jail and approval rule inside a benchmark's task container; the models row and which credential a run uses.
- Terminal-Bench 2.0 and Harbor (or another harness benchmark), Docker on my Mac.
- bh-02 trajectory and scripts/model-friction, which get real sessions to read.

## Open questions
- [ ] Which benchmark first: Terminal-Bench 2.0 through Harbor, or SWE-bench Verified or Pro.
- [ ] How many tasks and trials make a fair first comparison, and what token budget that costs.
- [ ] Which credential the runs use: the subscription token (are bulk eval runs within its terms and limits?) or an API or gateway endpoint.
- [ ] How approvals work with nobody there: the jail inside the task container (bubblewrap may need privileges there), or --no-jail with an approve-everything policy inside a container that is already isolated.
- [ ] How Harbor runs bh-02: installed in the task container (AbstractInstalledAgent) or as a BaseAgent.
- [ ] Where the runs happen: my Mac, or CI.

Drafted by the orchestrator from a conversation with the owner (2026-10-19); the owner corrects it before anyone accepts it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02 runs a task with nobody at the keyboard: started with the task, it works until the model answers, then exits with what happened
- [ ] #2 A slice of a harness benchmark is run with bh-02 and with Claude Code on the same model, several trials each, and the pass rates are written down side by side with what they cost
- [ ] #3 The run's sessions are read with bh-02 trajectory and scripts/model-friction, and what they show about where bh-02 helps or trips is written down
- [ ] #4 Must not break: the jail and approval rule hold in the headless run; any policy that lets calls run unasked is one I chose explicitly for the run
- [ ] #5 Must not break: the credential rule in CLAUDE.md holds wherever the runs happen
- [ ] #6 Must not break: nothing in bh-02's prompt or tools changes only to raise the score
<!-- AC:END -->
