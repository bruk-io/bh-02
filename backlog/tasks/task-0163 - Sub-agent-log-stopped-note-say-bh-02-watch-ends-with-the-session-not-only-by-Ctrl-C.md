---
id: TASK-0163
title: >-
  Sub-agent log-stopped note: say bh-02 watch ends with the session, not only by
  Ctrl-C
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 20:58'
updated_date: '2026-10-19 00:00'
labels:
  - subagents
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0161 made bh-02 watch end its follow, saying so, once the session is no longer running (the pid in running.lock is gone). The note child.log_stopped (TASK-0148) still says a watch of a log that stopped 'must be left with Ctrl-C'; it is true only while the session runs. Reword it (child.py, subagents README line ~230, CONTRACTS.md subagents:parent row, their tests in test_agents_child.py and test_agents_wiring.py) to say watch shows nothing after it until the session is no longer running, or Ctrl-C leaves it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The log-stopped note says bh-02 watch shows nothing after the failure and ends when the session is no longer running or on Ctrl-C
- [x] #2 The subagents README, CONTRACTS.md and tests say the same; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reword the log-stopped note (child.log_stopped and its docstring) to: bh-02 watch shows nothing after that and never sees the agent end; it ends when the session is no longer running, or on Ctrl-C. Same wording in subagents README (Watching a child, ~line 226-230), CONTRACTS.md asker row (subagents:parent provides it, ~line 44). GLOSSARY.md line 106 already says it right: unchanged.
2. Tests first: update the two assertions (test_agents_child.py ~line 303, test_agents_wiring.py ~line 1761) to the new wording, run them and see them fail against the old note (the planted check).
3. Fix child.py, then rerun the two test files until green.
4. Checks: scripts/check bh-02/plugins/subagents-cordis-plugin once (gates and docs); scripts/arch-check --no-fix once since bh-02/CONTRACTS.md is outside a member. Criterion 2 says scripts/check passes: leave it unticked and say the reviewer proves it.
Risks: none to behaviour; only wording. Keep the note's line length inside ruff's limit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: child.py log_stopped (message and docstring) now says: '`bh-02 watch` shows nothing after that and never sees the agent end: it ends when the session is no longer running, or on Ctrl-C'. Same wording in bh-02/plugins/subagents-cordis-plugin/README.md (Watching a child, the log-stopped sentence) and bh-02/CONTRACTS.md (asker row, provided by subagents:parent), and in tests test_agents_child.py and test_agents_wiring.py. GLOSSARY.md line 106 already said 'until the session is no longer running or Ctrl-C leaves it': unchanged.
Planted check (seen failing): the two test assertions were changed to the new wording first; with the old child.py they FAILED (AssertionError on endswith, message still ending 'must be left with Ctrl-C'): test_agents_child.py::test_a_log_that_stopped_is_told_..., test_agents_wiring.py::test_a_log_removed_under_a_running_child_is_said_once_when_it_ends_before_its_usage. After the change: uv run pytest on those two files: 97 passed.
scripts/check bh-02/plugins/subagents-cordis-plugin (first member run, gates and docs): exit 0; format ok (12 files), lint ok, types ok (6 source files), tests 138 passed, gates ok (root, libs/brig, libs/cordis, libs/cordis-helpers, libs/host-paths), docs ok, tokens skipped (no bh-01 beside the repo).
scripts/arch-check --no-fix (CONTRACTS.md is outside a member): exit 0, all gates ok.
git grep for 'must be left' / 'left with Ctrl' outside backlog/: no matches.
Not done here: 'scripts/check passes' in criterion 2 is left unticked for the reviewer. Follow-up filed as TASK-0167: the subagents README's watch bullet (line ~235) still says 'follows it until agent_end', which omits the session-ended stop TASK-0161 added.

After the wording was in place, child.py's docstring for log_stopped was aligned to the same phrasing ('ends when the session is no longer running, or on Ctrl-C'). Re-run: scripts/check bh-02/plugins/subagents-cordis-plugin --no-docs, exit 0: format, lint, types, 138 tests passed, all gates ok.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 44%]
........................................................................ [ 46%]
.........................................................s.s....sss.s.s. [ 48%]
s...ss.s..s.s.s.s.s.s..sss..sssss.s..........s.......................... [ 50%]
........................................................................ [ 51%]
.................s...................................................... [ 53%]
......................ssssssssssssssssssssssssssssssssssssssssssssssssss [ 55%]
sssssssssssssssss................................ssssssssss..s.......... [ 57%]
....s................................................................... [ 59%]
............................s........................................... [ 60%]
......................................................................ss [ 62%]
s....................................................................... [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
..........................................................               [100%]
3902 passed, 118 skipped in 191.06s (0:03:11)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 4.05 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (reviewer, not the worker): closed. Full scripts/check exited 0, no files changed by it. Note, README, CONTRACTS.md asker row and both tests say watch ends when the session is no longer running or on Ctrl-C. Nit, not filed: child.py:558 docstring 'since the log never ends, ends when...' leaves the subject of 'ends' unclear (watch is meant). README watch bullet already queued as TASK-0167.
<!-- SECTION:NOTES:END -->
