---
id: TASK-0135
title: Rewrite brig with a focus on architecture
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-17 14:58'
updated_date: '2026-10-17 18:59'
labels:
  - brig
  - size-8
dependencies: []
references:
  - >-
    backlog/decisions/decision-0008 -
    Rebuild-brig-from-empty-in-three-layers-domain-infra-and-presentation.md
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Moved

brig is rebuilt in a repository of its own, seeded on 2026-10-17 with its own board: this intent continues there as TASK-0001, and decision-0008's design as its decision-0001. The rebuild knows nothing of bh-02.

bh-02 keeps its old `libs/brig`, unchanged, and keeps working jailed. When the new brig can jail bh-02's Python process, moving the runner to its API is a bh-02 task of its own.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 brig lives in bh-02's `libs/brig`, rebuilt from empty: nothing of the old brig's code is in the folder, and it is reachable only in git history. brig imports only the standard library. Every file is Python 3.15, the supervisor program included.
- [ ] #2 Before any other work lands, bh-02's `.claude/settings.json` sets up the owner's plugins for every session in the repository, the owner's or an agent's, local or in the cloud: it registers the knowhere marketplace (`bruk-io/knowhere`), enables `philosophy@knowhere`, `authoring-kit@knowhere` and `c4-architecture@knowhere`, and approves the `likec4` server from `.mcp.json`.
- [ ] #3 The code is in three layers: `domain` does no I/O and imports nothing outside itself, `infra` imports nothing from brig and takes and returns plain data, and `presentation` is the only layer that knows both. A gate fails any change that breaks one of these rules.
- [ ] #4 Each jail type is a slice of its own, and no jail type imports another. bwrap and Seatbelt are built. oci has its place in the layout but is not built yet (paused).
- [ ] #5 Kept, and working: the filesystem policy, environment scrubbing, channels, the supervisor (named supervisor everywhere, never agent), the verified teardown and its report, grades, egress through the allowlisting proxy, and the interpreter checks.
- [ ] #6 Cut, with nothing left of them: resource limits and the trampoline, rebuilding a jail in another process, probes as public API (the batteries stay, as e2e tests), events and denial signatures, exec fidelity, the mechanism stack and its compatibility matrix, the fake runtime, and the general helper machinery (the proxy is the one helper, started and stopped as part of the jail).
- [ ] #7 The code follows the owner's Python approach (`philosophy:python-idioms`) and passes strict mypy.
- [ ] #8 Every test sits in one of three layers, defined by where the mocks start (the owner's `python-tests` rule, 0.4.6): `tests/unit/` tests one pure function, with nothing mocked; `tests/integration/` tests brig's own parts together from a real entry point, with the world faked at its edge and nowhere else (fakes only, asserted on through their state); `tests/e2e/` tests against the real world with nothing faked, either a whole journey through the public API (the batteries included) or one infra module against bubblewrap, sandbox-exec or Docker. No test in any layer patches: time, randomness and the host enter the code as data. The fakes of the world live with the integration tests, not in brig.
- [ ] #9 `just` is brig's only entry point (`libs/brig/justfile`; bh-02's `scripts/check` stays the workspace's): `just --list` shows every recipe with what it does, and each command line is written once, in the justfile.
- [ ] #10 `just check` runs only the unit and integration tests that the change reaches (the diff against `main`, plus uncommitted and untracked files), and nothing else.
- [ ] #11 `just done` runs ruff, mypy (`just typecheck`), every pypeeker gate (`check --strict`), every test in all three layers, the integration suite twice in one process to catch leaked state, the docs build and the architecture lint. It reports every step whole and every failure in one pass. An e2e test it cannot run on this host is listed by name, never counted as a pass. CI runs `just done`, and nothing else counts as green.
- [ ] #12 brig's docs live in bh-02's MkDocs site, under `docs/brig/`, and the site builds failing on any warning. Its API reference is generated from brig's public API at build time and never committed.
- [ ] #13 brig's architecture is a LikeC4 model in orthodox C4, laid out and linted by the c4-architecture plugin's rules (`likec4 validate` and c4lint clean). Its views are embedded in the docs, and the LikeC4 MCP server is enabled for every session in the repository, at a pinned version.
- [ ] #14 The SPEC is part of the docs: brig's ten laws carried over, then one section per layer.
- [ ] #15 Every line brig's own processes write (the supervisor program, the egress proxy and its decision lines) is one JSON object in one envelope, defined once and written by one encoder. The library itself writes no log: what it knows comes back to the embedder as data.
- [ ] #16 Must not break: Every one of brig's ten laws (the old SPEC, section 2) holds in the new brig. Each has a test that would fail if it stopped holding, law 10's with a planted violation and its positive control.
- [ ] #17 When the new brig can jail bh-02's Python process, bh-02's runner moves to the new API in one change, and bh-02 works again, jailed. Until then bh-02 may be broken.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Spec waived by @bruk (2026-10-17): the owner is both requester and approver, and decision-0008 carries the design.

Accepted by @bruk in conversation (2026-10-17), with the open questions resolved as above: five carried forward, the docs theme settled by staying in bh-02.

Moved 2026-10-17 at the owner's call: brig is rebuilt in its own repository, seeded from this intent and decision-0008 with bh-02 left out. Archived here; its four first-task drafts (DRAFT-0008 to DRAFT-0011) archived with it.
<!-- SECTION:NOTES:END -->
