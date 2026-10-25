---
id: TASK-0170
title: >-
  scripts/check never reaches tests on darwin: four libs/brig type errors on
  Linux-only names
status: In Progress
assignee: []
created_date: '2026-10-25 21:02'
updated_date: '2026-10-25 21:28'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`scripts/check` (the one definition of green) fails at its types step on macOS, before tests, gates or docs run, so no reviewer on darwin can get a full-tier check to pass. Four mypy errors, all in libs/brig and all from names that exist only on Linux:

- libs/brig/src/brig/runtime/_oci_agent.py:201 - Module has no attribute "SO_PEERCRED" [attr-defined]
- libs/brig/src/brig/run/dial.py:113 - Module has no attribute "pidfd_send_signal" [attr-defined]
- libs/brig/src/brig/run/host.py:476 - Module has no attribute "memfd_create" [attr-defined]
- libs/brig/src/brig/run/host.py:485 - Returning Any from function declared to return "int" [no-any-return]

Evidence: recorded on TASK-0169.02 (reviewer's --tier full, 2026-10-25, Darwin 27.0.0, exit after 'FAILED: types'); the same four appear in TASK-0169.01's recorded check; TASK-0169.03's worker also hit them and called them pre-existing. The last commit touching the three files is e2393a1 (TASK-0164), so this is not one task's regression but a standing condition of the repo on macOS.

Cost: every worker and reviewer on macOS either scopes the check to one member (which the gates and cross-member types do not cover) or reports a red full check they then have to explain away, which is how a real failure gets mistaken for this one. Fix is a design choice for the owner - a platform guard mypy understands (sys.platform narrowing), a per-module override in libs/brig's mypy settings, or typing the three uses behind a getattr seam - not a decision this review should make.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/check on macOS reaches its tests, gates and docs steps and reports them, with no type error from a Linux-only name in libs/brig
- [ ] #2 The chosen fix keeps the Linux behaviour type-checked rather than silencing the modules wholesale, and a note says which approach was taken and why
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approach: an explicit `sys.platform != "linux"` guard at the three Linux-only call sites (commit 3ee5f3e), not a mypy `platform` setting and not a per-module override. `brig/run/host.py:_source_fd` raises OSError (its docstring already said it raises when not on Linux), `brig/run/dial.py:_pidfd_alive` answers False (a pidfd is Linux's, so elsewhere no process is held), `brig/runtime/_oci_agent.py:accept_hello` raises AgentStartFailed. This keeps the Linux path fully type-checked on Linux (mypy analyses it there) and the code matches its own docstring; a `platform = "linux"` setting would have stopped mypy looking at the darwin branches, and a module override would have silenced three modules wholesale.

Evidence: `uv run mypy` -> Success on 208 files (host platform, darwin); `uv run mypy --platform linux` -> Success on 208 files; brig unit tests for dial, peer, pidfd, accept_hello pass; `scripts/arch-check --no-fix` ok for every gate. Pre-existing and unrelated: `libs/brig/tests/unit/test_process_namespaces_pure.py` fails to collect on darwin (`signal.SIGRTMIN`).

Correction to the draft's premise, from the TASK-0169.01 review: `scripts/check` starts every step at once and reports in order, so a types failure does not stop tests, gates and docs; the earlier runs never reached them because stray test runs held the jail lock. AC #1 is therefore a question about a full run on a quiet machine; one is running now and its result goes here.
<!-- SECTION:NOTES:END -->
