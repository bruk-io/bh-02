---
id: decision-0007
title: >-
  Run brig's supervisor on Python 3.15, the interpreter brig and bh-02 run on,
  never an older one
date: '2026-10-17 14:50'
status: accepted
---
## Context

brig's supervisor (decision-0001, built by TASK-0079.06) is a stdlib-only program that runs as each
jail's PID 1, and since TASK-0079.10 inside a container whose image has a python3. brig's SPEC
(decision-190) lets it run under any python3 from 3.9 on, so an embedder could use a host's system
Python, and a test parses the program as 3.9. bh-02's runner offers it two interpreters, best first
(`runner_cordis_plugin.jail.host_interpreters`): `/usr/bin/python3`, then the Python bh-02 itself runs
on (`sys.base_prefix`'s). So the jail's PID 1 runs under 3.12 or 3.13 while brig and bh-02 require
3.15 (`requires-python = ">=3.15"`), and the one program brig cannot import from is written in an
older dialect, outside strict mypy and the house idioms (`match`, `sentinel`, `frozendict`, `type`).

What already holds, and shaped the choice: the jail mounts bh-02's own interpreter read-only for the
program it starts, and TASK-0124, TASK-0126 and TASK-0127 keep an input from replacing it, the
project at the home directory included. brig's only embedder is bh-02.

Weighed and not taken:
- **Keep the 3.9 floor for other embedders.** There are none; the floor costs the supervisor the
  language the rest of brig is written in, and its own type checking.
- **Mount the host's 3.15 into a container whose image has an older python3.** Possible for a
  glibc image, broken for a musl one (Alpine); the container is the jail (decision-203), and
  `docker exec` already starts processes where the image has no usable Python.

## Decision

The owner, 2026-10-17: stick with 3.15.

1. brig's supervisor runs only under Python 3.15 or later. brig's default interpreter for it is the
   one brig itself runs on (its base interpreter, never a venv's), not `/usr/bin/python3`.
2. bh-02's runner offers the supervisor its own interpreter only (`sys.base_prefix`'s); the system
   Python is no longer a candidate. Where that interpreter cannot be held safely in a jail, the start
   fails closed (`InterpreterNotMounted`), with what to do, rather than falling back to an older one.
3. In a container, the supervisor is used only when the image's python3 is 3.15 or later; otherwise
   processes start through `docker exec` (decision-203), graded as they are today.
4. The supervisor program is written to the repository's 3.15 dialect and checked by strict mypy like
   the rest of brig. The 3.9 parse test goes; a test pins that it refuses to start under an older
   interpreter, saying which it needs.
5. brig's SPEC records this as a ruling amending decision-190, with the implementing task.

## Consequences

- The jail's PID 1 runs on the interpreter bh-02 runs on: one Python per session, no system Python in
  the path.
- The supervisor can share the house idioms and its wire messages can be closed TypedDicts on both
  ends, specified once.
- A host where bh-02's interpreter cannot be held in a jail can no longer start one under the system
  Python; it is told why. TASK-0126 and TASK-0127 made that case unreachable for the layouts measured.
- A container image needs a 3.15 python3 for the supervisor; any other image uses `docker exec`.
- CI's `linux-jail` job and `scripts/linux-jail-check` run the supervisor under uv's 3.15, which both
  already install for the app.

## Acceptance

Decided by the owner in conversation, 2026-10-17 ("I'm making the decision to stick with 3.15"), after
the orchestrator's account of what holds the supervisor below 3.15. Accepted as written. Supersedes
decision-190's "any python3, 3.9 or later". Built by TASK-0134.
