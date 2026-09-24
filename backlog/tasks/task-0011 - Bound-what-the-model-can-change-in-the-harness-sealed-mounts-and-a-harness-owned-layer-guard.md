---
id: task-0011
title: >-
  Bound what the model can change in the harness: sealed mounts and a
  harness-owned layer guard
status: Done
assignee: []
created_date: '2026-09-23 01:30'
updated_date: '2026-09-23 01:30'
labels:
  - cordis
  - codeact
  - bhh
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After task-0010 the model can reshape bhh two ways: mount a component (session-long, in bhh's process) or write a layer file (durable). Approval was the only line, a mounted component could depend on any key (the loader, the jail), and a layer write could switch the approver off. This narrows both with cordis's own mechanisms.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cordis has allowlist realms: use(..., expose=...) seals a subtree to the exposed keys, and what it binds stays inside (tested; invariants pass)
- [x] #2 A mounted component may depend only on the configured keys (default tools); asking for another is refused before it runs; its binds never reach the program
- [x] #3 Any tool call writing a layer file is asked about by a guard the harness mounts itself, which no layer can disable or replace, whether or not an approver row exists
- [x] #4 A composition whose loader cannot start is reported as such, not an AttributeError
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
cordis: `_Seal(exposed, outer)` on Context; `realm(key)` resolves isolate first, then a sealed subtree's exposed key in the outer context and any other key as `(seal, key)`; children inherit the seal; `use`/`Runtime.mount` take `expose`. Test: a sealed subtree sees `tools` only, waits on `loader`, and its bind of `llm` neither collides with nor leaks to the host's; invariants pass. codeact: CodeActConfig.expose (default ("tools",)); a mount whose component injects other keys is refused before it runs, and mounts use expose; a mounted `bind('kernel', ...)` leaves the program's kernel untouched. bhh.bootstrap: `layer_guard` (tools, output, layers) asks, with a `why`, about any call whose `path` resolves to a watched layer; run() adds it with `harness` and `layers` as override rows pinned `disabled=False` (a layer replacing or disabling `guard` is undone); a waiting `guard` in a composition without tools is not a stall; a loader that never started raises CompositionError with cordis's explain. Terminal confirm shows `why`. Tests: guard asks for both layer writes and not the other file, a no stands, with approve disabled and a layer replacing the guard row. Live: a cell's write_file to bhh/src/bhh/ask.toml was asked about and denied; file unchanged (the approver asked first; the first deny ends the check). Limits, stated in docs: the seal bounds what cordis hands a mounted component, not what its Python can do in-process; the guard covers tool calls, and an approved unjailed cell could still open a layer file itself.
<!-- SECTION:NOTES:END -->
