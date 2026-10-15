---
id: DRAFT-0007
title: Run the REPL under the project's own .venv
status: Draft
assignee: []
created_date: '2026-10-14 15:57'
labels:
  - python
  - runner
  - size-3
dependencies: []
priority: medium
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Direction agreed by the owner (2026-10-14): the REPL's environment is a .venv per project. Today the Python process is worker.py run under bh-02's own interpreter (python -I worker.py SOCKET, client.py), so an input imports the standard library and whatever bh-02's venv holds, never the project or its dependencies; the jail can read bh-02's venv but not write it, and jailed code cannot reach the network, so nothing an input does can install a package. Options weighed with the owner: A bh-02's interpreter (today); B the project's own .venv (chosen: the REPL imports the code being edited and its dependencies, which come from the project's own uv add, made by the person outside the jail); C an environment bh-02 builds from declared dependencies (later, only if a helper needs something the project lacks).

## Open questions
- [ ] A project with no .venv: fall back to bh-02's interpreter, or make one (uv venv) and say so?
- [ ] worker.py's Python floor: it is standard library only but written to bh-02's 3.15 (it uses match); which oldest Python must it run on, and the gate that checks it (run it under that Python in a test)?
- [ ] How the runner's jail reads the project's .venv and its interpreter (a venv's python may link outside the project, e.g. to uv's managed Pythons): what the jail must read, never write.
- [ ] What the model and the person are told: which interpreter the REPL runs on, and what to do to add a dependency.
- [ ] The person's startup file's imports, when the project's .venv lacks what it imports.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision records where the REPL's interpreter comes from, the fallback, the worker's Python floor and its gate, and what the jail reads, with each open question answered or carried
- [ ] #2 Build tasks are filed from it, each sized, none started
<!-- AC:END -->
